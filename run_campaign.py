#!/usr/bin/env python3
"""Fixed, serial campaign defined in PROTOCOL.md. Does not build/recover services."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / 'videojuegos-backend'
HOST = subprocess.check_output(['bash', str(BACKEND / 'lab.sh'), 'docker-host'], text=True).strip()
DOCKER = ['docker', '--host', HOST]
NETWORK = 'ciber-p1-games_lab'
IMAGE = 'python:3.12-slim'
CLIENT_A, CLIENT_B = 'games-loadtest-a', 'games-loadtest-b'
SERVICES = ('frontend', 'backend', 'keycloak', 'openldap', 'postgres')
HTTP = {'frontend': (4200, '/'), 'backend': (8000, '/health'),
        'keycloak': (8080, '/realms/games-lab/.well-known/openid-configuration')}
STOP = threading.Event()
for signum in (signal.SIGINT, signal.SIGTERM):
    signal.signal(signum, lambda signum, frame: STOP.set())


def now():
    return datetime.now(timezone.utc).isoformat()


def docker(*args, timeout=15):
    return subprocess.check_output(DOCKER + list(args), text=True, timeout=timeout)


def container(service):
    return f'ciber-p1-games-{service}-1'


def execute(service, *args):
    return docker('exec', container(service), *args)


def ignoreip(service):
    values = []
    for line in execute(service, 'fail2ban-client', 'get', 'http-flood', 'ignoreip').splitlines():
        try:
            values.append(str(ipaddress.ip_network(line.split()[-1], strict=False)))
        except (ValueError, IndexError):
            pass
    return sorted(values)


def is_ignored(service, ip):
    return any(ipaddress.ip_address(ip) in ipaddress.ip_network(net) for net in ignoreip(service))


def banned(service):
    return execute(service, 'fail2ban-client', 'status', 'http-flood').split('Banned IP list:', 1)[1].split()


def protection():
    result = {}
    for service in ('frontend', 'backend', 'keycloak', 'openldap'):
        jail = 'ldaps-connections' if service == 'openldap' else 'http-flood'
        listing = execute(service, 'fail2ban-client', 'status')
        assert jail in listing, f'{service}: jail missing'
        execute(service, 'fail2ban-client', 'status', jail)
        result[service] = {'jail': jail, 'active': True}
        if service in HTTP:
            result[service]['ignoreip'] = ignoreip(service)
    return result


def states():
    text = docker('inspect', *(container(s) for s in SERVICES), '--format',
        '{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}} {{.RestartCount}} {{.State.OOMKilled}}')
    return {parts[0].lstrip('/'): {'status': parts[1], 'health': parts[2],
        'restarts': int(parts[3]), 'oom_killed': parts[4] == 'true'}
        for parts in (line.split() for line in text.splitlines())}


PROBE = '''import http.client,json,sys,time
t=time.monotonic(); c=http.client.HTTPConnection(sys.argv[1],int(sys.argv[2]),timeout=1)
try:
 c.request('GET',sys.argv[3],headers={'Connection':'close'}); r=c.getresponse(); r.read()
 print(json.dumps({'status':r.status,'latency_ms':(time.monotonic()-t)*1000,'error':None}))
except Exception as e:
 print(json.dumps({'status':None,'latency_ms':(time.monotonic()-t)*1000,'error':type(e).__name__}))
finally: c.close()
'''


def probe(client, service):
    port, path = HTTP[service]
    return json.loads(docker('exec', client, 'python3', '-c', PROBE, service, str(port), path))


def host_cpu():
    fields = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return sum(fields), fields[3] + fields[4]


def available_memory():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('MemAvailable not available')


def bytes_value(value):
    number, unit = re.fullmatch(r'([\d.]+)(\w+)', value.strip()).groups()
    multiplier = {'B': 1, 'kB': 1000, 'MB': 1000**2, 'GB': 1000**3,
                  'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3}[unit]
    return int(float(number) * multiplier)


class Monitor(threading.Thread):
    def __init__(self, service, baseline):
        super().__init__(daemon=True)
        self.service, self.baseline = service, baseline
        self.done, self.abort = threading.Event(), threading.Event()
        self.samples, self.problems = [], []

    def run(self):
        previous = host_cpu()
        high_cpu = 0
        while not self.done.is_set():
            sample_started = time.monotonic()
            try:
                observation = probe(CLIENT_B, self.service)
                rows = docker('stats', '--no-stream', '--format', '{{json .}}',
                              *(container(s) for s in SERVICES), CLIENT_A, CLIENT_B)
                metrics = {}
                for row in rows.splitlines():
                    data = json.loads(row)
                    metrics[data['Name']] = {'cpu_percent': float(data['CPUPerc'].rstrip('%')),
                        'memory_bytes': bytes_value(data['MemUsage'].split('/')[0])}
                current = host_cpu()
                total = current[0] - previous[0]
                cpu = 100 * (1 - (current[1] - previous[1]) / total) if total else 0
                previous = current
                memory = available_memory()
                status = states()
                self.samples.append({'at_utc': now(), 'observer_b': observation,
                    'host_cpu_percent': round(cpu, 3), 'host_available_bytes': memory,
                    'containers': metrics, 'states': status})
                if observation['status'] != 200 or observation['latency_ms'] >= 1000:
                    self.problems.append('observer_b_unavailable_or_slow')
                if status != self.baseline:
                    self.problems.append('service_health_restart_or_oom_changed')
                if memory < 1024**3:
                    self.problems.append('host_available_memory_below_1GiB')
                high_cpu = high_cpu + 1 if cpu >= 85 else 0
                if high_cpu >= 2:
                    self.problems.append('host_cpu_at_least_85_percent_twice')
                if self.problems:
                    self.abort.set()
                    return
            except Exception as error:
                self.problems.append('monitor_error:' + type(error).__name__)
                self.abort.set()
                return
            # Enforce the observer budget even if Docker stats returns unusually fast.
            self.done.wait(max(.2, 2 - (time.monotonic() - sample_started)))


def release(service, ip):
    if is_ignored(service, ip):
        execute(service, 'fail2ban-client', 'set', 'http-flood', 'delignoreip', ip)
    if ip in banned(service):
        execute(service, 'fail2ban-client', 'set', 'http-flood', 'unbanip', ip)


@contextmanager
def stage_guard(service, ip, capacity):
    """A per-stage in-container lease restores runtime state even if host dies."""
    assert not is_ignored(service, ip) and ip not in banned(service)
    watchdog_code = ("import subprocess,time; time.sleep(25); "
        "subprocess.run(['fail2ban-client','set','http-flood','delignoreip'," + repr(ip) + "]); "
        "subprocess.run(['fail2ban-client','set','http-flood','unbanip'," + repr(ip) + "])")
    launcher = "import subprocess; p=subprocess.Popen(['python3','-c'," + repr(watchdog_code) + \
        "],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True); print(p.pid)"
    watchdog = int(execute(service, 'python3', '-c', launcher))
    try:
        if capacity:
            execute(service, 'fail2ban-client', 'set', 'http-flood', 'addignoreip', ip)
            assert is_ignored(service, ip)
        yield
    finally:
        if capacity:
            time.sleep(2)  # Let the still-running polling filter discard the last exempt records.
        release(service, ip)
        assert not is_ignored(service, ip) and ip not in banned(service)
        execute(service, 'python3', '-c',
            'import os,signal,sys\ntry: os.kill(int(sys.argv[1]),signal.SIGTERM)\nexcept ProcessLookupError: pass', str(watchdog))


def firewall_counter(service, ip):
    rules = execute(service, 'iptables', '-nvxL', 'f2b-http-flood')
    for line in rules.splitlines():
        parts = line.split()
        if ip in parts and parts[2] in ('REJECT', 'DROP'):
            return int(parts[0])
    return 0


def run_stage(service, rps, concurrency, mode, ip):
    capacity = mode.startswith('capacity')
    baseline = states()
    assert all(s['status'] == 'running' and s['health'] == 'healthy' and not s['oom_killed'] for s in baseline.values())
    assert available_memory() >= 1024**3
    monitor = Monitor(service, baseline)
    with stage_guard(service, ip, capacity):
        position = int(execute(service, 'python3', '-c',
            'from pathlib import Path; print(Path("/var/log/fail2ban.log").stat().st_size)'))
        monitor.start()
        port, path = HTTP[service]
        # Print PID once so an abort signals the actual generator, not just docker exec.
        bootstrap = 'import os,sys; print("PID",os.getpid(),flush=True); os.execv(sys.executable,[sys.executable,*sys.argv[1:]])'
        args = ['exec', CLIENT_A, 'python3', '-c', bootstrap, '/work/flood.py', service, str(port),
                '--path', path, '--duration', '10', '--concurrency', str(concurrency), '--rps', str(rps)]
        process = subprocess.Popen(DOCKER + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            first_line = process.stdout.readline().strip().split()
            assert first_line[0] == 'PID'
            pid = first_line[1]
            signalled = False
            deadline = time.monotonic() + 17
            while process.poll() is None:
                if (STOP.is_set() or monitor.abort.is_set()) and not signalled:
                    docker('exec', CLIENT_A, 'python3', '-c',
                           'import os,signal,sys; os.kill(int(sys.argv[1]),signal.SIGINT)', pid)
                    signalled = True
                if time.monotonic() > deadline:
                    raise RuntimeError('Generator exceeded bounded stage deadline')
                time.sleep(.1)
            output, errors = process.communicate(timeout=3)
            assert process.returncode in (0, 130), 'Generator failed; exception output intentionally omitted'
            result = json.loads(output)
        finally:
            monitor.done.set()
            monitor.join(timeout=15)
            if process.poll() is None:
                docker('stop', '--time', '1', CLIENT_A)
                process.wait(timeout=5)
        assert not monitor.is_alive(), 'Resource monitor did not stop'
        # If the safety lease fired early, capacity data are invalid.
        if capacity:
            assert is_ignored(service, ip), 'Safety lease expired during measurement'
        is_banned = ip in banned(service)
        packet_count = firewall_counter(service, ip) if is_banned else 0
        new_ban = execute(service, 'python3', '-c',
            'from pathlib import Path; import sys,re; s=Path("/var/log/fail2ban.log").read_text()[int(sys.argv[1]):]; '
            r'print(bool(re.search(r"\[http-flood\]\s+Ban\s+"+re.escape(sys.argv[2])+r"(?:\s|$)",s)))',
            str(position), ip).strip() == 'True'
        problems = list(monitor.problems)
        if not monitor.samples:
            problems.append('no_resource_samples')
        if states() != baseline:
            problems.append('final_health_or_restarts_changed')
        if result['interrupted']:
            problems.append('interrupted')
        if result['http_completed'] != result['expected_responses'] or result['attempted'] != result['http_completed']:
            problems.append('http_or_transport_errors')
        if result['rps_completed'] < rps * .95:
            problems.append('completed_rps_below_95_percent')
        latency = result['http_latency_ms']
        if latency['p95'] is None or latency['p95'] > 250 or latency['p99'] > 500:
            problems.append('latency_threshold_exceeded')
        result.update(service=service, mode=mode,
            protection={'jail_active': True, 'source_temporarily_exempt': capacity,
                        'source_banned': is_banned, 'ban_logged_this_stage': new_ban, 'blocked_packets': packet_count},
            resource_samples=monitor.samples, monitor_problems=monitor.problems,
            stable_without_ban=not problems and not is_banned,
            stability_failures=sorted(set(problems)),
            demonstrated_ban=bool(is_banned and new_ban and packet_count > 0 and monitor.samples and not monitor.problems))
    result['protection_restored'] = not is_ignored(service, ip) and ip not in banned(service)
    return result


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output_dir = ROOT / 'results' / stamp
    output_dir.mkdir(parents=True)
    metadata = {'started_at_utc': now(), 'docker_host': HOST, 'network': NETWORK,
                'protocol_sha256': hashlib.sha256((ROOT / 'PROTOCOL.md').read_bytes()).hexdigest(),
                'client_image': IMAGE, 'stages': [], 'complete': False}
    created = []
    initial = protection()
    metadata['initial_protection'] = initial
    existing = docker('ps', '-a', '--format', '{{.Names}}').splitlines()
    assert CLIENT_A not in existing and CLIENT_B not in existing, 'Existing client names: inspect before reusing'
    docker('image', 'inspect', IMAGE, '--format', '{{.Id}}')  # Never pull/build implicitly.
    metadata['client_image_id'] = docker('image', 'inspect', IMAGE, '--format', '{{.Id}}').strip()
    try:
        for client in (CLIENT_A, CLIENT_B):
            docker('run', '-d', '--name', client, '--network', NETWORK, '--memory', '128m', '--cpus', '.5',
                   '--pids-limit', '32', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                   '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=8m', '--mount',
                   f'type=bind,source={ROOT}/flood.py,target=/work/flood.py,readonly', IMAGE,
                   'python3', '-c', 'import time; time.sleep(1800)')
            created.append(client)
        ips = {client: docker('inspect', client, '--format',
            '{{(index .NetworkSettings.Networks "' + NETWORK + '").IPAddress}}').strip() for client in created}
        assert ips[CLIENT_A] != ips[CLIENT_B]
        metadata['client_ips'] = ips
        print('Client IPs:', ips, flush=True)
        for service in HTTP:
            if STOP.is_set():
                raise InterruptedError('Campaign interrupted')
            assert not is_ignored(service, ips[CLIENT_A]) and ips[CLIENT_A] not in banned(service)
            assert probe(CLIENT_A, service)['status'] == 200 and probe(CLIENT_B, service)['status'] == 200
            logpath = '/opt/keycloak/data/log/keycloak-http-access.log' if service == 'keycloak' else '/var/log/security/access.log'
            observed = execute(service, 'python3', '-c',
                'from pathlib import Path; import sys; print(any(line.startswith(sys.argv[2]+" ") '
                'for line in Path(sys.argv[1]).read_text().splitlines()))', logpath, ips[CLIENT_A])
            assert observed.strip() == 'True', 'Actual socket source IP not found'
            schedule = [(2, 1, 'protected_baseline'), (5, 2, 'capacity'), (10, 3, 'capacity'), (19, 3, 'capacity')]
            best = None
            for rps, workers, mode in schedule:
                result = run_stage(service, rps, workers, mode, ips[CLIENT_A])
                name = f'{service}-{mode}-{rps}.json'
                (output_dir / name).write_text(json.dumps(result, indent=2) + '\n')
                metadata['stages'].append(name)
                (output_dir / 'campaign.json').write_text(json.dumps(metadata, indent=2) + '\n')
                print(service, mode, rps, 'RPS:', result['rps_completed'],
                      'p95:', result['http_latency_ms']['p95'], 'stable:', result['stable_without_ban'], flush=True)
                if not result['stable_without_ban']:
                    if result['monitor_problems'] or STOP.is_set() or best is None:
                        raise RuntimeError('Unsafe/no stable baseline; campaign stopped')
                    print('Escalation stopped; will only repeat the previous stable stage.', flush=True)
                    break
                if mode == 'capacity':
                    best = (rps, workers)
            for mode in ('capacity_repeat', 'protected_comparison'):
                result = run_stage(service, *best, mode, ips[CLIENT_A])
                name = f'{service}-{mode}-{best[0]}.json'
                (output_dir / name).write_text(json.dumps(result, indent=2) + '\n')
                metadata['stages'].append(name)
                print(service, mode, 'RPS:', result['rps_completed'],
                      'stable:', result['stable_without_ban'], 'ban:', result['demonstrated_ban'], flush=True)
                if mode == 'capacity_repeat' and not result['stable_without_ban']:
                    raise RuntimeError('Highest stable stage not confirmed on repeat')
                if mode == 'protected_comparison' and best[0] >= 10 and not result['demonstrated_ban']:
                    raise RuntimeError('Protected comparison not attributable to a verified ban')
            (output_dir / 'campaign.json').write_text(json.dumps(metadata, indent=2) + '\n')
        metadata['complete'] = True
    finally:
        for client in created:
            subprocess.run(DOCKER + ['rm', '-f', client], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        final = protection()
        metadata['final_protection'] = final
        metadata['protection_matches_initial'] = final == initial
        metadata['ended_at_utc'] = now()
        (output_dir / 'campaign.json').write_text(json.dumps(metadata, indent=2) + '\n')
        assert final == initial, 'Protection state differs from baseline'
        print('All four jails active; original ignoreip restored. Results:', output_dir, flush=True)


if __name__ == '__main__':
    with open('/tmp/opencode/games-loadtest.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
