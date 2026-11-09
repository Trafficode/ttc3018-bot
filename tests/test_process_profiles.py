# ---------------------------------------------------------------------------
# test_process_profiles.py
# 2026-11-09
# - Saved recipes, fixed tool parameters, stock overrides and revision guards.
# ---------------------------------------------------------------------------
"""Temporary files and fake calibration data only; no device access."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from http.server import ThreadingHTTPServer
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from monitor.process_profiles import ProcessProfiles
from monitor.cnc import Controller
from monitor.jobs import parse_program
from monitor.pcb_progress import PcbProgress
from monitor.server import Handler
from test_cam import profile
from test_pcb_flow import settings


class RecipeTests(unittest.TestCase):
    """Inputs are reviewed once, material thickness is always job-specific."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "profiles.json"
        self.store = ProcessProfiles(self.path)
        self.values = settings()
        self.values.pop("thicknessMm")
        self.values.pop("confirmedSetup")
        self.values["clearanceMm"] = 3

    def save(self, **extra):
        return self.store.save({"name": "Fixture recipe",
                                "values": self.values,
                                "confirmedTools": True, **extra}, profile())

    def test_persistence_and_immutable_binding(self):
        saved = self.save()
        restored = ProcessProfiles(self.path)
        self.assertEqual(restored.get(saved["id"]), saved)
        self.assertNotIn("thicknessMm", saved["values"])
        self.assertEqual(saved["isolation"]["fingerprint"],
                         profile()["fingerprint"])

    def test_resolve_only_stock_changes_not_hidden_feed_overrides(self):
        saved = self.save()
        recipe, flow, clearance = self.store.resolve({
            "processProfileId": saved["id"],
            "processFingerprint": saved["fingerprint"],
            "confirmedSetup": True,
            "material": {"thicknessMm": 1, "skinMm": .15,
                         "millFeed": 299, "clearanceMm": 1}}, profile())
        self.assertEqual(flow["thicknessMm"], 1)
        self.assertEqual(flow["skinMm"], .15)
        self.assertEqual(flow["millFeed"], self.values["millFeed"])
        self.assertEqual(clearance, 3)
        self.assertEqual(recipe, saved)

    def test_stock_thickness_cannot_be_omitted(self):
        saved = self.save()
        with self.assertRaises(ValueError):
            self.store.resolve({"processProfileId": saved["id"],
                                "processFingerprint": saved["fingerprint"],
                                "confirmedSetup": True, "material": {}},
                               profile())

    def test_changed_recipe_and_changed_calibration_are_rejected(self):
        saved = self.save()
        self.values["millFeed"] = 70
        updated = self.save(id=saved["id"],
                            expectedFingerprint=saved["fingerprint"])
        self.assertEqual(updated["revision"], 2)
        with self.assertRaises(ValueError):
            self.store.assert_snapshot(saved)
        with self.assertRaises(ValueError):
            self.save(id=saved["id"],
                      expectedFingerprint=saved["fingerprint"])
        changed = {**profile(), "fingerprint": "b" * 64}
        with self.assertRaises(ValueError):
            self.store.resolve({"processProfileId": updated["id"],
                                "processFingerprint": updated["fingerprint"],
                                "material": {"thicknessMm": 1},
                                "confirmedSetup": True}, changed)

    def test_unsafe_and_unreviewed_recipe_never_saved(self):
        for key, value in (("millPower", 1001), ("millFeed", True),
                           ("backingMm", 0)):
            with self.assertRaises(ValueError):
                self.store.save({"name": "bad", "confirmedTools": True,
                                 "values": {**self.values, key: value}},
                                profile())
        with self.assertRaises(ValueError):
            self.store.save({"name": "unreviewed", "values": self.values},
                            profile())
        self.assertFalse(self.path.exists())

    def test_changed_recipe_blocks_stage_load_and_start_before_serial(self):
        saved = self.save()
        self.values["millFeed"] = 70
        self.save(id=saved["id"], expectedFingerprint=saved["fingerprint"])
        cnc = Controller()
        cnc.port = Mock()
        cnc.jobs.load(parse_program("fixture.nc", (
            "G21 G90 G94 G54\nG0 Z3\nG0 X0 Y0\n"
            "G1 Z-0.8 F5\nG1 X1 F60\nG0 Z3\nM5\nM30")))
        cnc.process_profiles = self.store
        cnc.jobs.program["pcb_flow"] = {"processProfile": saved}
        with self.assertRaisesRegex(ValueError, "oblicz PCB ponownie"):
            cnc.action("job_start", {
                "job_id": cnc.jobs.job_id, "confirmed": True})
        cnc.port.write.assert_not_called()
        collection = Mock()
        collection.lock = threading.RLock()
        collection.get.return_value = {"processProfile": saved}
        with self.assertRaisesRegex(ValueError, "oblicz PCB ponownie"):
            PcbProgress(collection, self.store).load("fixture", {}, cnc)
        collection.program.assert_not_called()
        cnc.port.write.assert_not_called()

    def test_corrupt_file_not_overwritten(self):
        self.path.write_text("broken")
        store = ProcessProfiles(self.path)
        self.assertTrue(store.status()["error"])
        with self.assertRaises(ValueError):
            store.save({"name": "new", "values": self.values,
                        "confirmedTools": True}, profile())
        self.assertEqual(self.path.read_text(), "broken")

    def test_http_import_token_cannot_edit_and_saves_do_not_control_cnc(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.control_token = "fixture-token"
        server.process_profiles = self.store
        server.cnc = Mock()
        server.cnc.lock = threading.RLock()
        server.cnc.status.return_value = {
            "job": {"state": "empty"},
            "calibration_profiles": {"selected": profile(),
                                     "profiles": [profile()]}}
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"

        def request(route, payload=None, operator=True, origin=base):
            headers = {"Origin": origin, "Content-Type": "application/json",
                       "Authorization": "Bearer " + "k" * 40}
            if operator:
                headers["X-PiloMill-Token"] = server.control_token
            body = None if payload is None else json.dumps(payload).encode()
            try:
                with urlopen(Request(base + route, body, headers)) as response:
                    return response.status, json.load(response)
            except HTTPError as error:
                error.close()
                return error.code, None

        payload = {"name": "Fixture", "values": self.values,
                   "confirmedTools": True}
        self.assertEqual(request("/api/pcb-profiles/save", payload,
                                 operator=False)[0], 403)
        self.assertEqual(request("/api/pcb-profiles/save", payload,
                                 origin="http://foreign")[0], 400)
        code, saved = request("/api/pcb-profiles/save", payload)
        self.assertEqual(code, 200)
        server.cnc.action.assert_not_called()
        self.assertEqual(request("/api/pcb-profiles/select", {
            "id": saved["id"], "fingerprint": saved["fingerprint"]})[0], 200)
        server.cnc.action.assert_called_once_with("profile_select", {
            "profile_id": profile()["id"]})
        server.cnc.action.reset_mock()
        server.cnc.status.return_value["job"]["state"] = "running"
        self.assertEqual(request("/api/pcb-profiles/save", payload)[0], 400)
        self.assertEqual(len(self.store.status()["profiles"]), 1)
        server.cnc.action.assert_not_called()


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
