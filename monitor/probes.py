# ---------------------------------------------------------------------------
# probes.py
# 2026-10-18
# - Bounded, explicit Z probing through the existing exclusive serial owner.
# ---------------------------------------------------------------------------
"""A single copper touch sets G54 Z, then retracts; never starts itself."""

import math
import secrets
import time


ACTIVE = {
    "starting", "probing", "contact_wait", "zero_ack", "retract_ack",
    "retract_wait",
    "no_contact_wait",
}


def probe_target_z(target):
    """Round toward the surface so the commanded descent never exceeds its cap."""
    return math.ceil(target * 10000 - 1e-9) / 10000


class ZProbe:
    """Nonblocking worker state; Controller.lock protects every operation."""

    def __init__(self):
        self.state = "idle"
        self.error = None
        self.lease = None
        self.heartbeat_at = 0
        self.deadline = 0
        self.query_at = 0
        self.receive = b""
        self.contact = None
        self.cancel_requested = False
        self.command = None
        self.start_machine = None
        self.completed_job_id = None
        self.completed_offset = None
        self.attempt = None
        self.recoverable_miss = False
        self.missed = False
        self.miss_position = None
        self.attempt_offset = None
        self.probe_limits = None

    def active(self):
        """Retain USB ownership through contact, zeroing and retraction."""
        return self.state in ACTIVE

    def status(self):
        """Expose phase and outcome, never the browser lease."""
        return {"kind": "point", "state": self.state, "active": self.active(),
                "job_id": self.completed_job_id,
                "error": self.error, "attempt": self.attempt}

    def record_attempt(self, position, target, feed, *, phase="reference", point=None, offset=None):
        """Retain the exact attempted travel for recovery, never infer a gap."""
        self.attempt = {"phase": phase, "point": point, "start": list(position),
                        "targetZ": target, "distanceMm": position[2]-target,
                        "feedMmMin": feed}
        self.attempt_offset = list(offset) if offset is not None else None

    def start(self, controller, payload, *, recoverable_miss=False):
        """Validate fresh physical state before queuing a bounded descent."""
        self.completed_job_id = None
        self.completed_offset = None
        if payload.get("confirmed") is not True:
            raise ValueError("Wymagane potwierdzenie sondowania.")
        distance = float(payload.get("distance", 0))
        if not math.isfinite(distance) or not 0.1 <= distance <= 10:
            raise ValueError("Droga sondowania: 0,1–10 mm.")
        limits = controller.probe_settings.snapshot(payload)
        feed = limits["z_feed_mm_min"]
        if controller.port is None or controller.jobs.active():
            raise ValueError("Połącz CNC i zakończ program.")
        controller._status()
        report = controller.report
        if report["state"] != "Idle":
            raise ValueError("Sondowanie wymaga stanu Idle.")
        if not controller.probe_tested or report["probe_triggered"]:
            raise ValueError("Sprawdź zwarcie sondy, potem rozewrzyj styk.")
        settings = {}
        for line in controller.info:
            if line.startswith("$") and "=" in line:
                key, value = line.split("=", 1)
                settings[key] = float(value)
        # This DLC32 installation reports contact with the opposite polarity.
        # Keep display and G38.2 semantics aligned in firmware, not in the UI.
        if settings.get("$6") != 1 or settings.get("$13") != 0:
            raise ValueError("Ta frezarka wymaga $6=1 i $13=0.")
        position = report.get("position")
        machine = report.get("MPos")
        expected = payload.get("position")
        if position is None or machine is None:
            raise ValueError("Brak pozycji roboczej lub MPos; nie rozpoczęto.")
        if not isinstance(expected, list) or len(expected) != 3:
            raise ValueError("Odśwież pozycję przed potwierdzeniem.")
        for actual, before in zip(position, expected):
            if not isinstance(before, (int, float)) or (
                not math.isfinite(before) or abs(actual - before) > 0.002
            ):
                raise ValueError("Pozycja zmieniła się; potwierdź ponownie.")
        modal = controller._line("$G")
        tokens = []
        for line in modal:
            if line.startswith("[GC:") and line.endswith("]"):
                tokens = line[4:-1].split()
        if not {"G54", "G21", "G90", "G94", "M5"}.issubset(tokens):
            raise ValueError("Wymagane G54 G21 G90 G94 i M5.")
        self.state = "starting"
        self.error = None
        self.contact = None
        self.receive = b""
        self.cancel_requested = False
        self.recoverable_miss = recoverable_miss
        self.missed = False
        self.miss_position = None
        self.start_machine = machine[:]
        self.probe_limits = limits
        target = probe_target_z(position[2] - min(distance, limits["max_descent_mm"]))
        self.distance = position[2] - target
        mode = 'G38.3' if self.recoverable_miss else 'G38.2'
        self.command = f"G90{mode}Z{target:.4f}F{feed:g}"
        self.record_attempt(position, target, feed, offset=controller.offset)
        self.lease = secrets.token_urlsafe(24)
        self.heartbeat_at = time.monotonic()
        self.deadline = self.heartbeat_at + self.distance / feed * 60 + 8
        self.query_at = 0
        return {"probe_lease": self.lease}

    def heartbeat(self, lease):
        """Only the operator browser that started the probe keeps it alive."""
        if not self.active() or not isinstance(lease, str) or (
            not self.lease or not secrets.compare_digest(lease, self.lease)
        ):
            raise ValueError("Nieprawidłowa sesja sondowania.")
        self.heartbeat_at = time.monotonic()

    def cancel(self):
        """Queue immediate abort for the serial owner; never resume a probe."""
        if self.active():
            self.cancel_requested = True

    def abort(self, controller, reason, state="failed"):
        """Reset and close on uncertain motion; never assign zero on failure."""
        try:
            if controller.port is not None:
                controller.port.write(b"!\x18")
        except Exception:
            pass
        self.state = state
        self.error = reason + " Sprawdź maszynę; połącz i ustaw zero ponownie."
        self.lease = None
        controller._close(self.error)

    def _write(self, controller, command, state):
        controller.port.write((command + "\n").encode("ascii"))
        self.state = state

    def _accept(self, controller, line):
        if line.startswith(("error:", "ALARM:", "Grbl")):
            raise RuntimeError(line)
        if line.startswith("[PRB:"):
            if self.state != "probing" or self.contact is not None:
                raise RuntimeError("Nieoczekiwany wynik sondowania.")
            coordinates, success = line[5:-1].rsplit(":", 1)
            point = [float(value) for value in coordinates.split(",")]
            if not line.endswith("]") or success not in ("0", "1") or (
                len(point) != 3 or not all(math.isfinite(v) for v in point)
            ):
                raise RuntimeError("Sondowanie nie potwierdziło kontaktu.")
            if any(abs(point[i] - self.start_machine[i]) > 0.01
                   for i in (0, 1)):
                raise RuntimeError("Zmiana X/Y podczas sondowania.")
            target = self.start_machine[2]
            if not target - self.distance - 0.01 <= point[2] <= target:
                raise RuntimeError("Kontakt poza drogą sondowania.")
            if success == "0":
                if not self.recoverable_miss:
                    raise RuntimeError("Sondowanie nie potwierdziło kontaktu.")
                if self.missed or abs(point[2]-(target-self.distance)) > .01:
                    raise RuntimeError("Niespójny koniec zjazdu bez styku.")
                self.missed = True
                self.miss_position = point
                return
            self.contact = point
        elif line == "ok":
            if self.state == "probing" and self.missed:
                self.state = "no_contact_wait"
            elif self.state == "probing" and self.contact is not None:
                self.state = "contact_wait"
            elif self.state == "zero_ack":
                controller.offset = None
                # G10 changes G54; a subsequent status refreshes the WCO.
                self._write(controller, "G0Z1", "retract_ack")
            elif self.state == "retract_ack":
                self.state = "retract_wait"
            else:
                raise RuntimeError("Nieoczekiwane potwierdzenie sondowania.")
            self.query_at = 0
        elif line.startswith("<"):
            controller._accept_status(line)
            report = controller.report
            if report["state"] not in ("Idle", "Run"):
                raise RuntimeError("Sondowanie przerwane: " + report["state"])
            machine = report.get("MPos")
            if machine is not None and any(
                abs(machine[i] - self.start_machine[i]) > 0.01
                for i in (0, 1)
            ):
                raise RuntimeError("Zmiana X/Y podczas sondowania.")
            if report["state"] != "Idle":
                return
            if self.state == "no_contact_wait":
                if machine is None or self.miss_position is None or any(
                    abs(a-b) > .01 for a, b in zip(machine, self.miss_position)
                ) or self.attempt_offset is None or controller.offset is None or any(
                    abs(a-b) > .002 for a, b in zip(controller.offset, self.attempt_offset)
                ) or report["probe_triggered"]:
                    raise RuntimeError("Nie potwierdzono bezczynności i pozycji po zjeździe bez styku.")
                self.state = "failed"
                self.error = "PROBE_NO_CONTACT — Nie wykryto styku z miedzią w dozwolonym zjeździe. Ustaw frez nad miedzią i ponów etap."
                self.lease = None
                controller.surface.invalidate(self.error)
                return
            if self.state == "contact_wait":
                machine = report.get("MPos")
                if machine is None:
                    raise RuntimeError("Brak MPos po kontakcie.")
                # PRB captures the touch, MPos the eventual stopped position.
                # Preserve their difference instead of zeroing the overshoot.
                delta = machine[2] - self.contact[2]
                if not -0.2 <= delta <= 0.01:
                    raise RuntimeError("Niespójna pozycja po kontakcie.")
                self._write(controller, f"G10L20P1Z{delta:.4f}", "zero_ack")
                self.deadline = time.monotonic() + 12
            elif self.state == "retract_wait":
                position = report.get("position")
                if position is not None and abs(position[2] - 1) <= 0.01:
                    if report["probe_triggered"]:
                        raise RuntimeError("Sonda nadal aktywna po odsunięciu.")
                    self.state = "completed"
                    self.completed_job_id = controller.jobs.job_id
                    self.completed_offset = list(controller.offset) if (
                        getattr(controller, "offset", None) is not None
                    ) else None
                    self.lease = None

    def tick(self, controller):
        """Run bounded read/write work without blocking HTTP cancellation."""
        if not self.active():
            return
        now = time.monotonic()
        if self.cancel_requested:
            self.abort(controller, "Przerwano sondowanie.", "stopped")
            return
        try:
            if controller.port is None:
                raise RuntimeError("Utrata USB podczas sondowania.")
            if now - self.heartbeat_at > 8:
                raise RuntimeError("Utrata kontaktu z przeglądarką.")
            if now > self.deadline:
                raise RuntimeError("Przekroczono czas sondowania.")
            if controller.report_time is None or (
                now - controller.report_time > 3
            ):
                raise RuntimeError("Brak aktualnego statusu CNC.")
            if self.state == "starting":
                self._write(controller, self.command, "probing")
            available = controller.port.in_waiting
            if available:
                self.receive += controller.port.read(min(available, 4096))
                if len(self.receive) > 8192:
                    raise RuntimeError("Za długa odpowiedź sondy.")
                while b"\n" in self.receive:
                    raw, self.receive = self.receive.split(b"\n", 1)
                    self._accept(controller, raw.decode("ascii").strip())
            if self.active() and now - self.query_at >= 0.2:
                controller.port.write(b"?")
                self.query_at = now
            if controller.report_time is None or (
                now - controller.report_time > 3
            ):
                raise RuntimeError("Brak aktualnego statusu CNC.")
        except Exception as error:
            self.abort(controller, str(error))

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
