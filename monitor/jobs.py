# ---------------------------------------------------------------------------
# jobs.py
# 2026-10-12
# - Validated linear GRBL programs and a single-owner asynchronous sender.
# ---------------------------------------------------------------------------
"""Upload never touches USB; only explicit operator start/resume runs code."""

import math
import re
import secrets
import threading
import time

MAX_FILE_BYTES = 1024 * 1024
ACTIVE = {"running", "draining", "pausing", "paused", "resuming"}
WORD = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))")
G_CODES = {0, 1, 4, 17, 21, 40, 49, 54, 80, 90, 94}
M_CODES = {2, 3, 5, 30}


def parse_program(name, content):
    """Accept bounded, absolute linear mill jobs, with explicit units/modes."""
    if not isinstance(name, str) or not isinstance(content, str):
        raise ValueError("Nazwa i zawartość pliku muszą być tekstem.")
    name = name.replace("\\", "/").split("/")[-1]
    if len(name) > 128 or not name.lower().endswith(
        (".nc", ".gcode", ".tap", ".ngc")
    ):
        raise ValueError("Wybierz plik .nc, .gcode, .tap lub .ngc.")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Limit pliku: 1 MiB.")
    lines = []
    modes = set()
    motion = None
    feed = None
    power = None
    spindle_on = False
    ended = False
    point = {"X": None, "Y": None, "Z": None}
    bounds = {axis: [None, None] for axis in point}
    first_move = True
    max_feed = 0
    max_power = 0
    for number, raw in enumerate(content.splitlines(), 1):
        if not raw.isascii() or any(
            ord(char) < 32 and char != "\t" for char in raw
        ):
            raise ValueError(f"Linia {number}: wymagany tekst ASCII.")
        raw = raw.split(";", 1)[0]
        raw = re.sub(r"\([^()]*\)", "", raw)
        if "(" in raw or ")" in raw:
            raise ValueError(f"Linia {number}: błędny komentarz.")
        command = "".join(raw.upper().split())
        if not command or command == "%":
            continue
        if ended:
            raise ValueError(f"Linia {number}: kod po końcu programu.")
        words = WORD.findall(command)
        if "".join(letter + value for letter, value in words) != command:
            raise ValueError(f"Linia {number}: niedozwolona składnia.")
        values = {}
        codes = {"G": [], "M": []}
        normalized = []
        for letter, value in words:
            value_number = float(value)
            if not math.isfinite(value_number) or abs(value_number) > 100000:
                raise ValueError(f"Linia {number}: wartość poza zakresem.")
            if letter == "N":
                if value_number < 0 or not value_number.is_integer():
                    raise ValueError("Niepoprawny numer linii.")
                continue
            if letter in codes:
                allowed = G_CODES if letter == "G" else M_CODES
                if value_number not in allowed:
                    raise ValueError(
                        f"Linia {number}: {letter}{value} nieobsługiwane. "
                        "Użyj liniowego G-code GRBL, bez M6/probing/homing."
                    )
                codes[letter].append(int(value_number))
            elif letter in "XYZFSP":
                if letter in values:
                    raise ValueError(f"Linia {number}: powtórzone {letter}.")
                values[letter] = value_number
            else:
                raise ValueError(f"Linia {number}: słowo {letter} zabronione.")
            normalized.append(letter + value)
        if len(codes["M"]) > 1:
            raise ValueError("Jedna funkcja M na linię.")
        move_codes = [code for code in codes["G"] if code in (0, 1, 4)]
        if len(move_codes) > 1:
            raise ValueError("Jedna funkcja ruchu na linię.")
        modes.update(codes["G"])
        if move_codes and move_codes[0] in (0, 1):
            motion = move_codes[0]
        if "F" in values:
            feed = values["F"]
            if not 1 <= feed <= 300:
                raise ValueError("Posuw F musi być 1–300 mm/min.")
            max_feed = max(max_feed, feed)
        if "S" in values:
            power = values["S"]
            if not 0 <= power <= 1000:
                raise ValueError("Moc S musi być 0–1000; to nie RPM.")
            max_power = max(max_power, power)
        if 3 in codes["M"]:
            if power is None or power <= 0:
                raise ValueError("M3 wymaga wcześniejszej lub tej samej S>0.")
            spindle_on = True
        if 5 in codes["M"]:
            spindle_on = False
        axes = [axis for axis in point if axis in values]
        if 4 in move_codes:
            if axes or "P" not in values or not 0 <= values["P"] <= 10:
                raise ValueError("G4 wymaga P od 0 do 10 s, bez osi.")
        elif "P" in values:
            raise ValueError("P jest dostępne tylko dla G4.")
        if axes:
            if not {21, 90, 94, 54}.issubset(modes) or motion not in (0, 1):
                raise ValueError("Przed ruchem wymagane G21 G90 G94 G54.")
            if motion == 1 and feed is None:
                raise ValueError("G1 wymaga określonego posuwu F.")
            if first_move:
                if axes != ["Z"] or values["Z"] <= 0 or motion != 0:
                    raise ValueError("Pierwszy ruch: G0 Z>0, bez X/Y.")
                first_move = False
            if any(axis in axes for axis in ("X", "Y")):
                if point["X"] is None or point["Y"] is None:
                    if not {"X", "Y"}.issubset(values):
                        raise ValueError("Pierwszy ruch XY musi podać X i Y.")
            for axis in axes:
                point[axis] = values[axis]
                limits = bounds[axis]
                limits[0] = (values[axis] if limits[0] is None
                             else min(limits[0], values[axis]))
                limits[1] = (values[axis] if limits[1] is None
                             else max(limits[1], values[axis]))
        if 2 in codes["M"] or 30 in codes["M"]:
            if spindle_on:
                raise ValueError("Przed końcem programu wymagane M5.")
            ended = True
        normalized = "".join(normalized)
        if len(normalized) > 78:
            raise ValueError(f"Linia {number}: maksymalnie 78 znaków.")
        if normalized:
            lines.append({"source_line": number, "code": normalized})
        if len(lines) > 20000:
            raise ValueError("Limit: 20000 poleceń.")
    if first_move or point["X"] is None or point["Y"] is None:
        raise ValueError("Plik musi zawierać ruch Z i XY.")
    if spindle_on or not any(line["code"] == "M5" for line in lines):
        raise ValueError(
            "Wymagana osobna linia M5 i wyłączone wrzeciono na końcu."
        )
    for axis, maximum in (("X", 300), ("Y", 180), ("Z", 20)):
        low, high = bounds[axis]
        if low is not None and (low < -maximum or high > maximum):
            raise ValueError(f"Zakres {axis} przekracza limit ±{maximum} mm.")
    return {"name": name, "lines": lines, "bounds_mm": bounds,
            "max_feed": max_feed, "max_power": max_power}


