# ---------------------------------------------------------------------------
# test_pwa_assets.py
# 2026-11-08
# - Check real manifest/icon routes without creating a CNC controller.
# ---------------------------------------------------------------------------
"""Validate install metadata and non-cacheable HTTP endpoints locally."""

from http.server import ThreadingHTTPServer
import json
import struct
import threading
import unittest
from urllib.request import urlopen

from monitor.server import Handler


class PwaAssets(unittest.TestCase):
    """Serve only static routes using the real HTTP handler."""

    def test_manifest_and_icon_dimensions(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        with urlopen(base + '/manifest.webmanifest') as response:
            self.assertEqual(response.headers['Content-Type'],
                             'application/manifest+json')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            manifest = json.load(response)
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['id'], '/')
        self.assertEqual(manifest['scope'], '/')
        for icon in manifest['icons']:
            with urlopen(base + icon['src']) as response:
                png = response.read()
            self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
            wanted = tuple(map(int, icon['sizes'].split('x')))
            self.assertEqual(struct.unpack('>II', png[16:24]), wanted)
        with urlopen(base + '/sw.js') as response:
            self.assertEqual(response.headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
