# ---------------------------------------------------------------------------
# cnc.py
# 2026-10-24
# - Exclusive USB owner for file jobs, grid maps and service depth trials.
# ---------------------------------------------------------------------------
"""Manual CNC access; never reconnect, home, unlock or start jobs implicitly."""

import math
import threading
import time
from monitor.jobs import JobRunner, parse_program
from monitor.probes import ZProbe
from monitor.surfaces import SurfaceScan
from monitor.compensation import compensate_program, live_offset
from monitor.feed import with_xy_feed
from monitor.calibration import Calibration, with_cut_depth
from monitor.profile_test import preview as profile_preview

SERIAL_PATH = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
JOG_LIMITS_MM = {"X": 300, "Y": 180, "Z": 10}


def parse_status(line):
    """Parse GRBL positions; work coordinates require WPos or MPos and WCO."""
    if not line.startswith("<") or not line.endswith(">"):
        raise ValueError("Invalid status report")
    parts = line[1:-1].split("|")
    result = {"state": parts[0], "position": None, "offset": None,
              "probe_triggered": False}
    values = {}
    for part in parts[1:]:
        key, _, value = part.partition(":")
        if key == "Pn":
            result["probe_triggered"] = "P" in value
        if key in ("MPos", "WPos", "WCO"):
            coordinates = [float(item) for item in value.split(",")[:3]]
            if len(coordinates) != 3:
                raise ValueError("Invalid position")
            if not all(math.isfinite(item) for item in coordinates):
                raise ValueError("Nonfinite position")
            values[key] = coordinates
    result.update(values)
    return result


def manual_command(action, payload):
    """Build only allowlisted commands; user input cannot contain G-code."""
    if action == "jog":
        axis = payload.get("axis")
        distance = float(payload.get("distance", 0))
        feed = float(payload.get("feed", 0))
        if axis not in ("X", "Y", "Z"):
            raise ValueError("Invalid axis")
        if not math.isfinite(distance) or not (
            0.01 <= abs(distance) <= JOG_LIMITS_MM[axis]
        ):
            raise ValueError(
                f"Krok osi {axis}: 0,01–{JOG_LIMITS_MM[axis]} mm."
            )
        if not math.isfinite(feed) or not 1 <= feed <= 300:
            raise ValueError("Feed must be 1 to 300 mm/min")
        return f"$J=G91 G21 {axis}{distance:g} F{feed:g}"
    if action == "zero_xy":
        return "G10 L20 P1 X0 Y0"
    if action == "zero_z":
        return "G10 L20 P1 Z0"
    if action == "spindle_on":
        power = int(payload.get("power", 0))
        if not 1 <= power <= 1000:
            raise ValueError("Power must be 1 to 1000; it is not RPM")
        return f"M3 S{power}"
    if action == "spindle_off":
        return "M5"
    raise ValueError("Unsupported action")


