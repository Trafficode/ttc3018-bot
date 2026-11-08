# ---------------------------------------------------------------------------
# library_http.py
# 2026-11-08
# - Separate collection-only ingestion credential and operator file selection.
# ---------------------------------------------------------------------------
"""Collection endpoints never expose controller actions to ingestion clients."""

import json
import os
from pathlib import Path
import secrets
from urllib.parse import unquote, urlsplit

from monitor.library import MAX_REQUEST


def integration_token():
    """Read a private token file; missing configuration disables ingestion."""
    filename = os.environ.get("PILOMILL_LIBRARY_TOKEN_FILE")
    if not filename:
        filename = str(Path.home() / ".local/share/bark-beetle/library.token")
    try:
        token = Path(filename).read_text().strip()
    except OSError:
        return ""
    return token if len(token) >= 32 else ""


def library_request(handler):
    """Handle a bounded collection route, or return False to the server."""
    path = urlsplit(handler.path).path
    if not path.startswith("/api/library"):
        return False

    def respond(status, payload):
        handler.respond(status, "application/json", json.dumps(
            payload, ensure_ascii=False).encode())

    bearer = handler.headers.get("Authorization", "")
    configured = integration_token()
    importing = (handler.command == "POST"
                 and path == "/api/library/packages")
    if importing:
        allowed = bool(configured) and secrets.compare_digest(
            bearer, "Bearer " + configured)
    else:
        supplied = handler.headers.get("X-PiloMill-Token", "")
        allowed = secrets.compare_digest(
            supplied, handler.server.control_token)
    if not allowed:
        respond(403, {"error": "Brak uprawnienia do kolekcji."})
        return True
    try:
        library = handler.server.library
        if handler.command == "GET" and path == "/api/library":
            respond(200, {"packages": library.list()})
        elif importing or (handler.command == "POST"
                           and path == "/api/library/select"):
            if not importing:
                origin = urlsplit(handler.headers.get("Origin", ""))
                if origin.netloc != handler.headers.get("Host"):
                    raise ValueError("Wybór pliku wymaga tej samej strony.")
            size = int(handler.headers.get("Content-Length", "0"))
            limit = MAX_REQUEST if importing else 2048
            if not 1 <= size <= limit:
                raise ValueError("Niepoprawny rozmiar żądania.")
            if handler.headers.get("Content-Type") != "application/json":
                raise ValueError("Wymagany JSON.")
            payload = json.loads(handler.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Wymagany obiekt JSON.")
            if importing:
                respond(200, library.import_package(payload))
            else:
                program = library.program(payload.get("packageId"),
                                          payload.get("name"))
                # The normal job loader enforces all active/probing interlocks
                # and invalidates the old surface map. It never opens USB.
                handler.server.cnc.action("job_load", program)
                respond(200, {"ok": True})
        elif handler.command == "GET" and path.startswith(
            "/api/library/files/"
        ):
            parts = path.removeprefix("/api/library/files/").split("/")
            if len(parts) != 2:
                raise ValueError("Niepoprawny adres pliku.")
            record, data = library.file(parts[0], unquote(parts[1]))
            content_type = ("application/zip" if record["kind"] == "cad"
                            else "text/plain")
            handler.respond(200, content_type, data)
        else:
            respond(404, {"error": "Nieznana operacja kolekcji."})
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        respond(400, {"error": str(error)})
    except RuntimeError as error:
        respond(409, {"error": str(error)})
    except OSError:
        respond(503, {"error": "Nie można zapisać lub odczytać kolekcji."})
    return True

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
