#!/usr/bin/env python3
"""No HTTP load: verify runtime exception cleanup and orphan watchdog restoration.

Uses an unused TEST-NET address, never exempts a real client. All jails stay active.
"""
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time

import run_campaign as campaign

IP = '192.0.2.254'
SERVICE = 'frontend'
output = Path(sys.argv[1]).resolve()
assert output.is_dir()
report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'http_requests_sent': 0,
          'control_only_test_net_ip': IP}

with open('/tmp/opencode/games-loadtest.lock', 'w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    before = campaign.protection()
    assert not campaign.is_ignored(SERVICE, IP) and IP not in campaign.banned(SERVICE)
    try:
        try:
            with campaign.stage_guard(SERVICE, IP, True):
                assert campaign.is_ignored(SERVICE, IP)
                raise RuntimeError('Deliberate control-path exception; no HTTP load')
        except RuntimeError:
            pass
        assert not campaign.is_ignored(SERVICE, IP)
        report['exception_finally_restored'] = True
        print('PASS: runtime exception restores the temporary exception.', flush=True)

        code = """import time
import run_campaign as c
with c.stage_guard('frontend','192.0.2.254',True):
 print('READY',flush=True)
 time.sleep(60)
"""
        child = subprocess.Popen([sys.executable, '-c', code], cwd=campaign.ROOT,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert child.stdout.readline().strip() == 'READY'
            assert campaign.is_ignored(SERVICE, IP)
            child.kill()  # SIGKILL cannot execute host finally; the in-container lease must expire.
            child.wait(timeout=3)
            started = time.monotonic()
            while campaign.is_ignored(SERVICE, IP) and time.monotonic() - started < 35:
                time.sleep(.5)
            assert not campaign.is_ignored(SERVICE, IP), 'Orphan watchdog failed to restore'
            report['sigkill_watchdog_restored'] = True
            report['watchdog_observed_after_sigkill_s'] = round(time.monotonic() - started, 3)
            print('PASS: watchdog restores after controller SIGKILL.', flush=True)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
    finally:
        campaign.release(SERVICE, IP)
        after = campaign.protection()
        report['all_jails_active'] = all(value['active'] for value in after.values())
        report['protection_matches_initial'] = after == before
        (output / 'restoration-checks.json').write_text(json.dumps(report, indent=2) + '\n')
        assert after == before