class Controller:
    """Serialize polling and commands through one exclusive USB owner."""

    def __init__(self, profile_path=None):
        self.lock = threading.RLock()
        self.port = None
        self.report = None
        self.report_time = None
        self.offset = None
        self.error = "Niepodłączona — połącz przy maszynie."
        self.info = []
        self.jobs = JobRunner()
        self.probe = ZProbe()
        self.surface = SurfaceScan()
        self.last_probe = self.probe
        self.probe_tested = False
        self.calibration = Calibration(profile_path)

    def _close(self, error):
        self.calibration.invalidate("Połączenie CNC zostało przerwane.")
        self.surface.invalidate("Połączenie CNC zostało przerwane.")
        self.probe_tested = False
        if self.port is not None:
            self.port.close()
        self.port = None
        self.report = None
        self.report_time = None
        self.offset = None
        self.error = error
        self.info = []

    def _read(self):
        line = self.port.readline(1025)
        if len(line) > 1024:
            raise RuntimeError("Oversized controller reply")
        return line.decode("ascii", errors="replace").strip()

    def _status(self, starting=False):
        self.port.write(b"?")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            line = self._read()
            if line.startswith("<"):
                self._accept_status(line)
                return
            if starting and line.startswith("Grbl"):
                continue
            if line.startswith(("Grbl", "ALARM:")):
                raise RuntimeError("Controller reset or alarm: " + line)
        raise RuntimeError("No current controller status; reconnect manually")

    def _accept_status(self, line):
        """Update cached coordinates from either polling or the job reader."""
        report = parse_status(line)
        if report["probe_triggered"] and not self.last_probe.active() and (
            not self.jobs.active() and not self.calibration.runner.active()
        ):
            self.probe_tested = True
        if "WCO" in report:
            self.offset = report["WCO"]
            scan = self.calibration.scan
            if scan.offset is not None and any(
                abs(a - b) > 0.002 for a, b in zip(self.offset, scan.offset)
            ):
                self.calibration.invalidate("Zero materiału zmieniło się.")
                if self.calibration.runner.active():
                    raise RuntimeError("Zero zmieniło się podczas próby.")
            if self.surface.valid and any(abs(a - b) > 0.002 for a, b in zip(
                self.offset, self.surface.offset
            )):
                self.surface.invalidate("Zero materiału zmieniło się.")
                if self.jobs.active() and self.jobs.status()["compensated"]:
                    raise RuntimeError(
                        "Zero mapy zmieniło się podczas programu."
                    )
        position = report.get("WPos")
        if position is None and "MPos" in report and self.offset is not None:
            position = []
            for index in range(3):
                position.append(report["MPos"][index] - self.offset[index])
        report["position"] = position
        self.report = report
        self.report_time = time.monotonic()

    def _line(self, command):
        self.port.write((command + "\n").encode("ascii"))
        replies = []
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            line = self._read()
            if line == "ok":
                return replies
            if line.startswith(("error:", "ALARM:", "Grbl")):
                raise RuntimeError(line)
            if line:
                replies.append(line)
        # Never retry: the command may already have been executed.
        raise RuntimeError("Reply timeout; command outcome unknown")

    def connect(self):
        """Open only after an explicit operator request, with DTR/RTS low."""
        import serial

        with self.lock:
            if self.port is not None:
                raise ValueError("Already connected")
            try:
                port = serial.Serial(
                    port=None, baudrate=115200, timeout=0.2,
                    write_timeout=1, exclusive=True,
                )
                port.dtr = False
                port.rts = False
                port.port = SERIAL_PATH
                self.port = port
                port.open()
                # Startup output is not a command acknowledgment.
                # ESP32 boot output can arrive seconds after opening USB.
                # This wait belongs only to explicit connection, never recovery.
                time.sleep(7)
                port.reset_input_buffer()
                self._status(starting=True)
                if self.report["state"] != "Idle":
                    raise RuntimeError("Machine is not Idle; no commands sent")
                self.info = self._line("$I")
                self.info.extend(self._line("$$"))
                settings = {}
                for line in self.info:
                    if line.startswith("$") and "=" in line:
                        key, value = line.split("=", 1)
                        settings[key] = float(value)
                if settings.get("$30") != 1000 or settings.get("$32") != 0:
                    raise RuntimeError("Unexpected spindle scale or laser mode")
                self._line("$G")
                self._status()
                self.error = None
            except Exception as error:
                self._close(str(error))
                raise RuntimeError(str(error)) from error

    def status(self):
        """Return a cached report; no USB access occurs in this method."""
        with self.lock:
            age = None
            if self.report_time is not None:
                age = time.monotonic() - self.report_time
            connected = self.port is not None
            fresh = connected and age is not None and age < 2
            inverted = None
            if connected:
                for line in self.info:
                    if line == "$6=0":
                        inverted = False
                    elif line == "$6=1":
                        inverted = True
            return {
                "connected": connected,
                "fresh": fresh,
                "state": self.report["state"] if fresh else None,
                "position": self.report["position"] if fresh else None,
                "reason": self.error,
                "age_seconds": age,
                "info": self.info,
                "job": self.jobs.status(),
                "probe_triggered": (
                    self.report["probe_triggered"] if fresh else None
                ),
                "probe_tested": self.probe_tested,
                "probe_inverted": inverted,
                "z_probe": self.last_probe.status(),
                "surface_map": self.surface.status(),
                "jog_limits_mm": JOG_LIMITS_MM.copy(),
                "geometry_model": {
                    "type": "V",
                    "correction": self.calibration.profiles.active["model"],
                },
                "calibration": self.calibration.status(),
                "calibration_profiles": self.calibration.profiles.status(),
                "profile_test_plan": profile_preview(self.calibration.profiles),
            }

    def disconnect(self):
        """Release USB only after fresh Idle and M5 checks; never send M5."""
        with self.lock:
            if self.port is None:
                return
            try:
                self._status()
                if self.report["state"] != "Idle":
                    raise ValueError("Rozłączanie wymaga bezczynnej frezarki.")
                modal = self._line("$G")
                spindle_off = False
                for line in modal:
                    if line.startswith("[GC:") and line.endswith("]"):
                        spindle_off = "M5" in line[4:-1].split()
                if not spindle_off:
                    raise ValueError(
                        "Wyłącz wrzeciono przed rozłączeniem (wymagane M5)."
                    )
                self._close("CNC rozłączone przez operatora.")
            except ValueError:
                raise
            except Exception as error:
                self._close(str(error))
                raise RuntimeError(str(error)) from error

    def load_flow_program(self, payload, operation):
        """Attach trusted workflow metadata only through the internal loader."""
        with self.lock:
            self.action("job_load", payload)
            self.probe.completed_job_id = None
            self.jobs.program["pcb_flow"] = operation

    def action(self, action, payload):
        """Exclude all other senders while a probe owns the serial stream."""
        with self.lock:
            if action == "probe_stop":
                return self.last_probe.cancel()
            if action == "probe_heartbeat":
                return self.last_probe.heartbeat(payload.get("lease"))
            if self.last_probe.active():
                raise ValueError("Sondowanie aktywne — użyj Przerwij sondę.")
            if self.calibration.runner.active() and action not in (
                "job_pause", "job_resume", "job_stop", "job_heartbeat"
            ):
                raise ValueError("Próba aktywna — użyj Pauzy lub Stop.")
            if action in ("profile_create", "profile_update", "profile_select",
                          "profile_delete"):
                if self.jobs.active():
                    raise ValueError("Najpierw zakończ aktywny program.")
                # Read only through the existing owner; never open USB here.
                if self.port is not None:
                    self._status()
                    if self.report["state"] != "Idle":
                        raise ValueError("Zmiana profilu wymaga Idle.")
                store = self.calibration.profiles
                if action == "profile_create":
                    return store.create(payload)
                if action == "profile_update":
                    result = store.update(payload)
                    self.surface.invalidate("Zmieniono parametry profilu.")
                    if self.calibration.mode == "profile_test":
                        self.calibration.invalidate("Zmieniono profil testu.")
                    return result
                if action == "profile_delete":
                    target = next((item for item in store.data["profiles"]
                                   if item["id"] == payload.get("profile_id")),
                                  None)
                    if payload.get("confirmed") is not True or (
                        target is None or payload.get("profile_fingerprint")
                        != target["fingerprint"]
                    ):
                        raise ValueError("Potwierdź usunięcie aktualnego profilu.")
                    was_active = payload.get("profile_id") == store.active["id"]
                    result = store.delete(payload.get("profile_id"))
                    if was_active:
                        self.surface.invalidate("Usunięto aktywny profil.")
                        if self.calibration.mode == "profile_test":
                            self.calibration.invalidate("Usunięto profil testu.")
                    return result
                store.select(payload.get("profile_id"))
                self.surface.invalidate("Zmieniono profil kalibracji.")
                if self.calibration.mode == "profile_test":
                    self.calibration.invalidate("Zmieniono profil kalibracji.")
                return
            if action in ("service_prepare", "service_cut", "service_save",
                          "profile_test_prepare", "profile_test_cut",
                          "profile_test_finish"):
                if self.jobs.active() or self.calibration.runner.active():
                    raise ValueError("Najpierw zakończ aktywny program.")
                if action == "service_save":
                    return self.calibration.save(payload)
                if self.port is None:
                    raise ValueError("Najpierw połącz CNC.")
                try:
                    if action == "profile_test_finish":
                        return self.calibration.finish(self, payload)
                    if action in ("service_prepare", "profile_test_prepare"):
                        return self.calibration.prepare(
                            self, payload, action == "profile_test_prepare"
                        )
                    return self.calibration.cut(
                        self, payload, action == "profile_test_cut"
                    )
                except RuntimeError as error:
                    self._close(str(error))
                    raise
            if action in ("probe_start", "surface_start"):
                try:
                    runner = (
                        self.surface if action == "surface_start"
                        else self.probe
                    )
                    result = runner.start(self, payload)
                    self.calibration.invalidate_repeat("Rozpoczęto sondowanie.")
                    self.last_probe = runner
                    if action == "probe_start":
                        self.surface.invalidate("Ponownie ustawiono zero Z.")
                        self.calibration.invalidate("Ponownie ustawiono zero Z.")
                    return result
                except RuntimeError as error:
                    self._close(str(error))
                    raise
            if action == "probe_polarity":
                return self._probe_polarity(payload)
            return self._action(action, payload)

    def _probe_polarity(self, payload):
        """Change only $6 after explicit confirmation; never invert UI alone."""
        if payload.get("confirmed") is not True or (
            not isinstance(payload.get("inverted"), bool)
            or not isinstance(payload.get("before"), bool)
        ):
            raise ValueError("Wymagane potwierdzenie zmiany polaryzacji.")
        if self.port is None or self.jobs.active():
            raise ValueError("Połącz CNC i zakończ aktywny program.")
        try:
            self._status()
            if self.report["state"] != "Idle":
                raise ValueError("Zmiana polaryzacji wymaga Idle.")
            modal = self._line("$G")
            spindle_off = any(
                line.startswith("[GC:") and line.endswith("]")
                and "M5" in line[4:-1].split() for line in modal
            )
            if not spindle_off:
                raise ValueError("Wyłącz wrzeciono przed zmianą polaryzacji.")
            settings = self._line("$$")
            before = f"$6={int(payload['before'])}"
            if before not in settings:
                raise ValueError("Polaryzacja zmieniła się; odśwież panel.")
            command = f"$6={int(payload['inverted'])}"
            self._line(command)
            settings = self._line("$$")
            if command not in settings:
                raise RuntimeError("Nie potwierdzono zapisu polaryzacji.")
            self.info = [line for line in self.info if not line.startswith("$")]
            self.info.extend(settings)
            self._status()
        except ValueError:
            raise
        except Exception as error:
            self._close(str(error))
            raise RuntimeError(str(error)) from error
        finally:
            # A polarity change invalidates every previous contact test.
            self.probe_tested = False
            self.surface.invalidate("Zmiana polaryzacji sondy.")
            self.calibration.invalidate("Zmiana polaryzacji sondy.")

    def _action(self, action, payload):
        """Perform one manual command; failures close and never retry USB."""
        runner = (self.calibration.runner if self.calibration.runner.active()
                  else self.jobs)
        if action in ("job_pause", "job_resume", "job_stop"):
            if action == "job_resume" and payload.get("confirmed") is not True:
                raise ValueError("Wymagane potwierdzenie wznowienia.")
            return runner.control(action[4:], payload.get("job_id"))
        if action == "job_heartbeat":
            return runner.heartbeat(payload.get("lease"))
        if action == "job_clear":
            result = self.jobs.clear()
            self.surface.invalidate("Usunięto plik.")
            return result
        if action == "job_load":
            program = parse_program(payload.get("name"), payload.get("content"))
            with self.lock:
                self.jobs.load(program)
                self.surface.invalidate("Wczytano inny plik.")
            return
        if action == "job_start":
            with self.lock:
                if self.jobs.active() or self.port is None:
                    raise ValueError("Połącz CNC; zakończ poprzednie zadanie.")
                if payload.get("confirmed") is not True:
                    raise ValueError("Wymagane potwierdzenie operatora.")
                flow = self.jobs.program.get("pcb_flow")
                if flow:
                    if self.jobs.state in ("completed", "stopped", "failed"):
                        raise ValueError("Wczytaj etap ponownie i powtórz Z; "
                                         "nie uruchamiaj go drugi raz.")
                    if "xy_feed" in payload or payload.get("service_depth"):
                        raise ValueError("Zlecenie PCB wymaga parametrów CAM.")
                    if flow["zPreparation"] == "grid3":
                        if not payload.get("surface_map_id") or (
                            getattr(self.surface, "columns", 0) < 3
                            or getattr(self.surface, "rows", 0) < 3
                        ):
                            raise ValueError("Ten etap wymaga nowej mapy "
                                             "Z co najmniej 3×3.")
                    elif self.probe.completed_job_id != self.jobs.job_id:
                        raise ValueError("Wykonaj nowy pomiar zera Z "
                                         "po zmianie wiertła.")
                    offset = live_offset(self._line("$#"))
                    if flow["kind"] == "drilling" and (
                        self.probe.completed_offset is None or any(
                            abs(a-b) > .002 for a, b in zip(
                                offset, self.probe.completed_offset)
                        )
                    ):
                        raise ValueError("Zero Z zmieniło się po pomiarze.")
                    expected = flow.get("xyOffset")
                    if expected is not None and any(
                        abs(a-b) > .002 for a, b in zip(offset[:2], expected)
                    ):
                        raise ValueError("Zero X/Y zlecenia zmieniło się.")
                    flow["xyOffset"] = offset[:2]
                    if flow["kind"] == "outline" and not getattr(
                        self.surface, "perimeter", False
                    ):
                        raise ValueError("Obrys wymaga pomiaru 8 punktów "
                                         "na nieobrobionej ramie miedzi.")
                self.calibration.profiles.check_program(
                    self.jobs.program, payload
                )
                self._status()
                if self.report["state"] != "Idle":
                    raise ValueError("Start wymaga stanu Idle.")
                if self.report["position"] is None:
                    raise ValueError(
                        "Brak współrzędnych roboczych; ustaw zero."
                    )
                modal = self._line("$G")
                tokens = []
                for line in modal:
                    if line.startswith("[GC:") and line.endswith("]"):
                        tokens = line[4:-1].split()
                if "G54" not in tokens or "M5" not in tokens:
                    raise ValueError(
                        "Start wymaga G54 i wyłączonego wrzeciona."
                    )
                execution = None
                if payload.get("service_depth") is True:
                    profile = self.calibration.profile
                    if profile is None or (
                        payload.get("expected_depth") != profile["depth"]
                    ):
                        raise ValueError("Profil Z zmienił się; odśwież panel.")
                    execution = with_cut_depth(
                        self.jobs.program, profile["depth"]
                    )
                if "xy_feed" in payload:
                    execution = with_xy_feed(
                        execution or self.jobs.program, payload["xy_feed"]
                    )
                if payload.get("surface_map_id") is not None:
                    surface = self.surface
                    if not surface.valid or surface.map_id != payload.get(
                        "surface_map_id"
                    ) or surface.job_id != self.jobs.job_id:
                        raise ValueError(
                            "Mapa jest nieaktualna; powtórz pomiar."
                        )
                    offset = live_offset(self._line("$#"))
                    if any(abs(a - b) > 0.002 for a, b in zip(
                        offset, surface.offset
                    )):
                        surface.invalidate("Zero materiału zmieniło się.")
                        raise ValueError("Zero mapy zmieniło się.")
                    execution = compensate_program(
                        execution or self.jobs.program, surface
                    )
                if flow and flow["kind"] == "drilling":
                    if flow.get("breakthroughMm", 0) < (
                        flow.get("surfaceSpreadMm", 0)
                        + flow.get("uncertaintyMm", 0)
                    ):
                        raise ValueError("Zapas wiercenia jest mniejszy niż "
                                         "zmierzona nierówność i budżet błędu.")
                    if self.calibration.profiles.active["id"] != "default":
                        raise ValueError("Wiercenie wymaga profilu roboczego "
                                         "bez korekty frezu V.")
                result = self.jobs.start(payload.get("job_id"), execution)
                self.calibration.invalidate_repeat("Uruchomiono inny program.")
                return result
        with self.lock:
            if self.jobs.active():
                raise ValueError(
                    "Zadanie aktywne — użyj Pauzy lub Stop zadania."
                )
            return self._manual_action(action, payload)

    def _manual_action(self, action, payload):
        """Keep existing manual operations isolated from the job sender."""
        if action == "connect":
            return self.connect()
        if action == "disconnect":
            return self.disconnect()
        if action == "jog_cancel":
            with self.lock:
                if self.port is None:
                    raise ValueError("Connect first")
                try:
                    self.port.write(b"\x85")
                    self._status()
                except Exception as error:
                    self._close(str(error))
                    raise RuntimeError(str(error)) from error
            return
        command = manual_command(action, payload)
        with self.lock:
            if self.port is None:
                raise ValueError("Connect first")
            try:
                self._status()
                if self.report["state"] != "Idle":
                    raise ValueError("Machine must be Idle")
                modal = self._line("$G")
                if not any("G54" in line.split() for line in modal):
                    raise ValueError("G54 work coordinates required")
                self._line(command)
                # Changing zero invalidates the cached work offset.
                if action.startswith("zero_"):
                    self.offset = None
                    self.surface.invalidate("Ręcznie zmieniono zero materiału.")
                    self.calibration.invalidate("Ręcznie zmieniono zero.")
                self._status()
            except ValueError:
                raise
            except Exception as error:
                self._close(str(error))
                raise RuntimeError(str(error)) from error

    def worker(self, stop):
        """Poll connected USB only; no automatic connection or recovery."""
        last_poll = 0
        while not stop.wait(0.02):
            with self.lock:
                if self.last_probe.active():
                    self.last_probe.tick(self)
                elif self.calibration.runner.active():
                    self.calibration.runner.tick(self)
                elif self.jobs.active():
                    self.jobs.tick(self)
                elif self.port is not None and (
                    time.monotonic() - last_poll >= 0.1
                ):
                    last_poll = time.monotonic()
                    try:
                        self._status()
                    except Exception as error:
                        self._close(str(error))
        with self.lock:
            if self.last_probe.active():
                self.last_probe.abort(
                    self, "Usługa zatrzymana podczas sondowania."
                )
            if self.jobs.active():
                self.jobs.abort(self, "Usługa zatrzymana podczas zadania.")
            if self.calibration.runner.active():
                self.calibration.runner.abort(
                    self, "Usługa zatrzymana podczas próby."
                )
            self._close("Service stopped")

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
