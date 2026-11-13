# ---------------------------------------------------------------------------
# cam_http.py
# 2026-11-13
# - Operator-only CAM preparation, readback and explicit program loading.
# ---------------------------------------------------------------------------
"""Collection ingestion credentials cannot compute, select or execute CAM."""

import json
import secrets
from urllib.parse import urlsplit


def cam_request(handler):
    """Handle CAM routes before generic machine actions."""
    path = urlsplit(handler.path).path
    if not path.startswith("/api/cam"):
        return False

    def respond(status, payload):
        handler.respond(status, "application/json", json.dumps(
            payload, ensure_ascii=False).encode())

    supplied = handler.headers.get("X-PiloMill-Token", "")
    if not supplied or not secrets.compare_digest(
        supplied, handler.server.control_token
    ):
        respond(403, {"error": "Brak uprawnienia operatora."})
        return True
    try:
        collection = handler.server.cam
        cnc = handler.server.cnc
        status = cnc.status()
        profile = status.get("calibration_profiles", {}).get("selected", {})
        if handler.command == "GET" and path == "/api/cam":
            programs = collection.list(profile)
            for item in programs:
                if item.get("processProfile"):
                    try:
                        handler.server.process_profiles.assert_snapshot(
                            item["processProfile"])
                    except ValueError:
                        item["stale"] = True
            respond(200, {"programs": programs})
        elif handler.command == "GET" and path.startswith("/api/cam/preview/"):
            respond(200, collection.preview(path.split("/")[-1]))
        elif handler.command == "GET" and path.startswith("/api/cam/flow/"):
            with collection.lock:
                respond(200, handler.server.pcb_progress.read(
                    path.split("/")[-1], status))
        elif handler.command == "POST" and path in (
            "/api/cam/prepare", "/api/cam/cancel", "/api/cam/select",
            "/api/cam/load-stage"
        ):
            origin = urlsplit(handler.headers.get("Origin", ""))
            if origin.netloc != handler.headers.get("Host"):
                raise ValueError("Wymagana ta sama strona.")
            size = int(handler.headers.get("Content-Length", "0"))
            if not 1 <= size <= 4096 or (
                handler.headers.get("Content-Type") != "application/json"
            ):
                raise ValueError("Wymagany krótki JSON.")
            payload = json.loads(handler.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Wymagany obiekt JSON.")
            if path == "/api/cam/prepare":
                # Heavy computation is available only with USB disconnected.
                # This cannot affect the sender's timing or an active machine.
                if status.get("connected") or status.get("job", {}).get(
                    "state") in ("running", "paused", "pausing", "resuming",
                                 "draining") or status.get("probing"):
                    raise RuntimeError("Rozłącz CNC przed obliczaniem CAM.")
                if payload.get("processProfileId") or (
                    "processProfiles" in payload
                ):
                    recipe, workflow, clearance = (
                        handler.server.process_profiles.resolve(
                            payload, profile))
                    payload = {**payload, "workflow": workflow,
                               "clearanceMm": clearance}
                    respond(202, collection.start(payload, profile, recipe))
                else:
                    respond(202, collection.start(payload, profile))
            elif path == "/api/cam/cancel":
                respond(200, collection.cancel(payload.get("id")))
            elif path == "/api/cam/load-stage":
                respond(200, handler.server.pcb_progress.load(
                    payload.get("id"), payload, cnc))
            else:
                if collection.get(payload.get("id")).get("workflow"):
                    raise ValueError("Wczytaj bieżący etap zlecenia PCB.")
                program = collection.program(payload.get("id"), profile)
                # Existing job loader owns machine interlocks and invalidates
                # the previous height map. Loading never starts execution.
                cnc.action("job_load", program)
                respond(200, {"ok": True})
        else:
            respond(404, {"error": "Nieznana operacja CAM."})
    except (ValueError, TypeError, KeyError, StopIteration) as error:
        respond(400, {"error": str(error) or "Niekompletne dane CAM."})
    except RuntimeError as error:
        respond(409, {"error": str(error)})
    except OSError:
        respond(503, {"error": "Kolekcja CAM jest niedostępna."})
    return True

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
