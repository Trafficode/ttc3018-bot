# ---------------------------------------------------------------------------
# test_profile_test.py
# 2026-10-24
# - Exact coupon geometry, immutable depth and simulated nine-point execution.
# ---------------------------------------------------------------------------
"""All probing and cutting use fake serial replies; never real hardware."""

import math
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from monitor.calibration import Calibration
from monitor.cnc import Controller
from monitor.compensation import height_at
from monitor.jobs import WORD
from monitor.profile_test import configuration, layout, program
from monitor.profiles import check_cam_program
from test_probes import Port


MODAL = ["[GC:G0 G54 G21 G90 G94 M5]"]
OFFSET = ["[G54:10,20,5]", "[G92:0,0,0]", "[TLO:0]"]


class ProfileTestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cnc = Controller()
        self.cnc.calibration = Calibration(Path(self.directory.name)/"p.json")
        self.store = self.cnc.calibration.profiles
        self.cnc.port = Port()
        self.cnc.info = ["$6=1", "$13=0"]
        self.cnc._accept_status("<Idle|MPos:12,23,6|WCO:10,20,5|Pn:P>")
        self.cnc._accept_status("<Idle|MPos:12,23,6|WCO:10,20,5>")

    def payload(self, **extra):
        active = self.store.active
        return {"profile_id": active["id"],
                "profile_fingerprint": active["fingerprint"],
                "confirmed": True, "position": self.cnc.report["position"][:],
                "session": self.cnc.calibration.session, **extra}

    def action(self, name, payload):
        with patch.object(self.cnc, "_status"), patch.object(
            self.cnc, "_line",
            side_effect=lambda c: OFFSET if c == "$#" else MODAL
        ):
            return self.cnc.action(name, payload)

    def receive(self, text):
        self.cnc.port.receive += text.encode()
        self.cnc.last_probe.tick(self.cnc)

    def complete(self):
        self.action("profile_test_prepare", self.payload(new_session=True))
        scan = self.cnc.calibration.scan
        self.receive("ok\n<Idle|MPos:12,23,6|WCO:10,20,5>\n")
        for point in scan.points:
            x, y = point["x"], point["y"]
            self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},6>\n")
            z = 5 + .001*(x-2)+.002*(y-3)
            self.receive(f"[PRB:{x+10},{y+20},{z}:1]\nok\n"
                         f"<Idle|MPos:{x+10},{y+20},{z-.002}|Pn:P>\n")
            self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},6>\n")
        return scan

    def test_nominal_copper_and_actual_sweep_fit_the_probe_area(self):
        config = configuration(self.store)
        for tip in (.1, .3, .5):
            config["tip"] = tip
            plan = layout(config)
            self.assertEqual([s["width"] for s in plan["shapes"][:3]],
                             [.3, .5, 1])
            r = plan["diameter"]/2
            points = [p for s in plan["shapes"] for p in s["path"]]
            self.assertAlmostEqual(min(p[0] for p in points)-r, 1)
            self.assertAlmostEqual(min(p[1] for p in points)-r, 1)
            self.assertAlmostEqual(plan["width"]-max(p[0] for p in points)-r, 1)
            self.assertAlmostEqual(plan["height"]-max(p[1] for p in points)-r, 1)
            self.assertLess(plan["height"], plan["width"])
            for shape in plan["shapes"]:
                for x, y in shape["path"]:
                    self.assertGreaterEqual(x-r, 0)
                    self.assertGreaterEqual(y-r, 0)
                    self.assertLessEqual(x+r, plan["width"])
                    self.assertLessEqual(y+r, plan["height"])
                points = shape["copper"]
                if shape["kind"] == "strip":
                    self.assertAlmostEqual(points[1][0]-points[0][0], 10)
                    self.assertAlmostEqual(points[2][1]-points[0][1],
                                           shape["width"])
                    path = shape["path"]
                    self.assertAlmostEqual(path[2][1]-path[0][1]-2*r,
                                           shape["width"])
                else:
                    self.assertAlmostEqual(math.dist(points[0], points[4]),
                                           shape["diameter"])
            codes = [p["code"] for p in program([2,3],config)["lines"]]
            self.assertFalse(any("G2" in c and "G21" not in c for c in codes))
            self.assertEqual(sum(c.startswith("G1Z") for c in codes), 5)

    def test_nine_touches_preserve_zero_then_require_separate_cut(self):
        scan = self.complete()
        self.assertTrue(scan.valid)
        self.assertEqual(scan.kind, "profile_test")
        self.assertEqual(len(scan.samples), 9)
        self.assertEqual((scan.columns, scan.rows), (3,3))
        self.assertEqual(scan.offset, [10,20,5])
        self.assertFalse(any(b"G10" in c or b"M3" in c
                             for c in self.cnc.port.writes))
        self.assertEqual(sum(b"G90G38.2Z-0.4000F20" in c
                             for c in self.cnc.port.writes), 9)
        with self.assertRaises(ValueError):
            self.action("profile_test_cut",self.payload(map_id=scan.map_id))
        self.action("profile_test_cut",self.payload(map_id=scan.map_id,
                                                   clip_removed=True))
        runner = self.cnc.calibration.runner
        self.assertTrue(runner.active())
        self.assertTrue(runner.program["compensated"])
        self.assertFalse(scan.valid)
        self.assertEqual(self.cnc.offset,[10,20,5])

    def test_profile_parameters_are_fixed_and_versions_preserve_old_ids(self):
        old = self.store.create({"source":"manual", "name":"A",
            "tip":.1,"angle":30,"feed":100,"plunge":20,"power":300,
            "depth":.1,"samples":[{"depth":.05,"width":.7,
                                    "measured_width":.5}]})
        self.store.select(old["id"])
        self.assertEqual(configuration(self.store)["depth"],.1)
        with self.assertRaises(ValueError):
            configuration(self.store,self.payload(depth=.2))
        generated = program([2,3],configuration(self.store))
        generated["cam_profile"] = {"id":old["id"],
                                    "fingerprint":old["fingerprint"]}
        check_cam_program(old,generated,{})
        wrong = program([2,3],{**configuration(self.store),"depth":.05})
        wrong["cam_profile"] = generated["cam_profile"]
        with self.assertRaises(ValueError):
            check_cam_program(old,wrong,{})
        new = self.store.create({"source":"manual", "name":"B",
            **old["conditions"], "depth":.15,"revision_of":old["id"],
            "samples":[{"depth":.05,"width":.7,"measured_width":.5}]})
        self.assertNotEqual(old["fingerprint"],new["fingerprint"])
        self.assertEqual(self.store.data["profiles"][0],old)
        self.assertEqual(new["revision_of"],old["id"])

    def test_wrong_mode_and_parameter_override_cannot_start_a_cut(self):
        self.complete()
        with self.assertRaises(ValueError):
            self.action("service_cut", self.payload(clip_removed=True))
        with self.assertRaises(ValueError):
            self.action("profile_test_cut",self.payload(
                map_id=self.cnc.calibration.scan.map_id,
                clip_removed=True,feed=75))
        self.assertFalse(self.cnc.calibration.runner.active())

    def cut_completed(self):
        scan = self.complete()
        self.action("profile_test_cut", self.payload(
            map_id=scan.map_id, clip_removed=True))
        self.cnc.calibration.runner.state = "completed"
        self.cnc.calibration.observe()
        return self.cnc.calibration

    def test_local_fast_approach_and_full_xy_clearance(self):
        service = self.cut_completed()
        previous = None
        approaches = []
        high = 2 + max(p["z"] for p in service.scan.samples)
        for line in service.runner.program["lines"]:
            values = {key:float(value) for key,value in WORD.findall(line["code"])}
            if values.get("G") == 0 and "X" in values:
                self.assertAlmostEqual(values["Z"],high,places=3)
            if values.get("G") == 1 and values.get("F") == 20:
                local = height_at(service.scan,values["X"],values["Y"])
                self.assertEqual(set(previous),{"G","Z"})
                self.assertAlmostEqual(previous["Z"]-local,.5,places=3)
                self.assertAlmostEqual(values["Z"]-local,-.05,places=3)
                approaches.append(previous["Z"])
            previous = values
        self.assertEqual(len(approaches),5)
        self.assertGreater(max(approaches)-min(approaches),.001)

    def test_finish_reuses_exact_program_and_records_no_new_sample(self):
        service = self.cut_completed()
        saved = copy.deepcopy(service.runner.program)
        self.assertTrue(service.repeat_status()["available"])
        self.assertEqual(service.repeat_status()["passes"],1)
        payload = self.payload(repeat_id=service.repeat_status()["id"],
                               setup_unchanged=True,clip_removed=True)
        with patch("monitor.calibration.compensate_program",
                   side_effect=AssertionError("Must not compensate twice")):
            self.action("profile_test_finish",payload)
        self.assertEqual(service.runner.program,saved)
        self.assertFalse(service.repeat_status()["available"])
        service.runner.state = "completed"
        service.observe()
        self.assertEqual(service.repeat_status()["passes"],2)
        self.assertEqual(len(self.store.data["trials"]),1)
        self.assertTrue(service.history[-1]["finish_pass"])

    def test_finish_requires_confirmation_and_is_invalid_after_disconnect(self):
        service = self.cut_completed()
        payload = self.payload(repeat_id=service.repeat_status()["id"],
                               clip_removed=True)
        with self.assertRaises(ValueError):
            self.action("profile_test_finish",payload)
        self.cnc._close("Disconnected")
        self.assertFalse(service.repeat_status()["valid"])
        self.assertFalse(service.repeat_status()["available"])

    def test_finish_checks_live_offset_and_profile_change(self):
        service = self.cut_completed()
        payload = self.payload(repeat_id=service.repeat_status()["id"],
                               setup_unchanged=True,clip_removed=True)
        changed = ["[G54:10,20,5.1]","[G92:0,0,0]","[TLO:0]"]
        with patch.object(self.cnc,"_status"),patch.object(
            self.cnc,"_line",side_effect=lambda c:changed if c=="$#" else MODAL
        ), self.assertRaises(ValueError):
            self.cnc.action("profile_test_finish",payload)
        self.assertFalse(service.repeat_status()["valid"])

    def test_finish_is_invalidated_by_profile_selection(self):
        service = self.cut_completed()
        self.action("profile_select",{"profile_id":"default"})
        self.assertFalse(service.repeat_status()["valid"])

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
