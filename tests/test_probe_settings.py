import json
import unittest
from unittest.mock import patch

from controller_fixture import Controller
from monitor.probe_settings import ProbeSettings
from test_probes import Port


class ProbeSettingsTests(unittest.TestCase):
    def setUp(self):
        self.cnc = Controller()
        self.path = self.cnc.probe_settings.path

    def save(self, distance=2.5, feed=150, **extra):
        settings = self.cnc.probe_settings.status()
        return self.cnc.action("probe_settings_save", {
            "revision": settings["revision"], "max_descent_mm": distance,
            "xy_feed_mm_min": feed, **extra,
        })

    def connect_fake(self):
        self.cnc.port = Port()
        self.cnc.info = ["$6=1", "$13=0"]
        self.cnc._accept_status("<Idle|MPos:0,0,6|WCO:0,0,5|Pn:P>")
        self.cnc._accept_status("<Idle|MPos:0,0,6|WCO:0,0,5>")

    def test_settings_persist_and_stale_edit_does_not_overwrite(self):
        original = self.cnc.status()["probe_settings"]
        saved = self.save(travel_clearance_mm=4.5, z_feed_mm_min=35)
        self.assertEqual(saved["travel_clearance_mm"], 4.5)
        self.assertEqual(saved["z_feed_mm_min"], 35)
        self.assertNotEqual(original["revision"], saved["revision"])
        self.assertEqual(ProbeSettings(self.path).status(), saved)
        self.assertEqual(self.cnc.status()["probe_settings"], saved)
        with self.assertRaisesRegex(ValueError, "innym oknie"):
            self.save(distance=4, revision=original["revision"])
        self.assertEqual(ProbeSettings(self.path).status(), saved)

    def test_legacy_settings_keep_values_and_receive_new_defaults(self):
        self.path.write_text(json.dumps({
            "version": 1, "max_descent_mm": 2.5, "xy_feed_mm_min": 80,
        }), encoding="utf-8")
        old = self.path.read_bytes()
        values = ProbeSettings(self.path).status()
        self.assertEqual(values["max_descent_mm"], 2.5)
        self.assertEqual(values["xy_feed_mm_min"], 80)
        self.assertEqual(values["travel_clearance_mm"], 3)
        self.assertEqual(values["z_feed_mm_min"], 20)
        self.assertEqual(self.path.read_bytes(), old)

    def test_out_of_range_and_corrupt_settings_block_motion_until_corrected(self):
        for distance, feed in ((0, 100), (10.1, 100), (True, 100),
                               (float("nan"), 100), (2, 301), (2, 24), (2, True)):
            with self.subTest(distance=distance, feed=feed), self.assertRaises(ValueError):
                self.save(distance, feed)
        for limits in ({"travel_clearance_mm": .99}, {"travel_clearance_mm": 10.01},
                       {"z_feed_mm_min": 9}, {"z_feed_mm_min": 61}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                self.save(**limits)
        self.path.write_text("broken json", encoding="utf-8")
        self.cnc.probe_settings = ProbeSettings(self.path)
        self.assertTrue(self.cnc.status()["probe_settings"]["error"])
        self.connect_fake()
        with self.assertRaisesRegex(ValueError, "Zapisz poprawne ustawienia"):
            self.cnc.action("probe_start", {
                "confirmed": True, "distance": 1, "feed": 20, "position": [0, 0, 1],
            })
        self.assertFalse(self.cnc.port.writes)
        self.assertIsNone(self.save()["error"])

    def test_reference_uses_lower_limit_and_rejects_stale_probe_approval(self):
        self.connect_fake()
        old = self.cnc.probe_settings.status()
        saved = self.save(distance=2.4, z_feed_mm_min=35)
        payload = {"confirmed": True, "distance": 10, "feed": 20,
                   "position": [0, 0, 1], "probe_settings_revision": old["revision"]}
        self.assertFalse(self.cnc.port.writes)
        with self.assertRaisesRegex(ValueError, "potwierdź ponownie"):
            self.cnc.action("probe_start", payload)
        self.assertFalse(self.cnc.port.writes)
        with patch.object(self.cnc, "_status"), patch.object(
            self.cnc, "_line", return_value=["[GC:G54 G21 G90 G94 M5]"]
        ):
            self.cnc.action("probe_start", {**payload, "probe_settings_revision": saved["revision"]})
        self.assertEqual(self.cnc.probe.command, "G90G38.2Z-1.4000F35")
        self.assertAlmostEqual(self.cnc.probe.attempt["distanceMm"], 2.4)
        with self.assertRaisesRegex(ValueError, "Sondowanie aktywne"):
            self.save(distance=3)

    def test_save_during_reserved_project_is_rejected_without_serial_writes(self):
        self.connect_fake()
        self.cnc.project_cycle.reserve("project", "isolation", "datum", [0, 0, 1])
        with self.assertRaises(ValueError):
            self.save()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.cnc.port.writes)
