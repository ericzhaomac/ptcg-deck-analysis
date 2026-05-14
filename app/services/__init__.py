from __future__ import annotations

__all__ = ["PragueAnalysisService"]


def __getattr__(name: str):
    if name == "PragueAnalysisService":
        from .prague_analysis_service import PragueAnalysisService

        return PragueAnalysisService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
