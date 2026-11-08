# ---------------------------------------------------------------------------
# controller_fixture.py
# 2026-10-24
# - Isolate fake CNC controllers from the operator's persisted profile state.
# ---------------------------------------------------------------------------
"""No serial connection is opened; each fixture has temporary local state."""

from pathlib import Path
import tempfile
import weakref

from monitor.cnc import Controller as BaseController


class Controller(BaseController):
    """Exercise the real controller with an isolated calibration directory."""

    def __init__(self):
        directory = tempfile.TemporaryDirectory()
        super().__init__(profile_path=Path(directory.name) / "preset.json")
        weakref.finalize(self, directory.cleanup)

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
