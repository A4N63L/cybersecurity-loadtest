"""Local-only transport checks; no laboratory load or sensitive responses."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest

import flood


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/slow':
            time.sleep(.2)
        self.send_response(418 if self.path == '/error' else 200)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, *args):
        pass


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def config(self, path='/'):
        return flood.arguments(['127.0.0.1', str(self.server.server_port), '--path', path,
                                '--timeout', '.05', '--duration', '1', '--rps', '4', '--concurrency', '4'])

    def test_http_error_is_not_network_failure(self):
        self.assertEqual(flood.request(self.config('/error'))[:2], ('http', '418'))

    def test_timeout_and_connection_failure_separate(self):
        self.assertEqual(flood.request(self.config('/slow'))[:2], ('timeout', 'timeout'))
        with socket.socket() as unused:
            unused.bind(('127.0.0.1', 0))
            config = self.config()
            config.port = unused.getsockname()[1]
            self.assertEqual(flood.request(config)[:2], ('connection_error', 'refused'))

    def test_shared_budget_not_multiplied_by_workers(self):
        result = flood.run(self.config())
        self.assertEqual(result['http_completed'], 4)
        self.assertLessEqual(result['rps_attempted'], 4.05)

    def test_sigterm_returns_partial_sanitized_json(self):
        import json
        process = subprocess.Popen([sys.executable, flood.__file__, '127.0.0.1',
            str(self.server.server_port), '--duration', '10', '--rps', '2'], stdout=subprocess.PIPE, text=True)
        time.sleep(.4)
        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=3)
        self.assertEqual(process.returncode, 130)
        self.assertTrue(json.loads(output)['interrupted'])


if __name__ == '__main__':
    unittest.main()
