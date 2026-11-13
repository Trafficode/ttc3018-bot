# ---------------------------------------------------------------------------
# library.py
# 2026-11-08
# - Immutable, bounded manufacturing packages; no controller access.
# ---------------------------------------------------------------------------
"""Store CAD attachments and validated NC programs independently of jobs."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
from datetime import datetime, timezone

from monitor.jobs import parse_program

MAX_REQUEST = 16 * 1024 * 1024
MAX_PACKAGE = 10 * 1024 * 1024
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}")
HASH = re.compile(r"[a-f0-9]{64}")


def digest(data):
    """Hash the original bytes, before any program normalization."""
    return hashlib.sha256(data).hexdigest()


def validate_package(payload):
    """Validate the complete transaction before creating any stored files."""
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise ValueError("Nieobsługiwana wersja pakietu.")
    project = payload.get("project")
    if not isinstance(project, dict):
        raise ValueError("Brak metadanych projektu.")
    for key in ("id", "name", "revision", "boardHash", "side", "datum"):
        value = project.get(key)
        if not isinstance(value, str) or not 1 <= len(value) <= 160:
            raise ValueError("Niepoprawne metadane projektu.")
    if not HASH.fullmatch(project["boardHash"]):
        raise ValueError("Brak skrótu źródłowego PCB.")
    if project["side"] not in ("B.Cu", "F.Cu"):
        raise ValueError("Brak strony obróbki.")
    files = payload.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 24:
        raise ValueError("Pakiet musi zawierać od 1 do 24 plików.")
    names = set()
    total = 0
    records = []
    contents = {}
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Niepoprawny plik.")
        name = item.get("name", "")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError("Niedozwolona nazwa pliku.")
        if name.lower() in names or name == "manifest.json":
            raise ValueError("Powtórzona lub zastrzeżona nazwa pliku.")
        names.add(name.lower())
        try:
            data = base64.b64decode(item.get("content", ""), validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("Niepoprawne kodowanie pliku.") from error
        total += len(data)
        if not data or len(data) > 5 * 1024 * 1024 or total > MAX_PACKAGE:
            raise ValueError("Przekroczony rozmiar pakietu lub pusty plik.")
        if digest(data) != item.get("sha256"):
            raise ValueError("Suma kontrolna pliku nie odpowiada zawartości.")
        kind = item.get("kind")
        record = {"name": name, "kind": kind, "sha256": digest(data),
                  "bytes": len(data)}
        if kind == "program":
            try:
                program = parse_program(name, data.decode("ascii"))
            except UnicodeDecodeError as error:
                raise ValueError("Program musi być ASCII.") from error
            if payload.get("camConfirmed") is not True:
                raise ValueError("Potwierdź pochodzenie CAM programów.")
            record.update({key: program[key] for key in
                           ("bounds_mm", "max_feed", "max_power",
                            "z_feeds")})
            record["cam_profile"] = program.get("cam_profile")
            record["commands"] = len(program["lines"])
        elif kind != "cad" or not name.lower().endswith(".zip"):
            raise ValueError("Dozwolone są programy NC i archiwum CAD ZIP.")
        if kind == "cad":
            from monitor.project_bundle import bundle_summary
            machining = bundle_summary(data, project)
            if machining["version"] == 1:
                record["machining"] = machining
        records.append(record)
        contents[name] = data
    # Strip unknown fields. Stable ordering makes identical retries idempotent.
    manifest = {"schemaVersion": 1,
                "project": {key: project[key] for key in
                            ("id", "name", "revision", "boardHash",
                             "side", "datum")},
                "camConfirmed": payload.get("camConfirmed") is True,
                "files": sorted(records, key=lambda item: item["name"])}
    identity = json.dumps(manifest, sort_keys=True).encode()
    return digest(identity), manifest, contents


class PackageLibrary:
    """Atomic local collection. Import never loads a job or touches USB."""

    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()

    def _directory(self, package_id):
        if not isinstance(package_id, str) or not HASH.fullmatch(package_id):
            raise ValueError("Niepoprawny identyfikator pakietu.")
        directory = self.root / package_id
        if directory.is_symlink():
            raise ValueError("Niedozwolony katalog pakietu.")
        return directory

    def get(self, package_id):
        """Read stored metadata; original file hashes are checked on use."""
        directory = self._directory(package_id)
        try:
            manifest = json.loads((directory / "manifest.json").read_text())
        except (OSError, ValueError) as error:
            raise ValueError("Pakiet niedostępny lub uszkodzony.") from error
        if not isinstance(manifest, dict) or manifest.get("id") != package_id:
            raise ValueError("Zmieniony identyfikator pakietu.")
        try:
            identity = {key: manifest[key] for key in
                        ("schemaVersion", "project", "camConfirmed", "files")}
        except KeyError as error:
            raise ValueError("Niekompletne metadane pakietu.") from error
        if digest(json.dumps(identity, sort_keys=True).encode()) != package_id:
            raise ValueError("Metadane pakietu zostały zmienione.")
        return manifest

    def list(self):
        """Return bounded metadata only, never program contents."""
        if not self.root.exists():
            return []
        result = []
        for directory in self.root.iterdir():
            if HASH.fullmatch(directory.name):
                try:
                    result.append(self.get(directory.name))
                except ValueError:
                    result.append({"id": directory.name, "corrupt": True})
        return sorted(result, key=lambda item: item.get("receivedAt", ""),
                      reverse=True)

    def file(self, package_id, name):
        """Resolve only manifest entries and verify original bytes."""
        manifest = self.get(package_id)
        record = next((item for item in manifest["files"]
                       if item["name"] == name), None)
        if record is None or not NAME.fullmatch(name):
            raise ValueError("Nie znaleziono pliku w pakiecie.")
        filename = self._directory(package_id) / name
        if filename.is_symlink():
            raise ValueError("Niedozwolony plik pakietu.")
        try:
            data = filename.read_bytes()
        except OSError as error:
            raise ValueError("Plik pakietu jest niedostępny.") from error
        if len(data) != record["bytes"] or digest(data) != record["sha256"]:
            raise ValueError("Plik pakietu został zmieniony.")
        return record, data

    def program(self, package_id, name):
        """Revalidate at selection using the current authoritative parser."""
        record, data = self.file(package_id, name)
        if record["kind"] != "program":
            raise ValueError("CAD wymaga CAM; wybierz program G-code.")
        content = data.decode("ascii")
        parse_program(name, content)
        return {"name": name, "content": content}

    def import_package(self, payload):
        """Commit all files together; failures leave no visible partial job."""
        package_id, manifest, contents = validate_package(payload)
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination = self._directory(package_id)
            if destination.exists():
                existing = self.get(package_id)
                for record in existing["files"]:
                    self.file(package_id, record["name"])
                return {"package": existing, "duplicate": True}
            entries = self.list()
            used = sum(item["bytes"] for entry in entries
                       for item in entry.get("files", []))
            if len(entries) >= 200 or used + sum(map(len, contents.values())) > (
                256 * 1024 * 1024
            ):
                raise ValueError("Kolekcja jest pełna.")
            manifest.update({"id": package_id,
                             "receivedAt": datetime.now(
                                 timezone.utc).isoformat()})
            staging = Path(tempfile.mkdtemp(prefix=".incoming-",
                                            dir=self.root))
            try:
                for name, data in contents.items():
                    with (staging / name).open("xb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                with (staging / "manifest.json").open("x") as stream:
                    json.dump(manifest, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                staging.rename(destination)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            return {"package": manifest, "duplicate": False}

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