class JobRunner:
    """One serial reader runs ticks; HTTP controls only queue state requests."""

    def __init__(self):
        self.lock = threading.RLock()
        self.program = None
        self.job_id = None
        self.state = "empty"
        self.acknowledged = 0
        self.pending = None
        self.error = None
        self.requested = None
        self.lease = None
        self.heartbeat_at = 0
        self.query_at = 0
        self.pending_at = 0
        self.receive = b""
        self.waiting_resume = False
        self.error_line = None

    def active(self):
        """Include held/draining jobs, so manual commands cannot interleave."""
        with self.lock:
            return self.state in ACTIVE

    def load(self, program):
        """Replace a validated in-memory program only when no job owns USB."""
        with self.lock:
            if self.active():
                raise ValueError("Najpierw zakończ lub przerwij zadanie.")
            self.program = program
            self.job_id = secrets.token_hex(12)
            self.state = "ready"
            self.acknowledged = 0
            self.error = None
            self.pending = None
            self.error_line = None

    def start(self, job_id):
        """Create a fresh browser lease; starting never happens implicitly."""
        with self.lock:
            if self.state not in ("ready", "completed", "stopped", "failed"):
                raise ValueError("Zadanie nie jest gotowe.")
            if self.program is None or job_id != self.job_id:
                raise ValueError("Plik się zmienił — odśwież podgląd.")
            self.state = "running"
            self.acknowledged = 0
            self.pending = None
            self.error = None
            self.requested = None
            self.receive = b""
            self.error_line = None
            self.waiting_resume = False
            self.query_at = 0
            self.lease = secrets.token_urlsafe(24)
            self.heartbeat_at = time.monotonic()
            return {"lease": self.lease}

    def clear(self):
        """Forget an inactive upload without any serial or filesystem access."""
        with self.lock:
            if self.active():
                raise ValueError("Najpierw przerwij aktywne zadanie.")
            self.program = None
            self.job_id = None
            self.state = "empty"
            self.acknowledged = 0
            self.pending = None
            self.error = None
            self.error_line = None
            self.lease = None

    def control(self, action, job_id=None):
        """Queue hold, explicit resume or abort for the serial worker."""
        with self.lock:
            if action == "pause" and self.state in ("running", "draining"):
                self.requested = "pause"
                self.state = "pausing"
                self.waiting_resume = False
            elif action == "resume" and self.state == "paused":
                if job_id != self.job_id:
                    raise ValueError("Plik się zmienił.")
                self.requested = "resume"
                self.state = "resuming"
                self.lease = secrets.token_urlsafe(24)
                self.heartbeat_at = time.monotonic()
                return {"lease": self.lease}
            elif action == "stop" and self.active():
                self.requested = "stop"
            else:
                raise ValueError("Akcja niedostępna w tym stanie zadania.")

    def heartbeat(self, lease):
        """Other viewers cannot keep an unattended job's owner lease alive."""
        with self.lock:
            if not isinstance(lease, str) or not self.lease or not (
                secrets.compare_digest(lease, self.lease)
            ):
                raise ValueError("Nieaktualna sesja zadania.")
            self.heartbeat_at = time.monotonic()

    def status(self):
        """Report accepted lines separately from physical job completion."""
        with self.lock:
            program = self.program
            total = len(program["lines"]) if program else 0
            source_line = self.error_line
            if self.pending is not None and program:
                source_line = program["lines"][self.pending]["source_line"]
            return {
                "id": self.job_id, "state": self.state,
                "name": program["name"] if program else None,
                "total": total, "acknowledged": self.acknowledged,
                "source_line": source_line, "error": self.error,
                "bounds_mm": program["bounds_mm"] if program else None,
                "max_feed": program["max_feed"] if program else None,
                "max_power": program["max_power"] if program else None,
            }

    def abort(self, controller, reason, state="failed"):
        """Attempt GRBL hold/reset, discard the stream and require reconnect."""
        with self.lock:
            try:
                if controller.port is not None:
                    controller.port.write(b"!\x18")
            except Exception:
                pass  # Lost USB cannot guarantee machine or spindle stop.
            self.state = state
            if self.pending is not None and self.program:
                command = self.program["lines"][self.pending]
                self.error_line = command["source_line"]
            self.error = reason + (
                " Sprawdź wrzeciono; połącz i ustaw zero ponownie."
            )
            self.pending = None
            self.requested = None
            self.lease = None
            controller._close(self.error)

    def tick(self, controller):
        """Nonblocking send-response pump, called only by the serial owner."""
        with self.lock:
            if not self.active():
                return
            now = time.monotonic()
            if controller.port is None:
                self.abort(controller, "Utrata połączenia USB.")
                return
            try:
                if self.requested == "stop":
                    self.abort(controller, "Przerwano zadanie.", "stopped")
                    return
                if self.requested == "resume":
                    if controller.report_time is None or (
                        now - controller.report_time > 2
                    ):
                        raise RuntimeError("Status nieaktualny; nie wznowiono.")
                    controller.port.write(b"~")
                    self.waiting_resume = True
                    self.pending_at = now
                    self.requested = None
                if self.state in ("running", "draining", "resuming"):
                    if now - self.heartbeat_at > 8:
                        self.requested = "pause"
                        self.state = "pausing"
                        self.waiting_resume = False
                        self.error = "Utrata kontaktu z przeglądarką — pauza."
                if self.requested == "pause":
                    controller.port.write(b"!")
                    self.requested = None
                available = controller.port.in_waiting
                if available:
                    self.receive += controller.port.read(min(available, 4096))
                    if len(self.receive) > 8192:
                        raise RuntimeError("Za długa odpowiedź sterownika.")
                    while b"\n" in self.receive:
                        raw, self.receive = self.receive.split(b"\n", 1)
                        line = raw.decode("ascii", errors="replace").strip()
                        if line.startswith("<"):
                            controller._accept_status(line)
                            machine = controller.report["state"]
                            if machine.startswith("Alarm"):
                                raise RuntimeError("Alarm sterownika.")
                            if machine not in (
                                "Idle", "Run", "Hold:0", "Hold:1"
                            ):
                                raise RuntimeError(
                                    "Nieoczekiwany stan: " + machine
                                )
                            if self.state == "pausing" and machine in (
                                "Hold:0", "Idle"
                            ):
                                self.state = "paused"
                            if machine.startswith("Hold") and self.state in (
                                "running", "draining"
                            ):
                                self.state = (
                                    "paused" if machine == "Hold:0"
                                    else "pausing"
                                )
                            if self.state == "resuming" and machine in (
                                "Run", "Idle"
                            ):
                                self.waiting_resume = False
                                self.state = "running"
                                self.error = None
                            if self.state == "draining" and machine == "Idle":
                                self.state = "completed"
                                self.lease = None
                        elif line == "ok":
                            if self.pending is None:
                                raise RuntimeError(
                                    "Nieoczekiwane potwierdzenie."
                                )
                            self.acknowledged += 1
                            self.pending = None
                        elif line.startswith(("error:", "ALARM:", "Grbl")):
                            raise RuntimeError(line)
                if now - self.query_at >= 0.5:
                    controller.port.write(b"?")
                    self.query_at = now
                if controller.report_time is None or (
                    now - controller.report_time > 3
                ):
                    raise RuntimeError("Brak aktualnego statusu CNC.")
                if self.pending is not None and self.state == "running":
                    if now - self.pending_at > 120:
                        raise RuntimeError(
                            "Brak potwierdzenia linii; bez ponawiania."
                        )
                if self.state == "running" and self.pending is None:
                    commands = self.program["lines"]
                    if self.acknowledged == len(commands):
                        # ok means accepted; only a subsequent Idle means done.
                        self.state = "draining"
                    else:
                        self.pending = self.acknowledged
                        code = commands[self.pending]["code"] + "\n"
                        controller.port.write(code.encode("ascii"))
                        self.pending_at = now
            except Exception as error:
                self.abort(controller, str(error))

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
