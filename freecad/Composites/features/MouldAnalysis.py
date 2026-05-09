# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCADGui
from FreeCAD import Vector

from .. import MOULD_TOOL_ICON, is_comp_type
from ..tools.mould_analysis import (
    analyze_source_shape,
    default_mould_analysis_draw_direction,
)
from .Command import BaseCommand
from .VPCompositePart import CompositePartFP, VPCompositePart


def is_mould_analysis(obj):
    return is_comp_type(obj, "Part::FeaturePython", "Composite::MouldAnalysis")


class MouldAnalysisFP(CompositePartFP):
    Type = "Composite::MouldAnalysis"

    def __init__(self, obj, source):
        obj.addProperty(
            "App::PropertyLink",
            "Source",
            "MouldAnalysis",
            "Link to the source solid",
            locked=True,
        ).Source = source

        obj.addProperty(
            "App::PropertyVector",
            "PreferredDrawDirection",
            "MouldAnalysis",
            "Preferred draw direction",
        ).PreferredDrawDirection = Vector(
            default_mould_analysis_draw_direction.x,
            default_mould_analysis_draw_direction.y,
            default_mould_analysis_draw_direction.z,
        )

        obj.addProperty(
            "App::PropertyString",
            "AnalysisStatus",
            "MouldAnalysis",
            "Current analysis state",
        ).AnalysisStatus = "Waiting for source"
        obj.setPropertyStatus("AnalysisStatus", "ReadOnly")

        obj.addProperty(
            "App::PropertyFloat",
            "DrawDirectionScore",
            "MouldAnalysis",
            "Normalized score for the preferred draw direction",
        ).DrawDirectionScore = 0.0
        obj.setPropertyStatus("DrawDirectionScore", "ReadOnly")

        obj.addProperty(
            "App::PropertyVector",
            "BestDrawDirection",
            "MouldAnalysis",
            "Best candidate draw direction",
        ).BestDrawDirection = Vector(
            default_mould_analysis_draw_direction.x,
            default_mould_analysis_draw_direction.y,
            default_mould_analysis_draw_direction.z,
        )
        obj.setPropertyStatus("BestDrawDirection", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "DrawDirectionRanking",
            "MouldAnalysis",
            "Ranking of candidate draw directions",
        ).DrawDirectionRanking = "No candidate directions available."
        obj.setPropertyStatus("DrawDirectionRanking", "ReadOnly")

        obj.addProperty(
            "App::PropertyInteger",
            "UndercutCount",
            "MouldAnalysis",
            "Heuristic count of possible undercut regions",
        ).UndercutCount = 0
        obj.setPropertyStatus("UndercutCount", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "UndercutSummary",
            "MouldAnalysis",
            "Human-readable undercut summary",
        ).UndercutSummary = "No source shape available."
        obj.setPropertyStatus("UndercutSummary", "ReadOnly")

        obj.addProperty(
            "App::PropertyStringList",
            "UndercutRegions",
            "MouldAnalysis",
            "Heuristic undercut regions",
        ).UndercutRegions = ["No source shape available."]
        obj.setPropertyStatus("UndercutRegions", "ReadOnly")

        obj.addProperty(
            "App::PropertyInteger",
            "DraftViolationCount",
            "MouldAnalysis",
            "Heuristic count of possible draft violations",
        ).DraftViolationCount = 0
        obj.setPropertyStatus("DraftViolationCount", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "DraftViolationSummary",
            "MouldAnalysis",
            "Human-readable draft violation summary",
        ).DraftViolationSummary = "No source shape available."
        obj.setPropertyStatus("DraftViolationSummary", "ReadOnly")

        obj.addProperty(
            "App::PropertyStringList",
            "DraftViolationRegions",
            "MouldAnalysis",
            "Heuristic draft violation regions",
        ).DraftViolationRegions = ["No source shape available."]
        obj.setPropertyStatus("DraftViolationRegions", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "PartingSurfaceStatus",
            "MouldAnalysis",
            "Current parting surface state",
        ).PartingSurfaceStatus = "Waiting for source"
        obj.setPropertyStatus("PartingSurfaceStatus", "ReadOnly")

        obj.addProperty(
            "App::PropertyVector",
            "PartingSurfaceNormal",
            "MouldAnalysis",
            "Normal of the proposed parting surface",
        ).PartingSurfaceNormal = Vector(
            default_mould_analysis_draw_direction.x,
            default_mould_analysis_draw_direction.y,
            default_mould_analysis_draw_direction.z,
        )
        obj.setPropertyStatus("PartingSurfaceNormal", "ReadOnly")

        obj.addProperty(
            "App::PropertyFloat",
            "PartingSurfaceOffset",
            "MouldAnalysis",
            "Offset of the proposed parting surface",
        ).PartingSurfaceOffset = 0.0
        obj.setPropertyStatus("PartingSurfaceOffset", "ReadOnly")

        obj.addProperty(
            "App::PropertyFloat",
            "PartingSurfaceArea",
            "MouldAnalysis",
            "Area of the proposed parting surface",
        ).PartingSurfaceArea = 0.0
        obj.setPropertyStatus("PartingSurfaceArea", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "PartingSurfaceSummary",
            "MouldAnalysis",
            "Human-readable parting surface summary",
        ).PartingSurfaceSummary = "No source shape available."
        obj.setPropertyStatus("PartingSurfaceSummary", "ReadOnly")

        obj.addProperty(
            "App::PropertyLink",
            "PartingSurface",
            "MouldAnalysis",
            "Preview parting surface",
            hidden=True,
        )
        parting_surface = obj.Document.addObject(
            "Part::Feature",
            f"{obj.Name}_PartingSurface",
        )
        obj.PartingSurface = parting_surface
        obj.setPropertyStatus("PartingSurface", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "MouldHalvesStatus",
            "MouldAnalysis",
            "Current mould halves state",
        ).MouldHalvesStatus = "Waiting for source"
        obj.setPropertyStatus("MouldHalvesStatus", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "MouldHalvesSummary",
            "MouldAnalysis",
            "Human-readable mould halves summary",
        ).MouldHalvesSummary = "No source shape available."
        obj.setPropertyStatus("MouldHalvesSummary", "ReadOnly")

        obj.addProperty(
            "App::PropertyLink",
            "MouldHalfA",
            "MouldAnalysis",
            "First mould half preview",
            hidden=True,
        )
        mould_half_a = obj.Document.addObject(
            "Part::Feature",
            f"{obj.Name}_MouldHalfA",
        )
        obj.MouldHalfA = mould_half_a
        obj.setPropertyStatus("MouldHalfA", "ReadOnly")

        obj.addProperty(
            "App::PropertyLink",
            "MouldHalfB",
            "MouldAnalysis",
            "Second mould half preview",
            hidden=True,
        )
        mould_half_b = obj.Document.addObject(
            "Part::Feature",
            f"{obj.Name}_MouldHalfB",
        )
        obj.MouldHalfB = mould_half_b
        obj.setPropertyStatus("MouldHalfB", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "ValidationStatus",
            "MouldAnalysis",
            "Current validation state",
        ).ValidationStatus = "Waiting for source"
        obj.setPropertyStatus("ValidationStatus", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "ValidationSummary",
            "MouldAnalysis",
            "Human-readable validation summary",
        ).ValidationSummary = "No source shape available."
        obj.setPropertyStatus("ValidationSummary", "ReadOnly")

        obj.addProperty(
            "App::PropertyStringList",
            "ValidationChecks",
            "MouldAnalysis",
            "Validation check results",
        ).ValidationChecks = ["No source shape available."]
        obj.setPropertyStatus("ValidationChecks", "ReadOnly")

        obj.addProperty(
            "App::PropertyString",
            "AnalysisSummary",
            "MouldAnalysis",
            "Human-readable analysis summary",
        ).AnalysisSummary = "Select a solid to begin mould analysis."
        obj.setPropertyStatus("AnalysisSummary", "ReadOnly")

        super().__init__(obj)

    def execute(self, fp):
        source_shape = fp.Source.Shape if fp.Source else None
        result = analyze_source_shape(source_shape, fp.PreferredDrawDirection)
        fp.AnalysisStatus = result["status"]
        fp.DrawDirectionScore = result["draw_direction_score"]
        fp.BestDrawDirection = result["best_draw_direction"]
        fp.DrawDirectionRanking = result["draw_direction_ranking"]
        fp.UndercutCount = result["undercut_count"]
        fp.UndercutSummary = result["undercut_summary"]
        fp.UndercutRegions = result["undercut_regions"]
        fp.DraftViolationCount = result["draft_violation_count"]
        fp.DraftViolationSummary = result["draft_violation_summary"]
        fp.DraftViolationRegions = result["draft_violation_regions"]
        fp.PartingSurfaceStatus = result["parting_surface_status"]
        fp.PartingSurfaceNormal = result["parting_surface_normal"]
        fp.PartingSurfaceOffset = result["parting_surface_offset"]
        fp.PartingSurfaceArea = result["parting_surface_area"]
        fp.PartingSurfaceSummary = result["parting_surface_summary"]
        if fp.PartingSurface:
            fp.PartingSurface.Shape = result["parting_surface_shape"]
        fp.MouldHalvesStatus = result["mould_halves_status"]
        fp.MouldHalvesSummary = result["mould_halves_summary"]
        if fp.MouldHalfA:
            fp.MouldHalfA.Shape = result["mould_half_a_shape"]
        if fp.MouldHalfB:
            fp.MouldHalfB.Shape = result["mould_half_b_shape"]
        fp.ValidationStatus = result["validation_status"]
        fp.ValidationSummary = result["validation_summary"]
        fp.ValidationChecks = result["validation_checks"]
        fp.AnalysisSummary = result["summary"]
        fp.Shape = result["shape"]

    def onChanged(self, fp, prop):
        if prop in ("Source", "PreferredDrawDirection"):
            fp.recompute()


class ViewProviderMouldAnalysis(VPCompositePart):
    def claimChildren(self):
        children = []
        for name in ("PartingSurface", "MouldHalfA", "MouldHalfB"):
            child = getattr(self.Object, name, None)
            if child:
                children.append(child)
        return children

    def getIcon(self):
        return MOULD_TOOL_ICON


class CompositeMouldAnalysisCommand(BaseCommand):
    icon = MOULD_TOOL_ICON
    menu_text = "Mould analysis"
    tool_tip = """Create a mould analysis object.
        Select source feature.
        WORK-IN-PROGRESS"""
    sel_args = [
        {
            "key": "source",
            "type": "Part::Feature",
        },
    ]
    type_id = "Part::FeaturePython"
    instance_name = "MouldAnalysis"
    cls_fp = MouldAnalysisFP
    cls_vp = ViewProviderMouldAnalysis


FreeCADGui.addCommand("Composites_MouldAnalysis", CompositeMouldAnalysisCommand())
