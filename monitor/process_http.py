# ---------------------------------------------------------------------------
# process_http.py
# 2026-11-13
# - Operator-only recipe editing; never invokes controller execution actions.
# ---------------------------------------------------------------------------
"""Shared workstation profiles replace repeated browser-only tool settings."""

import json
import secrets
from urllib.parse import urlsplit


def process_request(handler):
    """Handle bounded profile reads/saves with the normal operator token."""
    path = urlsplit(handler.path).path
    if not path.startswith("/api/pcb-profiles"):
        return False

    def respond(status, value):
        handler.respond(status, "application/json", json.dumps(
            value, ensure_ascii=False).encode())

    token = handler.headers.get("X-PiloMill-Token", "")
    if not token or not secrets.compare_digest(
        token, handler.server.control_token
    ):
        respond(403, {"error": "Brak uprawnienia operatora."})
        return True
    try:
        store = handler.server.process_profiles
        if handler.command == "GET" and path == "/api/pcb-profiles":
            respond(200, store.status())
            return True
        if handler.command != "POST" or path not in (
            "/api/pcb-profiles/save", "/api/pcb-profiles/select"
        ):
            respond(404, {"error": "Nieznana operacja profilu PCB."})
            return True
        origin = urlsplit(handler.headers.get("Origin", ""))
        if origin.netloc != handler.headers.get("Host"):
            raise ValueError("Wymagana ta sama strona.")
        size = int(handler.headers.get("Content-Length", "0"))
        if not 1 <= size <= 8192 or handler.headers.get(
            "Content-Type") != "application/json":
            raise ValueError("Wymagany krótki JSON.")
        payload = json.loads(handler.rfile.read(size))
        if not isinstance(payload, dict):
            raise ValueError("Wymagany obiekt JSON.")
        # Use the same lock as Start so a recipe cannot change between the
        # execution snapshot check and the sender entering its running state.
        with handler.server.cnc.lock:
            status = handler.server.cnc.status()
            if status.get("job", {}).get("state") in (
                "running", "paused", "pausing", "draining", "resuming"
            ) or status.get("z_probe", {}).get("active") or status.get(
                "calibration", {}).get("job", {}).get("state") in (
                    "running", "paused", "pausing", "draining", "resuming"):
                raise ValueError("Zakończ aktywną obróbkę lub pomiar.")
            if path.endswith("/save"):
                selected = status.get("calibration_profiles", {}).get(
                    "selected", {})
                respond(200, store.save(payload, selected))
            else:
                recipe = store.get(payload.get("id"))
                if recipe["fingerprint"] != payload.get("fingerprint"):
                    raise ValueError("Profil zmienił się; odśwież dane.")
                reference = recipe.get("isolation")
                if "kind" in payload and payload["kind"] not in (
                    "drilling", "outline"
                ):
                    raise ValueError("Niepoprawny rodzaj profilu.")
                if reference is None or payload.get("kind"):
                    respond(200, store.select(payload))
                    return True
                available = status.get("calibration_profiles", {}).get(
                    "profiles", [])
                if not any(value.get("id") == reference["id"] and value.get(
                    "fingerprint") == reference["fingerprint"]
                           for value in available):
                    raise ValueError("Kalibracja frezu V zmieniła się; "
                                     "zaktualizuj profil obróbki.")
                handler.server.cnc.action("profile_select", {
                    "profile_id": reference["id"]})
                respond(200, store.select(payload))
    except (ValueError, TypeError, KeyError) as error:
        respond(400, {"error": str(error)})
    except OSError:
        respond(503, {"error": "Nie można zapisać profilu PCB."})
    return True

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
