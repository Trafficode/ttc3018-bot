# ---------------------------------------------------------------------------
# cam.py
# 2026-11-13
# - Freeze selected machining stages independently of unrelated V-bit models.
# ---------------------------------------------------------------------------
"""Two logical stores: source packages remain untouched by generated results."""

import copy
from datetime import datetime, timezone
import json
import math
import os
import re
from pathlib import Path
import secrets
import subprocess
import sys
import threading

from monitor.jobs import parse_program
from monitor.library import HASH, digest
from monitor.profiles import check_cam_program, fingerprint

ENGINE = "bark-planar-isolation/1;gerbonara/1.6.3;shapely/2.2.0"
ROOT = Path(__file__).resolve().parent.parent


def implementation_hashes():
    """Pin every geometry, output-validator and tool-model implementation."""
    return {name: digest((ROOT / "monitor" / name).read_bytes())
            for name in ("cam_geometry.py", "cam_worker.py", "jobs.py",
                         "profiles.py", "pcb_flow.py")}


def write_json(filename, value):
    """Atomically replace one small lifecycle record."""
    temporary = filename.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(filename)


class CamCollection:
    """One sandboxed worker at a time; only explicit selection reaches CNC."""

    def __init__(self, root, library):
        self.root = Path(root)
        self.library = library
        self.lock = threading.RLock()
        self.process = None
        self.current = None
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for directory in self.root.iterdir():
            if HASH.fullmatch(directory.name):
                try:
                    item = self.get(directory.name)
                    if item["state"] == "running":
                        self._stop_unit(item["unit"])
                        item.update(state="interrupted", error=(
                            "Obliczanie przerwane przez restart; "
                            "uruchom ponownie."))
                        write_json(directory / "manifest.json", item)
                except (OSError, ValueError, KeyError):
                    pass

    def directory(self, item_id):
        """Resolve an identifier, never a client-supplied filesystem path."""
        if not isinstance(item_id, str) or not HASH.fullmatch(item_id):
            raise ValueError("Niepoprawny identyfikator CAM.")
        directory = self.root / item_id
        if directory.is_symlink():
            raise ValueError("Niedozwolony katalog CAM.")
        return directory

    def get(self, item_id):
        """Read an attempt and verify every finalized artifact on use."""
        directory = self.directory(item_id)
        item = json.loads((directory / "manifest.json").read_text("utf-8"))
        if item.get("id") != item_id:
            raise ValueError("Uszkodzony zapis CAM.")
        if item.get("state") in ("ready", "blocked") and not (
            item.get("evidenceHash") and item.get("artifacts")
        ):
            raise ValueError("Brak integralności wyniku CAM.")
        for name, expected in item.get("artifacts", {}).items():
            if name not in ("isolation.nc", "preview.json", "request.json",
                            "source.zip", "result.json", "outline.nc") and not (
                re.fullmatch(r"drill-\d{2}\.nc", name)
            ):
                raise ValueError("Niepoprawny artefakt CAM.")
            filename = directory / name
            if filename.is_symlink() or (
                digest(filename.read_bytes()) != expected
            ):
                raise ValueError("Artefakt CAM został zmieniony.")
        if item.get("evidenceHash"):
            evidence = {key: value for key, value in item.items()
                        if key != "evidenceHash"}
            if digest(json.dumps(evidence, sort_keys=True).encode()) != (
                item["evidenceHash"]
            ):
                raise ValueError("Metadane wyniku CAM zostały zmienione.")
        return item

    def list(self, profile):
        """Expose history with freshness derived from the current profile."""
        result = []
        with self.lock:
            for directory in self.root.iterdir():
                if not HASH.fullmatch(directory.name):
                    continue
                try:
                    item = self.get(directory.name)
                    item["stale"] = (not item.get("workflow") and
                        item["profile"]["fingerprint"] !=
                        profile.get("fingerprint")) or item.get(
                            "implementationHashes") != implementation_hashes()
                    result.append(item)
                except (OSError, ValueError, KeyError):
                    result.append({"id": directory.name, "state": "corrupt"})
        return sorted(result, key=lambda item: item.get("createdAt", ""),
                      reverse=True)

    def start(self, payload, profile, process_profile=None):
        """Capture exact inputs before starting a single bounded subprocess."""
        workflow = None
        if payload.get("workflow") is not None:
            from monitor.pcb_flow import selected_operations, validate_flow
            workflow = validate_flow(payload["workflow"])
        needs_isolation = workflow is None or "isolation" in (
            selected_operations(workflow))
        if needs_isolation and (
            not profile.get("model") or "depth" not in profile
        ):
            raise ValueError("Wybierz zmierzony profil ze stałą głębokością.")
        if needs_isolation and (
            profile.get("fingerprint") != fingerprint(profile) or
            payload.get("profileFingerprint") != profile["fingerprint"]
        ):
            raise ValueError("Profil zmienił się; odśwież kolekcję.")
        clearance = payload.get("clearanceMm")
        if isinstance(clearance, bool) or not isinstance(
            clearance, (int, float)
        ) or not math.isfinite(clearance) or not 1 <= clearance <= 10:
            raise ValueError("Wycofanie Z: wpisz 1–10 mm.")
        if payload.get("confirmedDatum") is not True:
            raise ValueError("Potwierdź stronę obróbki i wspólne zero.")
        package = self.library.get(payload.get("packageId"))
        if package["project"]["datum"] != (
            "KiCad absolute board datum; shared copper, drills and outline"
        ):
            raise ValueError("Nieobsługiwany układ współrzędnych pakietu.")
        record, data = self.library.file(package["id"], payload.get("name"))
        if record["kind"] != "cad":
            raise ValueError("Wybierz pakiet CAD.")
        request = {"packageId": package["id"], "sourceSha256": record["sha256"],
                   "project": package["project"],
                   "profile": copy.deepcopy(profile) if needs_isolation else {},
                   "clearanceMm": clearance, "engine": ENGINE}
        request["implementationHashes"] = implementation_hashes()
        if process_profile:
            request["processProfile"] = copy.deepcopy(process_profile)
        if workflow is not None:
            request["workflow"] = workflow
        with self.lock:
            if self.current:
                raise RuntimeError("RPi już oblicza program CAM.")
            entries = list(self.root.iterdir())
            used = sum(file.stat().st_size for entry in entries
                       if entry.is_dir() for file in entry.iterdir()
                       if file.is_file())
            if len(entries) >= 100 or used + 32 * 1024 * 1024 > (
                512 * 1024 * 1024
            ):
                raise ValueError("Kolekcja CAM jest pełna.")
            item_id = digest(json.dumps(request, sort_keys=True).encode()
                             + secrets.token_bytes(16))
            directory = self.directory(item_id)
            directory.mkdir(mode=0o700)
            (directory / "source.zip").write_bytes(data)
            write_json(directory / "request.json", request)
            item = {**request, "id": item_id, "state": "running",
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "unit": "bark-cam-" + item_id[:16]}
            write_json(directory / "manifest.json", item)
            self.current = item_id
            threading.Thread(target=self._run, args=(item_id,),
                             daemon=True).start()
            return item

    def _run(self, item_id):
        """PrivateDevices denies USB; timeout/cancel kills the entire unit."""
        directory = self.directory(item_id)
        item = self.get(item_id)
        command = ["systemd-run", "--user", "--quiet", "--wait", "--pipe",
                   "--collect", "--unit=" + item["unit"],
                   "--setenv=OPENBLAS_NUM_THREADS=1",
                   "--setenv=OMP_NUM_THREADS=1",
                   "-p", "PrivateDevices=yes", "-p", "NoNewPrivileges=yes",
                   "-p", "PrivateNetwork=yes", "-p", "MemoryMax=1536M",
                   "-p", "CPUQuota=75%", "-p", "TasksMax=32",
                   "-p", "RuntimeMaxSec=180", "-p", "KillMode=control-group",
                   "-p", "WorkingDirectory=" + str(ROOT),
                   sys.executable, "-m",
                   "monitor.cam_worker", str(directory)]
        try:
            with (directory / "worker.log").open("wb") as log:
                with self.lock:
                    if self.get(item_id)["state"] == "cancelled":
                        return
                    process = subprocess.Popen(command, stdout=log,
                                               stderr=subprocess.STDOUT)
                    self.process = process
                try:
                    code = process.wait(timeout=195)
                except subprocess.TimeoutExpired:
                    self._stop_unit(item["unit"])
                    process.kill()
                    process.wait(timeout=5)
                    raise ValueError("Przekroczono limit czasu CAM.")
            with self.lock:
                latest = self.get(item_id)
                if latest["state"] == "cancelled":
                    return
                if code or not (directory / "result.json").exists():
                    raise ValueError("Silnik CAM lub jego izolacja jest "
                                     "niedostępna. Sprawdź dziennik usługi.")
                result = json.loads((directory / "result.json").read_text())
                item.update(result)
                if item["state"] not in ("ready", "blocked", "failed"):
                    raise ValueError("Niepoprawny wynik silnika CAM.")
                names = ["request.json", "source.zip", "result.json"]
                if (directory / "preview.json").exists():
                    names.append("preview.json")
                if item["state"] == "ready":
                    from monitor.pcb_flow import selected_operations
                    if not item.get("workflow") or "isolation" in (
                        selected_operations(item["workflow"])
                    ):
                        program = parse_program("isolation.nc", (
                            directory / "isolation.nc").read_text("ascii"))
                        check_cam_program(item["profile"], program, {})
                        names.append("isolation.nc")
                    for operation in item.get("report", {}).get(
                        "sequence", []
                    ):
                        name = operation["file"]
                        parse_program(name, (directory / name).read_text(
                            "ascii"))
                        if name not in names:
                            names.append(name)
                item["artifacts"] = {
                    name: digest((directory / name).read_bytes())
                    for name in names}
                item["evidenceHash"] = digest(json.dumps(
                    item, sort_keys=True).encode())
                write_json(directory / "manifest.json", item)
        except Exception as error:
            with self.lock:
                if self.get(item_id)["state"] != "cancelled":
                    item.update(state="failed", error=str(error)[:500])
                    item.pop("evidenceHash", None)
                    write_json(directory / "manifest.json", item)
        finally:
            with self.lock:
                self.current = None
                self.process = None

    @staticmethod
    def _stop_unit(unit):
        subprocess.run(["systemctl", "--user", "stop", unit], timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def cancel(self, item_id):
        """Cancel computation only; never send a CNC stop or reset."""
        with self.lock:
            item = self.get(item_id)
            if item_id != self.current or item["state"] != "running":
                raise ValueError("Te obliczenia nie są uruchomione.")
            item["state"] = "cancelled"
            write_json(self.directory(item_id) / "manifest.json", item)
        self._stop_unit(item["unit"])
        return item

    def preview(self, item_id):
        """Return only finalized, hash-checked geometry."""
        item = self.get(item_id)
        if "preview.json" not in item.get("artifacts", {}):
            raise ValueError("Podgląd nie jest jeszcze dostępny.")
        filename = self.directory(item_id) / "preview.json"
        return json.loads(filename.read_text())

    def program(self, item_id, profile, operation_file="isolation.nc"):
        """Check original source, artifact and active profile before loading."""
        item = self.get(item_id)
        if item["state"] != "ready" or not item["report"]["checks"]["passed"]:
            raise ValueError("Ten wynik nie jest gotowym programem obróbki.")
        if operation_file == "isolation.nc" and (
            profile.get("fingerprint") != item["profile"]["fingerprint"]
        ) or (
            item.get("implementationHashes") != implementation_hashes()
        ):
            raise ValueError("Profil lub silnik zmienił się; oblicz ponownie.")
        source = self.library.get(item["packageId"])
        record = next(file for file in source["files"]
                      if file["sha256"] == item["sourceSha256"])
        self.library.file(source["id"], record["name"])
        if operation_file not in item["artifacts"] or not (
            operation_file == "isolation.nc" or any(
                operation["file"] == operation_file
                for operation in item["report"].get("sequence", []))
        ):
            raise ValueError("Brak operacji w sprawdzonym zleceniu.")
        content = (self.directory(item_id) / operation_file).read_text("ascii")
        program = parse_program(operation_file, content)
        if operation_file == "isolation.nc":
            check_cam_program(profile, program, {})
        return {"name": operation_file[:-3] + "-" + item_id[:8] + ".nc",
                "content": content}

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
