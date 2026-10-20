#!/usr/bin/env python3
"""Adapted from fail2ban-ddos.zip/attacker/flood.py (teacher's bounded lab).

Retains the shared rate limiter, worker pool, deadline and stop event. Adds CLI,
transport error categories, discarded response bodies, latency/RPS JSON and signals.
This stage deliberately enforces <=20 RPS, <=4 workers and <=10 seconds.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import http.client
import json
import math
from pathlib import Path
import signal
import socket
import ssl
import threading
import time


class RateLimiter:
    """One aggregate start budget, never one budget per worker or catch-up burst."""

    def __init__(self, rps):
        self.interval = 1 / rps
        self.next_request_at = time.monotonic()
        self.lock = threading.Lock()

    def wait_for_turn(self, stop, deadline):
        with self.lock:
            delay = max(0, self.next_request_at - time.monotonic())
            if stop.wait(delay) or time.monotonic() >= deadline:
                return False
            self.next_request_at = time.monotonic() + self.interval
            return True


def percentile(values, quantile):
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)]


def request(config):
    """Read/discard bounded responses; never save body, headers or exception text."""
    started = time.monotonic()
    connection = None
    try:
        if config.scheme == 'https':
            context = ssl.create_default_context(cafile=config.ca_file)
            connection = http.client.HTTPSConnection(config.host, config.port,
                timeout=config.timeout, context=context)
        else:
            connection = http.client.HTTPConnection(config.host, config.port, timeout=config.timeout)
        connection.request('GET', config.path, headers={'Connection': 'close'})
        response = connection.getresponse()
        total = 0
        while True:
            remaining = config.timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            chunk = response.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > 4 * 1024 * 1024:
                return 'protocol_error', 'response_size_limit', None
        return 'http', str(response.status), (time.monotonic() - started) * 1000
    except (TimeoutError, socket.timeout):
        return 'timeout', 'timeout', None
    except ssl.SSLCertVerificationError:
        return 'connection_error', 'tls_certificate', None
    except socket.gaierror:
        return 'connection_error', 'dns', None
    except ConnectionRefusedError:
        return 'connection_error', 'refused', None
    except ConnectionResetError:
        return 'connection_error', 'reset', None
    except OSError:
        return 'connection_error', 'other_os_error', None
    except http.client.HTTPException:
        return 'protocol_error', 'http_protocol', None
    finally:
        if connection is not None:
            connection.close()


def run(config, stop=None):
    stop = stop or threading.Event()
    began_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    deadline = started + config.duration
    limiter = RateLimiter(config.rps)
    lock = threading.Lock()
    outcomes = {kind: Counter() for kind in ('http', 'timeout', 'connection_error', 'protocol_error')}
    latencies = []

    def worker():
        while not stop.is_set() and limiter.wait_for_turn(stop, deadline):
            kind, detail, latency = request(config)
            with lock:
                outcomes[kind][detail] += 1
                if latency is not None:
                    latencies.append(latency)

    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        futures = [pool.submit(worker) for _ in range(config.concurrency)]
        for future in futures:
            future.result()
    elapsed = time.monotonic() - started
    completed = sum(outcomes['http'].values())
    attempted = sum(sum(counts.values()) for counts in outcomes.values())
    return {
        'started_at_utc': began_at,
        'configuration': {'host': config.host, 'port': config.port, 'scheme': config.scheme,
            'path': config.path, 'duration_s': config.duration, 'concurrency': config.concurrency,
            'rps_limit_global': config.rps, 'timeout_s': config.timeout, 'expected_status': config.expected_status},
        'elapsed_s': round(elapsed, 6), 'interrupted': stop.is_set(),
        'attempted': attempted, 'http_completed': completed,
        'expected_responses': outcomes['http'][str(config.expected_status)],
        'http_statuses': dict(outcomes['http']), 'timeouts': sum(outcomes['timeout'].values()),
        'connection_errors': dict(outcomes['connection_error']), 'protocol_errors': dict(outcomes['protocol_error']),
        'rps_completed': round(completed / elapsed, 6),
        'rps_attempted': round(attempted / elapsed, 6),
        'http_latency_ms': {name: round(value, 6) if value is not None else None
            for name, value in [('p50', percentile(latencies, .50)),
                                ('p95', percentile(latencies, .95)), ('p99', percentile(latencies, .99))]},
        'latency_population': 'completed HTTP responses, including non-expected HTTP statuses',
        'sensitive_data_saved': False,
    }


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', help='Hostname/IP only, without credentials or URL scheme')
    parser.add_argument('port', type=int)
    parser.add_argument('--scheme', choices=('http', 'https'), default='http')
    parser.add_argument('--path', default='/')
    parser.add_argument('--duration', type=float, default=10)
    parser.add_argument('--concurrency', type=int, default=1)
    parser.add_argument('--rps', type=float, default=2, help='Aggregate limit across ALL workers')
    parser.add_argument('--timeout', type=float, default=1)
    parser.add_argument('--expected-status', type=int, default=200)
    parser.add_argument('--ca-file', help='Optional trusted CA for HTTPS; verification remains enabled')
    parser.add_argument('--output', type=Path, help='Optional sanitized JSON destination')
    config = parser.parse_args(argv)
    if not config.host or any(c in config.host for c in '/@?#\r\n'):
        parser.error('host must be a hostname/IP, without URL or credentials')
    if not 1 <= config.port <= 65535:
        parser.error('port must be 1..65535')
    if not config.path.startswith('/') or any(c in config.path for c in '?\r\n#'):
        parser.error('path must be absolute, without query strings or fragments')
    if not 0 < config.duration <= 10 or not 1 <= config.concurrency <= 4 or not 0 < config.rps <= 20:
        parser.error('stage limits: duration <=10 s, concurrency <=4, global RPS <=20; positive values only')
    if not 0 < config.timeout <= 2 or not 100 <= config.expected_status <= 599:
        parser.error('timeout must be >0 and <=2 s; expected HTTP status must be 100..599')
    return config


def main():
    config = arguments()
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda signum, frame: stop.set())
    result = run(config, stop)
    encoded = json.dumps(result, indent=2)
    if config.output:
        config.output.write_text(encoded + '\n')
    print(encoded, flush=True)
    return 130 if result['interrupted'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
