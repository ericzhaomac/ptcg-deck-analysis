from __future__ import annotations

__all__ = ["DatasetAnalysisService", "PragueAnalysisService"]


def __getattr__(name: str):
    if name == "DatasetAnalysisService":
        from .dataset_analysis_service import DatasetAnalysisService

        return DatasetAnalysisService
    if name == "PragueAnalysisService":
        from .prague_analysis_service import PragueAnalysisService

        return PragueAnalysisService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
