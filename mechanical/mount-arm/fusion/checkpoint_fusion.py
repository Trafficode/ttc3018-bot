# ---------------------------------------------------------------------------
# checkpoint_sliding_insert.py
# 2026-10-06
# - Validate the sliding mount and the plate's electronics-side reinforcement.
# ---------------------------------------------------------------------------

import hashlib
import json
from pathlib import Path

import adsk.core
import adsk.fusion


def run(_context):
    """Check solids and clearances, then export the saved native revision."""
    app = adsk.core.Application.get()
    document = app.activeDocument
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    assert document.name == "PiloMill-L" and document.isSaved
    assert root.attributes.itemByName("PiloMill", "layout").value == (
        "sliding-thread-insert-top-ribs-v2")
    names = {"IntegralStand", "EquipmentHead", "ClampKnob", "ThreadInsert"}
    assert {o.component.name for o in root.occurrences} == names
    for feature in design.timeline:
        assert feature.healthState == (
            adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState), (
                feature.name + ": " + feature.errorOrWarningMessage)
    entities = adsk.core.ObjectCollection.create()
    parts = []
    meshes = []
    for occurrence in root.occurrences:
        component = occurrence.component
        assert component.bRepBodies.count == 1
        body = component.bRepBodies.item(0)
        assert body.isSolid
        bounds = body.boundingBox
        parts.append({
            "name": component.name, "volume_mm3": body.volume * 1000,
            "local_min_mm": [v * 10 for v in bounds.minPoint.asArray()],
            "local_max_mm": [v * 10 for v in bounds.maxPoint.asArray()],
        })
        entities.add(occurrence)
        calculator = body.meshManager.createMeshCalculator()
        calculator.surfaceTolerance = 0.002
        calculator.normalTolerance = 0.05
        mesh = calculator.calculate()
        meshes.append({"name": component.name,
                       "vertices": mesh.nodeCoordinatesAsDouble,
                       "triangles": mesh.nodeIndices})
    setting = design.createInterferenceInput(entities)
    setting.areCoincidentFacesIncluded = False
    interference = design.analyzeInterference(setting)
    assert interference.count == 0
    assert document.save("Top-side ribs for flat-print equipment plate")
    folder = Path(r"D:\Workspace\github\ttc3018-bot"
                  r"\mechanical\mount-arm\fusion")
    hashes = {}
    for name in ["PiloMill-L.f3d", "PiloMill-L.step"]:
        target = folder / name
        if target.suffix == ".f3d":
            options = design.exportManager.createFusionArchiveExportOptions(
                str(target))
        else:
            options = design.exportManager.createSTEPExportOptions(str(target))
        assert design.exportManager.execute(options)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    report = {
        "source_of_truth": "Autodesk Fusion", "document": document.name,
        "layout": "sliding-thread-insert-top-ribs-v2", "units": "mm",
        "document_saved": True, "unsaved_changes": document.isModified,
        "timeline_healthy": True, "timeline_count": design.timeline.count,
        "parts": parts, "interference_pairs": 0, "sha256": hashes,
        "head_plate_size_mm": [130, 105, 4], "stand_height_mm": 220,
        "top_ribs": {"count": 6, "width_mm": 3, "height_above_plate_mm": 4},
        "top_ribs_keepouts": "RPi outline, pegs and insertion guide unchanged",
        "warping_resistance_physically_validated": False,
        "cool_before_removal": "Let both plate and bed reach room temperature",
        "front_lip_height_mm": 40, "modeled_thread": "M14x2",
        "female_thread_geometry": "Exact native BRep copy, scale 1.03 radial",
        "guide": "Top-open dovetail; insertion from front, closed rear end",
        "slide_clearance_mm": "0.3-0.35 provisional",
        "retention": "Integral release clip; release through underside window",
        "clip_length_mm": 14, "clip_thickness_mm": 1.5,
        "clip_catch_deflection_mm": 0.3,
        "metal_fasteners_required": False,
        "installation_requires_external_fastening": True,
        "physical_slide_and_clip_fit_validated": False,
        "physical_thread_fit_validated": False,
        "clamp_strength_validated": False, "thermal_validated": False,
        "slicer_validated": False,
        "prior_slicer_jobs": "Obsolete for the revised equipment plate",
        "parameters": {p.name: p.expression for p in design.userParameters},
    }
    (folder / "validation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    staging = Path(r"C:\Users\kamku\OneDrive\Dokumenty\ChatGPT"
                   r"\Anycubic Kobra X & TwoTrees Skills")
    (staging / "pilomill-sliding-mesh.json").write_text(json.dumps({
        "document": document.name,
        "source_revision": hashes["PiloMill-L.f3d"], "parts": meshes,
    }), encoding="utf-8")
    app.activeViewport.fit()
    app.activeViewport.saveAsImageFile(
        str(staging / "pilomill-sliding-insert.png"), 1400, 900)
    print(json.dumps(report))

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
