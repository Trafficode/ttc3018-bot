# ---------------------------------------------------------------------------
# test_cam.py
# 2026-11-08
# - Real Gerber fixtures, independent sweep rejection and collection contracts.
# ---------------------------------------------------------------------------
"""All tests are offline and never construct a serial controller."""

import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile
from http.server import ThreadingHTTPServer
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from monitor.cam import CamCollection, write_json
from monitor.library import PackageLibrary, digest
from monitor.profiles import fingerprint
from monitor.server import Handler

try:
    from monitor.cam_geometry import (
        contour_paths, emit_program, generate, read_copper,
        transform_geometry, verify_sweep)
    from shapely.geometry import box
    GEOMETRY = True
except ImportError:
    GEOMETRY = False


def profile():
    """A fixed calibrated width, separate from nominal tip geometry."""
    result = {"id": "1234567890abcdef", "name": "Measured fixture",
              "depth": .08, "model": {"intercept_mm": .3, "slope": .5,
                                       "min_depth": .01, "max_depth": .3},
              "conditions": {"tip": .1, "angle": 30, "feed": 60,
                             "plunge": 5, "power": 1000}}
    result["fingerprint"] = fingerprint(result)
    return result


def gerber(regions):
    """Real RS-274-X regions; input coordinates are millimetres."""
    lines = ["%FSLAX46Y46*%", "%MOMM*%", "%LPD*%", "G01*"]
    for points in regions:
        lines.append("G36*")
        for index, (x, y) in enumerate(points):
            lines.append(f"X{round(x * 1e6)}Y{round(y * 1e6)}"
                         f"D{'02' if index == 0 else '01'}*")
        lines.append("G37*")
    return ("\n".join(lines) + "\nM02*\n").encode()


def archive(gap=2):
    """Two known rectangular copper lands, with a variable gap."""
    first = [(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)]
    x = 4 + gap
    second = [(x, 2), (x+2, 2), (x+2, 4), (x, 4), (x, 2)]
    outline = ("%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n"
               "%ADD10C,0.05*%\nD10*\nG01*\nX0Y0D02*\n"
               "X20000000Y0D01*\nX20000000Y20000000D01*\n"
               "X0Y20000000D01*\nX0Y0D01*\nM02*\n")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as result:
        result.writestr("fixture-F_Cu.gtl", gerber([first, second]))
        result.writestr("fixture-B_Cu.gbl", gerber([first, second]))
        result.writestr("fixture-Edge_Cuts.gm1", outline)
        result.writestr("copper-plan.json", json.dumps({
            "sourceHash": "a" * 64, "settings": {"layer": "B.Cu"}}))
        result.writestr("validation.json", '{"issues":0,"findings":[]}')
        result.writestr("copper-readback.json", '{"findings":[]}')
    return output.getvalue()


def package(data):
    """Collection payload with the exact shared datum declared by Tractor."""
    return {"schemaVersion": 1, "camConfirmed": False,
            "project": {"id": "fixture", "name": "Fixture PCB",
                        "revision": "fixture", "boardHash": "a" * 64,
                        "side": "B.Cu", "datum": "KiCad absolute board "
                        "datum; shared copper, drills and outline"},
            "files": [{"kind": "cad", "name": "cad.zip",
                       "content": base64.b64encode(data).decode(),
                       "sha256": digest(data)}]}


