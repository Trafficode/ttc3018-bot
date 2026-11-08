# Local manufacturing collection

The **Plik → Z kolekcji** control selects a stored manufacturing package, then one
program. **Wybierz plik** still reads a local disk file. Collection ingestion never
changes the currently loaded job. Selection uses the existing `job_load` action,
including active job/probe exclusion and old surface-map invalidation. No import
or selection starts movement, opens USB, or starts the spindle.

Tractor sends checked PCB geometry and optionally operator-supplied NC programs.
Computer-aided manufacturing (CAM) can now prepare copper isolation on the RPi.
**Paczki z Tractor** keeps original sources; **Programy obróbki** keeps generated
results. See [CAM preparation](cam-preparation.md) for profile selection, checked
toolpaths, failures and the separate worker boundary. Drilling and outline remain
unprepared. Externally supplied NC still uses an explicit operator declaration
of geometry correspondence; it does not gain the generated-result checks.

## Storage and API

`~/.local/share/bark-beetle/library/<SHA-256>/` contains original bytes and
`manifest.json`. Files survive service restart. Packages are immutable and
content addressed; identical retries are deduplicated. Atomic directory rename
keeps rejected/incomplete packages out of the list. Files are hash-checked again
on download or selection. The current parser revalidates selected G-code and
the existing Start path checks the matching calibrated tool profile.

POST `/api/library/packages` accepts schema version 1: `project` with `id`, `name`,
`revision`, `boardHash`, `side`, `datum`; `camConfirmed`; and `files` with `name`,
`kind` (`cad` ZIP or `program` NC), base64 `content`, and byte-exact `sha256`.
Programs require `camConfirmed: true` and pass `monitor.jobs.parse_program`.
ZIPs are attachments only, never extracted. Limits: 24 files/10 MiB per package,
1 MiB per NC, 16 MiB HTTP body, 200 packages/256 MiB collection. Full storage
rejects a new package; no automatic deletion or overwrite occurs.

Ingestion requires `Authorization: Bearer <secret>`. Set the same random secret
in Tractor's ignored local settings and the private file
`~/.local/share/bark-beetle/library.token`, mode 0600. An alternate file may be
selected with `PILOMILL_LIBRARY_TOKEN_FILE`. Missing/short token disables import.
Never copy the operator control token into Tractor. The import credential cannot
read the collection, load a file or invoke controller actions.

The operator UI uses `X-PiloMill-Token` for GET `/api/library`, GET
`/api/library/files/:id/:name`, and same-origin POST `/api/library/select` with
`packageId` and `name`. Selection delegates to the existing controller owner.
There is no parallel serial connection. CAM has a separate isolated computation
worker; collection import itself never starts it.

## Validation and deployment

Run `python -m unittest discover -s tests` and `npm run build` in `ui/`.
`tests/test_library.py` uses temporary storage, loopback HTTP and a mocked
controller, never USB. Preserve existing checkout changes before deployment;
compare the baseline of every replaced file, back it up, and deploy only this
feature's files. Before restarting the monitor confirm the CNC is inactive and
the operator is ready. Preserve camera/environment service routes and the HIL
relay panel. Real cutting, CAM quality and tool calibration require separate
physical validation.
