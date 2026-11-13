# ---------------------------------------------------------------------------
# pcb_projects_http.py
# 2026-11-13
# - Operator-only independent PCB stage preparation and explicit tool loading.
# ---------------------------------------------------------------------------
"""Ingestion credentials grant no access to project execution preparation."""

import json
import secrets
from urllib.parse import parse_qs, urlsplit


def pcb_project_request(handler):
    """Use the existing operator token and same-origin bounded JSON contract."""
    url = urlsplit(handler.path)
    if not url.path.startswith("/api/pcb-projects"):
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
        store = handler.server.pcb_projects
        if handler.command == "GET" and url.path == "/api/pcb-projects":
            package = parse_qs(url.query).get("packageId", [None])[0]
            respond(200, {"runs": store.list(package)})
            return True
        if handler.command != "POST" or url.path not in (
            "/api/pcb-projects/prepare", "/api/pcb-projects/load"
        ):
            respond(404, {"error": "Nieznana operacja projektu PCB."})
            return True
        if urlsplit(handler.headers.get("Origin", "")).netloc != (
            handler.headers.get("Host")
        ):
            raise ValueError("Wymagana ta sama strona.")
        length = int(handler.headers.get("Content-Length", "0"))
        if not 1 <= length <= 4096 or handler.headers.get(
            "Content-Type") != "application/json":
            raise ValueError("Wymagany krótki JSON.")
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("Wymagany obiekt JSON.")
        if url.path.endswith("/prepare"):
            respond(202, store.prepare(payload))
        else:
            respond(200, store.load(payload))
    except (ValueError, TypeError, KeyError) as error:
        respond(400, {"error": str(error) or "Niekompletne dane projektu."})
    except RuntimeError as error:
        respond(409, {"error": str(error)})
    except OSError:
        respond(503, {"error": "Przygotowanie projektu jest niedostępne."})
    return True

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