@unittest.skipUnless(GEOMETRY, "Install requirements-cam.txt for geometry")
class GeometryTests(unittest.TestCase):
    """Exercise real parser offsets and independent emitted-path checks."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.project = package(archive())["project"]

    def test_real_gerber_generates_calibrated_linear_program(self):
        report, preview, content = generate(
            archive(), self.project, profile(), 3, self.directory)
        self.assertTrue(report["checks"]["passed"])
        self.assertEqual(report["checks"]["protectedIslands"], 2)
        self.assertAlmostEqual(report["diameterMm"], .34)
        self.assertTrue(content.startswith("; BARK_BEETLE_PROFILE"))
        self.assertIn("G1 Z-0.08000 F5", content)
        self.assertIn("M3 S1000", content)
        self.assertEqual(preview["bounds"], [0, 0, 20, 20])
        self.assertEqual(report["operations"]["drilling"], "not_prepared")

    def test_too_narrow_gap_returns_location_and_no_program(self):
        report, preview, content = generate(
            archive(.1), self.project, profile(), 3, self.directory)
        self.assertFalse(report["checks"]["passed"])
        self.assertIsNone(content)
        self.assertTrue(all("x" in value and "y" in value
                            for value in report["checks"]["findings"]))
        self.assertTrue(preview["paths"])

    def test_sweep_detects_tampered_nc_crossing_a_land(self):
        copper = box(2, 2, 4, 4).union(box(7, 2, 9, 4))
        paths = contour_paths(copper, .34)
        paths.append([[1, 3], [10, 3]])
        content, program = emit_program(paths, profile(), 3)
        report = verify_sweep(copper, box(0, 0, 20, 20), program, .34)
        self.assertFalse(report["passed"])
        self.assertGreater(report["copperLossMm2"], 1)

    def test_common_origin_mirror_is_not_individual_centering(self):
        copper, stock, transform = transform_geometry(
            box(12, -18, 14, -16), box(10, -20, 30, 0), "B.Cu")
        self.assertEqual(copper.bounds, (16, 2, 18, 4))
        self.assertEqual(stock.bounds, (0, 0, 20, 20))
        self.assertEqual(transform["matrix"], [-1, 0, 0, 1, 30, 20])

    def test_clear_polarity_survives_readback(self):
        outer = gerber([[(1, 1), (9, 1), (9, 9), (1, 9), (1, 1)]])
        inner = gerber([[(3, 3), (7, 3), (7, 7), (3, 7), (3, 3)]])
        data = outer.replace(b"M02*", b"%LPC*%\n" + inner.split(
            b"G01*\n", 1)[1])
        filename = self.directory / "polarity.gbr"
        filename.write_bytes(data)
        copper = read_copper(filename)
        self.assertAlmostEqual(copper.area, 48)
        self.assertEqual(len(copper.interiors), 1)

    def test_source_binding_and_archive_paths_fail_closed(self):
        project = {**self.project, "boardHash": "b" * 64}
        with self.assertRaisesRegex(ValueError, "PCB"):
            generate(archive(), project, profile(), 3, self.directory)
        output = io.BytesIO(archive())
        with zipfile.ZipFile(output, "a") as result:
            result.writestr("../escape", "no")
        with self.assertRaisesRegex(ValueError, "ścieżka"):
            generate(output.getvalue(), self.project, profile(), 3,
                     self.directory)


class CollectionTests(unittest.TestCase):
    """Persistence and stale-result checks without a running subprocess."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.library = PackageLibrary(root / "library")
        self.source = self.library.import_package(package(archive()))["package"]
        self.cam = CamCollection(root / "cam", self.library)
        self.payload = {"packageId": self.source["id"], "name": "cad.zip",
                        "clearanceMm": 3, "confirmedDatum": True,
                        "profileFingerprint": profile()["fingerprint"]}

    def test_inputs_captured_and_single_worker(self):
        with patch("monitor.cam.threading.Thread") as worker:
            item = self.cam.start(self.payload, profile())
            worker.return_value.start.assert_called_once()
            self.assertEqual(self.library.list(), [self.source])
            self.assertEqual(item["profile"], profile())
            with self.assertRaises(RuntimeError):
                self.cam.start(self.payload, profile())

    def test_profile_and_datum_confirmation_required(self):
        for field, value in (("profileFingerprint", "wrong"),
                             ("confirmedDatum", False),
                             ("clearanceMm", float("nan"))):
            with self.assertRaises(ValueError):
                self.cam.start({**self.payload, field: value}, profile())
        self.assertEqual(self.cam.list(profile()), [])

    def test_restart_marks_interrupted_and_retains_source(self):
        with patch("monitor.cam.threading.Thread"):
            item = self.cam.start(self.payload, profile())
        with patch("monitor.cam.CamCollection._stop_unit") as stop:
            restored = CamCollection(self.cam.root, self.library)
        stop.assert_called_once_with(item["unit"])
        self.assertEqual(restored.get(item["id"])["state"], "interrupted")
        self.assertEqual(self.library.list(), [self.source])

    def test_stale_and_blocked_results_cannot_load(self):
        with patch("monitor.cam.threading.Thread"):
            item = self.cam.start(self.payload, profile())
        item.update(state="failed")
        write_json(self.cam.directory(item["id"]) / "manifest.json", item)
        changed = copy.deepcopy(profile())
        changed["fingerprint"] = "b" * 64
        self.assertTrue(self.cam.list(changed)[0]["stale"])
        with self.assertRaises(ValueError):
            self.cam.program(item["id"], profile())

    def test_finalized_metadata_without_integrity_is_rejected(self):
        with patch("monitor.cam.threading.Thread"):
            item = self.cam.start(self.payload, profile())
        item["state"] = "ready"
        write_json(self.cam.directory(item["id"]) / "manifest.json", item)
        with self.assertRaisesRegex(ValueError, "integralności"):
            self.cam.get(item["id"])

    def test_http_permissions_idle_gate_and_explicit_load(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.cam = Mock()
        server.control_token = "operator-fixture"
        server.cnc = Mock()
        server.cnc.status.return_value = {
            "connected": False, "job": {"state": "empty"},
            "calibration_profiles": {"selected": profile()}}
        server.cam.start.return_value = {"id": "c" * 64, "state": "running"}
        server.cam.program.return_value = {"name": "isolation.nc",
                                           "content": "fixture"}
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"

        def request(route, operator=True, origin=base):
            headers = {"Content-Type": "application/json", "Origin": origin,
                       "Authorization": "Bearer " + "k" * 40}
            if operator:
                headers["X-PiloMill-Token"] = server.control_token
            data = json.dumps(self.payload).encode()
            try:
                with urlopen(Request(base + route, data, headers)) as response:
                    return response.status
            except HTTPError as error:
                error.close()
                return error.code

        self.assertEqual(request("/api/cam/prepare", False), 403)
        self.assertEqual(request("/api/cam/prepare", origin="http://other"),
                         400)
        server.cam.start.assert_not_called()
        self.assertEqual(request("/api/cam/prepare"), 202)
        server.cnc.action.assert_not_called()
        server.cnc.status.return_value["connected"] = True
        self.assertEqual(request("/api/cam/prepare"), 409)
        self.assertEqual(request("/api/cam/select"), 200)
        server.cnc.action.assert_called_once_with("job_load", {
            "name": "isolation.nc", "content": "fixture"})


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
