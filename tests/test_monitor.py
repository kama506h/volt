import http.client
import threading
import unittest
from http.server import ThreadingHTTPServer
from volt.collector import Collector, rates
from volt.__main__ import handler_for

class MonitorTests(unittest.TestCase):
    def test_rates_reset(self):
        self.assertEqual(rates((100, 200), (300, 100), 2), [100, 0])

    def test_snapshot(self):
        c = Collector()
        c.sample()
        d = c.snapshot()
        self.assertGreater(d['memory_total'], 0)
        self.assertTrue(0 <= d['cpu'] <= 100)
        d['history'].clear()
        self.assertEqual(len(c.snapshot()['history']), 1)
        self.assertEqual(c.history.maxlen, 120)

    def test_http(self):
        c = Collector()
        c.sample()
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(c))
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            for path, host, expected in [('/', 'localhost', 200), ('/api/stats', 'localhost', 200), ('/app.js', 'localhost', 200), ('/../collector.py', 'localhost', 404), ('/api/stats', 'evil.example', 403)]:
                with self.subTest(path=path, host=host):
                    conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
                    conn.request('GET', path, headers={'Host': host})
                    r = conn.getresponse()
                    self.assertEqual(r.status, expected)
                    r.read()
                    conn.close()
        finally:
            server.shutdown()
            server.server_close()
            t.join()
