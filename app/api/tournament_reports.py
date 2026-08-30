from __future__ import annotations

from typing import Callable, TypeVar

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.services.tournament_report_service import (
    TournamentReportNotEligible,
    TournamentReportNotFound,
    TournamentReportService,
    TournamentSnapshotUnavailable,
)
from app.tournament_reports.contracts import (
    ArchetypeReportResponse,
    EventOverviewResponse,
    ReportGrain,
    ReportSelection,
    TournamentReportIndexResponse,
)


T = TypeVar("T")


def build_tournament_report_router(service: TournamentReportService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/tournament-reports", tags=["tournament-reports"])

    def translate_report_errors(operation: Callable[[], T]) -> T | JSONResponse:
        try:
            return operation()
        except TournamentReportNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except TournamentSnapshotUnavailable as error:
            raise HTTPException(status_code=503, detail=error.detail) from error
        except TournamentReportNotEligible as error:
            if error.sample_size is None:
                raise HTTPException(status_code=409, detail=error.detail) from error
            return JSONResponse(
                status_code=422,
                content={
                    "detail": error.detail,
                    "reason_code": error.reason_code,
                    "sample_size": error.sample_size,
                },
            )

    @router.get("", response_model=TournamentReportIndexResponse)
    def list_reports():
        mounted = service.dataset_state_store.reconcile(
            service.dataset_state_store.load(),
            available_dataset_ids=[
                record.dataset_id for record in service.dataset_registry.list_datasets()
            ],
        ).mounted_dataset_ids
        return service.list_reports(mounted)

    @router.get("/{dataset_id}", response_model=EventOverviewResponse)
    def get_overview(dataset_id: str):
        return translate_report_errors(lambda: service.get_overview(dataset_id))

    @router.get("/{dataset_id}/families/{family_id}", response_model=ArchetypeReportResponse)
    def get_family_report(dataset_id: str, family_id: str):
        return translate_report_errors(
            lambda: service.get_archetype_report(
                dataset_id,
                ReportSelection(grain=ReportGrain.FAMILY, selection_id=family_id),
            )
        )

    @router.get("/{dataset_id}/variants/{variant_id}", response_model=ArchetypeReportResponse)
    def get_variant_report(dataset_id: str, variant_id: str):
        return translate_report_errors(
            lambda: service.get_archetype_report(
                dataset_id,
                ReportSelection(grain=ReportGrain.VARIANT, selection_id=variant_id),
            )
        )

    return router
