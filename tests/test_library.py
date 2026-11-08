# ---------------------------------------------------------------------------
# test_library.py
# 2026-11-08
# - Hardware-free persistent package, integrity and HTTP permission tests.
# ---------------------------------------------------------------------------
"""Collection imports must never invoke the controller."""

import base64
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from monitor.library import PackageLibrary
from monitor.server import Handler

PROGRAM = b"G21 G90 G94 G54\nG0 Z3\nG0 X0 Y0\nF100\nG1 X1\nM5\nM30"


def package():
    """A small spindle-off program, never sent to a real controller."""
    return {"schemaVersion": 1,
            "project": {"id": "fixture", "name": "Fixture PCB",
                        "revision": "r1", "boardHash": "a" * 64,
                        "side": "B.Cu", "datum": "shared origin"},
            "camConfirmed": True,
            "files": [{"name": "isolation.nc", "kind": "program",
                       "content": base64.b64encode(PROGRAM).decode(),
                       "sha256": hashlib.sha256(PROGRAM).hexdigest()}]}


class LibraryTests(unittest.TestCase):
    """Exercise persistence, atomic rejection and exact-byte identity."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.library = PackageLibrary(Path(self.temp.name) / "library")

    def test_restart_and_duplicate(self):
        first = self.library.import_package(package())
        library = PackageLibrary(self.library.root)
        second = library.import_package(package())
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(library.list()), 1)
        program = library.program(first["package"]["id"], "isolation.nc")
        self.assertEqual(program["content"].encode(), PROGRAM)

    def test_invalid_batch_never_appears(self):
        for field, value in (("name", "../bad.nc"),
                             ("content", "!not-base64!"),
                             ("sha256", "0" * 64)):
            payload = package()
            bad = copy.deepcopy(payload["files"][0])
            bad[field] = value
            payload["files"].append(bad)
            with self.assertRaises(ValueError):
                self.library.import_package(payload)
            self.assertEqual(self.library.list(), [])

    def test_bad_gcode_and_missing_cam_declaration(self):
        payload = package()
        payload["camConfirmed"] = False
        with self.assertRaises(ValueError):
            self.library.import_package(payload)
        payload = package()
        payload["files"][0]["content"] = base64.b64encode(b"M6").decode()
        payload["files"][0]["sha256"] = hashlib.sha256(b"M6").hexdigest()
        with self.assertRaises(ValueError):
            self.library.import_package(payload)

    def test_modified_bytes_and_manifest_are_rejected(self):
        saved = self.library.import_package(package())["package"]
        directory = self.library.root / saved["id"]
        (directory / "isolation.nc").write_bytes(b"M3 S1000")
        with self.assertRaises(ValueError):
            self.library.program(saved["id"], "isolation.nc")
        with self.assertRaises(ValueError):
            self.library.import_package(package())
        filename = directory / "manifest.json"
        manifest = json.loads(filename.read_text())
        manifest["project"]["side"] = "F.Cu"
        filename.write_text(json.dumps(manifest))
        self.assertTrue(self.library.list()[0]["corrupt"])

    def test_cad_is_an_attachment_not_a_program(self):
        payload = package()
        payload["files"][0].update(name="cad.zip", kind="cad")
        payload["camConfirmed"] = False
        saved = self.library.import_package(payload)["package"]
        with self.assertRaisesRegex(ValueError, "CAM"):
            self.library.program(saved["id"], "cad.zip")

    def test_http_separates_import_and_machine_permissions(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.library = self.library
        server.control_token = "operator-fixture"
        server.cnc = Mock()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"

        def request(route, payload=None, integration=False, operator=False):
            headers = {"Content-Type": "application/json", "Origin": base}
            if integration:
                headers["Authorization"] = "Bearer " + "k" * 40
            if operator:
                headers["X-PiloMill-Token"] = server.control_token
            data = None if payload is None else json.dumps(payload).encode()
            try:
                with urlopen(Request(base + route, data, headers)) as response:
                    return response.status, json.load(response)
            except HTTPError as error:
                return error.code, None

        with patch("monitor.library_http.integration_token",
                   return_value="k" * 40):
            self.assertEqual(request("/api/library/packages", package())[0],
                             403)
            status, result = request("/api/library/packages", package(), True)
            self.assertEqual(status, 200)
            server.cnc.action.assert_not_called()
            self.assertEqual(request("/api/library", integration=True)[0], 403)
            self.assertEqual(request("/api/cnc/action",
                                     {"action": "job_start"}, True)[0], 403)
            self.assertEqual(request("/api/library", operator=True)[0], 200)
            choice = {"packageId": result["package"]["id"],
                      "name": "isolation.nc"}
            self.assertEqual(request("/api/library/select", choice,
                                     operator=True)[0], 200)
            server.cnc.action.assert_called_once_with(
                "job_load", {"name": "isolation.nc",
                             "content": PROGRAM.decode()})
            server.cnc.action.side_effect = ValueError("Aktywne zadanie")
            self.assertEqual(request("/api/library/select", choice,
                                     operator=True)[0], 400)


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
