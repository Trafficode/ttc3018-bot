# ---------------------------------------------------------------------------
# checkpoint_fusion.py
# 2026-10-04
# - Save the active PiloMill-L Fusion design and export native checkpoints.
# ---------------------------------------------------------------------------
"""Execute inside Fusion; never rebuild this design from another CAD system."""

import hashlib
import json
from pathlib import Path

import adsk.core
import adsk.fusion


def run(_context: str):
    """Save the recognized active design and export F3D, STEP and validation.

    Fusion internal lengths are centimeters. Reports use millimeters and cubic
    millimeters. Run outside interactive commands. No geometry is changed.
    """
    app = adsk.core.Application.get()
    document = app.activeDocument
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None or document.name != "PiloMill-L" or not document.isSaved:
        raise ValueError("Open the saved PiloMill-L design before checkpointing")
    root = design.rootComponent
    expected = {"StandBase", "StandPole", "EquipmentHead", "ClampKnob"}
    found = {occ.component.name for occ in root.occurrences}
    if found != expected or root.bRepBodies.count:
        raise ValueError("Active model structure differs; inspect before export")
    parts = []
    for occurrence in root.occurrences:
        if occurrence.bRepBodies.count != 1:
            raise ValueError("Expected one solid per stand component")
        body = occurrence.bRepBodies.item(0)
        if not body.isSolid:
            raise ValueError("Non-solid component: " + occurrence.name)
        bounds = body.boundingBox
        parts.append({
            "name": occurrence.component.name,
            "volume_mm3": body.volume * 1000,
            "min_mm": [bounds.minPoint.x * 10, bounds.minPoint.y * 10,
                       bounds.minPoint.z * 10],
            "max_mm": [bounds.maxPoint.x * 10, bounds.maxPoint.y * 10,
                       bounds.maxPoint.z * 10],
        })
    healthy = adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState
    for item in design.timeline:
        if item.healthState != healthy:
            raise ValueError(item.name + ": " + item.errorOrWarningMessage)
    folder = Path(r"D:\Workspace\github\ttc3018-bot\mechanical\mount-arm\fusion")
    if not folder.is_dir():
        raise ValueError("Repository output folder is missing")
    if document.isModified:
        if not document.save("PiloMill-L Fusion checkpoint"):
            raise ValueError("Fusion document save failed")
    files = {}
    archive = folder / "PiloMill-L.f3d"
    options = design.exportManager.createFusionArchiveExportOptions(
        str(archive))
    if not design.exportManager.execute(options):
        raise ValueError("Native archive export failed")
    step = folder / "PiloMill-L.step"
    options = design.exportManager.createSTEPExportOptions(str(step))
    if not design.exportManager.execute(options):
        raise ValueError("STEP export failed")
    for path in [archive, step]:
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    base = root.occurrences.itemByName("StandBase:1").bRepBodies.item(0)
    pole = root.occurrences.itemByName("StandPole:1").bRepBodies.item(0)
    rear_offset = abs(base.boundingBox.minPoint.y - pole.boundingBox.minPoint.y)
    report = {
        "source_of_truth": "Autodesk Fusion", "document": document.name,
        "document_saved": document.isSaved,
        "unsaved_changes": document.isModified,
        "fusion_version": app.version, "units": "mm", "parts": parts,
        "timeline_healthy": True, "rear_edge_offset_mm": rear_offset * 10,
        "parameters": {p.name: p.expression for p in design.userParameters},
        "sketches": [
            {"name": sketch.name,
             "fully_constrained": sketch.isFullyConstrained}
            for occurrence in root.occurrences
            for sketch in occurrence.component.sketches
        ],
        "physical_fit_validated": False, "stability_validated": False,
        "thermal_validated": False, "slicer_validated": False,
        "sha256": files,
    }
    (folder / "validation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    app.activeViewport.fit()
    print(json.dumps(report))

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
