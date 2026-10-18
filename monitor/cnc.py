# ---------------------------------------------------------------------------
# cnc.py
# 2026-10-18
# - Single USB owner, pin diagnostics, bounded Z probing and file jobs.
# ---------------------------------------------------------------------------
"""Manual CNC access; never reconnect, home, unlock or start jobs implicitly."""

import math
import threading
import time
from monitor.jobs import JobRunner, parse_program
from monitor.probes import ZProbe

SERIAL_PATH = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"


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
        if not math.isfinite(distance) or not 0 < abs(distance) <= 10:
            raise ValueError("Step must be between 0 and 10 mm")
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

    def __init__(self):
        self.lock = threading.RLock()
        self.port = None
        self.report = None
        self.report_time = None
        self.offset = None
        self.error = "Niepodłączona — połącz przy maszynie."
        self.info = []
        self.jobs = JobRunner()
        self.probe = ZProbe()
        self.probe_tested = False

    def _close(self, error):
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
        if report["state"] == "Idle" and report["probe_triggered"]:
            self.probe_tested = True
        if "WCO" in report:
            self.offset = report["WCO"]
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
                "z_probe": self.probe.status(),
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

    def action(self, action, payload):
        """Exclude all other senders while a probe owns the serial stream."""
        with self.lock:
            if action == "probe_stop":
                return self.probe.cancel()
            if action == "probe_heartbeat":
                return self.probe.heartbeat(payload.get("lease"))
            if self.probe.active():
                raise ValueError("Sondowanie aktywne — użyj Przerwij sondę.")
            if action == "probe_start":
                try:
                    return self.probe.start(self, payload)
                except RuntimeError as error:
                    self._close(str(error))
                    raise
            return self._action(action, payload)

    def _action(self, action, payload):
        """Perform one manual command; failures close and never retry USB."""
        if action in ("job_pause", "job_resume", "job_stop"):
            if action == "job_resume" and payload.get("confirmed") is not True:
                raise ValueError("Wymagane potwierdzenie wznowienia.")
            return self.jobs.control(action[4:], payload.get("job_id"))
        if action == "job_heartbeat":
            return self.jobs.heartbeat(payload.get("lease"))
        if action == "job_clear":
            return self.jobs.clear()
        if action == "job_load":
            program = parse_program(payload.get("name"), payload.get("content"))
            with self.lock:
                self.jobs.load(program)
            return
        if action == "job_start":
            with self.lock:
                if self.jobs.active() or self.port is None:
                    raise ValueError("Połącz CNC; zakończ poprzednie zadanie.")
                if payload.get("confirmed") is not True:
                    raise ValueError("Wymagane potwierdzenie operatora.")
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
                return self.jobs.start(payload.get("job_id"))
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
                if self.probe.active():
                    self.probe.tick(self)
                elif self.jobs.active():
                    self.jobs.tick(self)
                elif self.port is not None and (
                    time.monotonic() - last_poll >= 0.5
                ):
                    last_poll = time.monotonic()
                    try:
                        self._status()
                    except Exception as error:
                        self._close(str(error))
        with self.lock:
            if self.probe.active():
                self.probe.abort(self, "Usługa zatrzymana podczas sondowania.")
            if self.jobs.active():
                self.jobs.abort(self, "Usługa zatrzymana podczas zadania.")
            self._close("Service stopped")

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
