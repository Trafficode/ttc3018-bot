# ---------------------------------------------------------------------------
# test_profile_test.py
# 2026-10-24
# - Exact coupon geometry, immutable depth and simulated nine-point execution.
# ---------------------------------------------------------------------------
"""All probing and cutting use fake serial replies; never real hardware."""

import math
import copy
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from monitor.cnc import Controller
from monitor.compensation import height_at
from monitor.jobs import WORD
from monitor.profile_test import configuration, contour_moves, layout, preview, program
from monitor.profiles import check_cam_program
from test_probes import Port


MODAL = ["[GC:G0 G54 G21 G90 G94 M5]"]
OFFSET = ["[G54:10,20,5]", "[G92:0,0,0]", "[TLO:0]"]


class ProfileTestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cnc = Controller(Path(self.directory.name)/"p.json")
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
        travel_z = 5 + scan.clearance
        self.receive(f"ok\n<Idle|MPos:12,23,{travel_z}|WCO:10,20,5>\n")
        for point in scan.points:
            x, y = point["x"], point["y"]
            self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},{travel_z}>\n")
            if travel_z > 6:
                self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},6>\n")
            z = 5 + .001*(x-2)+.002*(y-3)
            self.receive(f"[PRB:{x+10},{y+20},{z}:1]\nok\n"
                         f"<Idle|MPos:{x+10},{y+20},{z-.002}|Pn:P>\n")
            self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},{travel_z}>\n")
        return scan

    def complete_cycle_scan(self, **options):
        result = self.action("profile_test_start", self.payload(fixed_probe=True, **options))
        scan = self.cnc.calibration.scan
        self.assertEqual(self.cnc.calibration.origin, [2, 3])
        self.assertIn("cycle_lease", result)
        self.receive("[PRB:12,23,5.2:1]\nok\n<Idle|MPos:12,23,5.198|Pn:P>\n")
        travel_z = 5.2 + scan.clearance
        self.receive(f"ok\nok\n<Idle|MPos:12,23,{travel_z}|WCO:10,20,5.2>\n")
        for point in scan.points:
            x, y = point["x"], point["y"]
            self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},{travel_z}>\n")
            if travel_z > 6.2:
                self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},6.2>\n")
            z = 5.2 + .001*(x-2)+.002*(y-3)
            self.receive(f"[PRB:{x+10},{y+20},{z}:1]\nok\n"
                         f"<Idle|MPos:{x+10},{y+20},{z-.002}|Pn:P>\n")
            self.receive(f"ok\n<Idle|MPos:{x+10},{y+20},{travel_z}>\n")
        self.assertTrue(scan.valid)
        return result

    def advance_cycle(self):
        with patch.object(self.cnc, "_status"), patch.object(self.cnc, "_line",
            side_effect=lambda command: ["[G54:10,20,5.2]", "[G92:0,0,0]", "[TLO:0]"] if command == "$#" else MODAL):
            self.cnc.calibration.tick_cycle(self.cnc)

    def test_one_confirmation_references_z_maps_and_starts_exactly_one_cut(self):
        result = self.complete_cycle_scan()
        calibration = self.cnc.calibration
        self.assertEqual(self.cnc.offset, [10,20,5.2])
        self.assertEqual(sum(b"G10L20P1Z" in command for command in self.cnc.port.writes), 1)
        self.assertFalse(any(b"G10L20P1X" in command or b"M3" in command for command in self.cnc.port.writes))
        self.advance_cycle()
        self.assertEqual(calibration.cycle["phase"], "cutting")
        self.assertTrue(calibration.runner.active())
        self.assertTrue(calibration.runner.program["compensated"])
        job = calibration.runner.job_id
        self.advance_cycle()
        self.assertEqual(calibration.runner.job_id, job)
        self.cnc.action("profile_test_heartbeat", {"lease": result["cycle_lease"]})
        with self.assertRaises(ValueError):
            self.cnc.action("profile_test_heartbeat", {"lease": "observer"})
        calibration.runner.state = "completed"
        self.advance_cycle()
        self.assertFalse(calibration.cycle["active"])
        self.assertEqual(calibration.cycle["phase"], "completed")

    def test_next_start_rebuilds_from_saved_settings_and_rejects_old_preview(self):
        original = dict(name="Próba", source="settings", depth=.1, tip=.1,
                        angle=30, feed=40, plunge=10, power=600)
        draft = self.store.create(original)
        self.store.select(draft["id"])
        snapshots = []
        for revision, options in (
            (original, {"passes": 1, "overlap_percent": 0}),
            ({**original, "depth": .12, "tip": .15, "angle": 45,
              "feed": 30, "corner_feed": 15, "plunge": 5, "power": 900},
             {"passes": 2, "overlap_percent": 75})
        ):
            if snapshots:
                before = self.store.active["fingerprint"]
                self.action("profile_update", self.payload(**revision))
                count = len(self.cnc.port.writes)
                with self.assertRaisesRegex(ValueError, "Profil testu zmienił"):
                    self.action("profile_test_start", self.payload(
                        profile_fingerprint=before, fixed_probe=True, **options))
                self.assertEqual(len(self.cnc.port.writes), count)
            plan = preview(self.store)
            if options["passes"] == 2:
                plan = plan["variants"][str(options["overlap_percent"])]
            planned_width = revision["tip"] + 2 * revision["depth"] * math.tan(
                math.radians(revision["angle"] / 2))
            self.assertAlmostEqual(plan["diameter"], planned_width)
            self.assertEqual(plan["diameter_source"], "nominal")
            self.assertEqual(plan["settings"]["corner_feed"], revision.get("corner_feed"))
            if revision.get("corner_feed"):
                with self.assertRaisesRegex(ValueError, "wyłącznie parametrów profilu"):
                    self.action("profile_test_start", self.payload(
                        fixed_probe=True, corner_feed=25, **options))
                self.assertEqual(len(self.cnc.port.writes), count)
            self.complete_cycle_scan(**options)
            scan = self.cnc.calibration.scan
            self.assertAlmostEqual(scan.area["X"][1] - scan.area["X"][0], plan["width"])
            self.assertAlmostEqual(scan.area["Y"][1] - scan.area["Y"][0], plan["height"])
            self.advance_cycle()
            calibration = self.cnc.calibration
            self.assertEqual(calibration.cycle["phase"], "cutting")
            sent = calibration.runner.program
            geometry = sent["tool_geometry"]
            self.assertEqual(geometry["profile_id"], draft["id"])
            self.assertAlmostEqual(geometry["diameter_mm"], planned_width)
            self.assertEqual(geometry["depth_mm"], revision["depth"])
            self.assertEqual(geometry["passes"], options["passes"])
            self.assertEqual(geometry["overlap_percent"], options["overlap_percent"])
            self.assertAlmostEqual(geometry["step_mm"], plan["step_mm"])
            self.assertEqual(sent["max_power"], revision["power"])
            codes = [row["code"] for row in sent["lines"]]
            feeds = [revision["feed"], revision["plunge"]]
            if revision.get("corner_feed"):
                feeds.append(revision["corner_feed"])
                self.assertEqual(geometry["corner_feed_mm_min"], revision["corner_feed"])
            for feed in feeds:
                self.assertTrue(any(f"F{feed}G1" in code for code in codes))
            snapshots.append((calibration.runner.job_id, sent["bounds_mm"]["Y"]))
            calibration.runner.state = "completed"
            self.advance_cycle()
            calibration.observe()
            self.cnc._accept_status("<Idle|MPos:12,23,6.2|WCO:10,20,5.2>")
        self.assertNotEqual(snapshots[0][0], snapshots[1][0])
        self.assertNotEqual(snapshots[0][1], snapshots[1][1])

    def test_corner_moves_cover_short_edges_and_split_long_edges_without_changing_path(self):
        points = [(0, 0), (4, 0), (4, 1), (0, 1)]
        original = [(4, 0, 50), (4, 1, 50), (0, 1, 50), (0, 0, 50)]
        for corner_feed in (None, 50):
            self.assertEqual(list(contour_moves(points, 50, corner_feed)), original)
        self.assertEqual(list(contour_moves(points, 50, 25)), [
            (.5, 0, 25), (3.5, 0, 50), (4, 0, 25), (4, 1, 25),
            (3.5, 1, 25), (.5, 1, 50), (0, 1, 25), (0, 0, 25),
        ])

    def test_same_settings_use_the_saved_calibrated_width_in_preview_and_cut(self):
        profile = self.store.create({
            "source": "manual", "name": "Zmierzony", "tip": .1, "angle": 30,
            "depth": .1, "feed": 40, "plunge": 10, "power": 600,
            "samples": [{"depth": .1, "width": 1, "measured_width": .92,
                         "used_diameter": .15}],
        })
        self.store.select(profile["id"])
        estimate = preview(self.store)
        self.assertEqual(estimate["diameter_source"], "calibrated")
        self.assertAlmostEqual(estimate["diameter"], .23)
        self.complete_cycle_scan()
        self.advance_cycle()
        generated = self.cnc.calibration.runner.program["tool_geometry"]
        self.assertAlmostEqual(generated["diameter_mm"], estimate["diameter"])
        self.assertEqual(generated["correction"], profile["model"])
        self.assertAlmostEqual(generated["centreline_spacing_mm"], .73)

    def test_cycle_expired_owner_never_starts_cut(self):
        self.complete_cycle_scan()
        self.cnc.calibration.cycle_heartbeat_at = time.monotonic()-9
        self.advance_cycle()
        self.assertFalse(self.cnc.calibration.runner.active())
        self.assertEqual(self.cnc.calibration.cycle["phase"], "failed")

    def test_profile_test_uses_shared_probe_settings_without_changing_cut_feed(self):
        saved = self.cnc.action("probe_settings_save", {
            "revision": self.cnc.probe_settings.status()["revision"],
            "max_descent_mm": 1.2, "xy_feed_mm_min": 75,
            "travel_clearance_mm": 4, "z_feed_mm_min": 30,
        })
        self.complete_cycle_scan(probe_settings_revision=saved["revision"])
        descents = [line for line in self.cnc.port.writes if b"G38.2" in line]
        travels = [line for line in self.cnc.port.writes if line.startswith(b"G1X")]
        self.assertEqual(descents, [b"G90G38.2Z-0.2000F30\n"] * 10)
        self.assertEqual(len(travels), 9)
        self.assertTrue(all(line.endswith(b"F75\n") for line in travels))
        self.advance_cycle()
        program_lines = self.cnc.calibration.runner.program["lines"]
        self.assertTrue(any("F100G1" in row["code"] for row in program_lines))
        plane = 4 + max(point["z"] for point in self.cnc.calibration.scan.samples)
        xy_travels = [index for index, row in enumerate(program_lines)
                      if row["code"].startswith("G1X") and row["code"].endswith("F75")]
        self.assertEqual(len(xy_travels), 3)
        for index in xy_travels:
            self.assertEqual(program_lines[index - 1]["code"], f"G0Z{plane:.4f}")

    def test_double_pass_cycle_uses_both_outward_paths_and_records_exact_trial(self):
        profile = self.store.create({"source": "settings", "name": "Nowy",
            "tip": .15, "angle": 30, "depth": .1, "feed": 60,
            "plunge": 5, "power": 600})
        self.store.select(profile["id"])
        options = {"passes": 2, "overlap_percent": 50}
        config = configuration(self.store, self.payload(**options))
        plan = layout(config)
        step = plan["diameter"] / 2
        self.assertAlmostEqual(plan["total_mm"], 1.5 * plan["diameter"])
        for shape in plan["shapes"]:
            inner, outer = shape["paths"]
            self.assertGreater(len(outer), 0)
            self.assertAlmostEqual(
                min(point[0] for point in inner) - min(point[0] for point in outer),
                step if shape["kind"] == "strip" else step / math.cos(math.pi / 8))
            self.assertTrue(all(step <= x <= plan["width"] - step
                                and step <= y <= plan["height"] - step
                                for x, y in outer))
        self.complete_cycle_scan(**options)
        self.advance_cycle()
        calibration = self.cnc.calibration
        self.assertEqual(calibration.cycle["phase"], "cutting")
        raw = program(calibration.origin, config)
        self.assertEqual(sum(row["code"].startswith("G1Z") for row in raw["lines"]), 6)
        self.assertEqual(calibration.runner.program["tool_geometry"], raw["tool_geometry"])
        self.assertFalse(calibration.repeat_status()["available"])
        calibration.runner.state = "completed"
        calibration.observe()
        trial = self.store.data["trials"][-1]
        self.assertEqual(trial["profile"], {"id": profile["id"], "fingerprint": profile["fingerprint"]})
        self.assertAlmostEqual(trial["geometry"]["step_mm"], step)
        self.assertEqual(trial["geometry"]["strip_widths"], [.3, .5])

    def test_rejects_invalid_overlap_before_probe(self):
        for options in ({"passes": 1, "overlap_percent": 50},
                        {"passes": 2, "overlap_percent": 100}, {"passes": 3}):
            with self.assertRaises(ValueError):
                self.action("profile_test_start", self.payload(fixed_probe=True, **options))
        self.assertFalse(self.cnc.calibration.scan.active())

    def test_cycle_stop_or_failed_probe_never_starts_cut(self):
        self.action("profile_test_start", self.payload(fixed_probe=True))
        self.cnc.action("probe_stop", {})
        self.cnc.calibration.scan.state = "completed"
        self.cnc.calibration.scan.valid = True
        self.advance_cycle()
        self.assertFalse(self.cnc.calibration.runner.active())
        self.assertEqual(self.cnc.calibration.cycle["phase"], "stopped")

    def test_cycle_requires_confirmation_and_fixed_probe(self):
        for payload in (self.payload(), self.payload(fixed_probe=True, confirmed=False)):
            with self.assertRaises(ValueError):
                self.action("profile_test_start", payload)
        self.assertFalse(self.cnc.last_probe.active())

    def test_cycle_profile_drift_blocks_transition(self):
        self.complete_cycle_scan()
        self.cnc.calibration.profile_identity["fingerprint"] = "changed"
        self.advance_cycle()
        self.assertFalse(self.cnc.calibration.runner.active())
        self.assertEqual(self.cnc.calibration.cycle["phase"], "failed")

    def test_nominal_copper_and_actual_sweep_fit_the_probe_area(self):
        config = configuration(self.store)
        for tip in (.1, .3, .5):
            config["tip"] = tip
            plan = layout(config)
            self.assertEqual([shape["kind"] for shape in plan["shapes"]],
                             ["strip", "strip", "octagon"])
            self.assertEqual([shape["width"] for shape in plan["shapes"][:2]], [.3, .5])
            self.assertEqual(plan["shapes"][2]["diameter"], 1)
            self.assertEqual((plan["width"], plan["height"]), (5, 5))
            r = plan["diameter"]/2
            points = [p for s in plan["shapes"] for p in s["path"]]
            self.assertAlmostEqual(min(p[1] for p in points)-r, .4)
            self.assertAlmostEqual(plan["height"]-max(p[1] for p in points)-r, .4)
            for shape in plan["shapes"]:
                for x, y in shape["path"]:
                    self.assertGreaterEqual(x-r, 0)
                    self.assertGreaterEqual(y-r, 0)
                    self.assertLessEqual(x+r, plan["width"])
                    self.assertLessEqual(y+r, plan["height"])
                points = shape["copper"]
                if shape["kind"] == "strip":
                    sides = (points[1][0] - points[0][0], points[2][1] - points[0][1])
                    self.assertAlmostEqual(max(sides), shape["length"])
                    self.assertGreaterEqual(shape["length"], 1)
                    self.assertLessEqual(shape["length"], 3)
                    self.assertAlmostEqual(min(sides), shape["width"])
                    path = shape["path"]
                    self.assertAlmostEqual(min(path[2][i] - path[0][i] for i in (0, 1)) - 2*r,
                                           shape["width"])
                else:
                    self.assertAlmostEqual(math.dist(points[0], points[4]),
                                           shape["diameter"])
            codes = [p["code"] for p in program([2,3],config)["lines"]]
            self.assertFalse(any("G2" in c and "G21" not in c for c in codes))
            self.assertEqual(sum(c.startswith("G1Z") for c in codes), 3)

    def test_two_pass_sweeps_fit_the_fixed_field_and_stay_separate(self):
        config = configuration(self.store)
        for tip, depth, angle in ((.01, .01, 10), (.1, .12, 30), (.3, .075, 30)):
            for passes, overlap in ((1, 0), (2, 25), (2, 50), (2, 75)):
                with self.subTest(tip=tip, depth=depth, angle=angle, passes=passes, overlap=overlap):
                    plan = layout({**config, "tip": tip, "depth": depth, "angle": angle,
                                   "passes": passes, "overlap_percent": overlap})
                    radius = plan["diameter"] / 2
                    self.assertEqual((plan["width"], plan["height"]), (5, 5))
                    self.assertEqual(plan["corner_zone_mm"], .5)
                    sweeps = []
                    for shape in plan["shapes"]:
                        xs, ys = zip(*shape["paths"][-1])
                        sweep = (min(xs)-radius, min(ys)-radius, max(xs)+radius, max(ys)+radius)
                        sweeps.append(sweep)
                        margin = plan["margin_mm"]
                        self.assertGreaterEqual(sweep[0], margin - 1e-9)
                        self.assertGreaterEqual(sweep[1], margin - 1e-9)
                        self.assertLessEqual(sweep[2], plan["width"] - margin + 1e-9)
                        self.assertLessEqual(sweep[3], plan["height"] - margin + 1e-9)
                    for index, first in enumerate(sweeps):
                        for other in sweeps[index+1:]:
                            separate = max(other[0]-first[2], first[0]-other[2],
                                           other[1]-first[3], first[1]-other[3])
                            self.assertGreaterEqual(separate, .15-1e-9)

    def test_oversized_two_pass_groove_is_rejected_before_probing(self):
        profile = self.store.create({"name": "Szeroki", "source": "settings",
            "tip": .5, "angle": 30, "depth": .05, "feed": 50, "plunge": 20, "power": 300})
        self.store.select(profile["id"])
        plan = preview(self.store)
        self.assertNotIn("error", plan)
        self.assertIn("5 × 5 mm", plan["variants"]["25"]["error"])
        with self.assertRaisesRegex(ValueError, "5 × 5 mm"):
            self.action("profile_test_start", self.payload(fixed_probe=True, passes=2, overlap_percent=25))
        self.assertEqual(self.cnc.port.writes, [])

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
        high = 3 + max(p["z"] for p in service.scan.samples)
        for line in service.runner.program["lines"]:
            values = {key:float(value) for key,value in WORD.findall(line["code"])}
            if line["code"].startswith("G1X") and line["code"].endswith("F100"):
                self.assertAlmostEqual(previous["Z"],high,places=3)
            if values.get("G") == 1 and values.get("F") == 20:
                local = height_at(service.scan,values["X"],values["Y"])
                self.assertEqual(set(previous),{"G","Z"})
                self.assertAlmostEqual(previous["Z"]-local,.5,places=3)
                self.assertAlmostEqual(values["Z"]-local,-.05,places=3)
                approaches.append(previous["Z"])
            previous = values
        self.assertEqual(len(approaches),3)
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
