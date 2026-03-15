from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.analysis_result import AnalysisResult
from app.models.enums import ComparisonErrorReason, ComparisonStatus, RevisionDetectionStatus
from app.models.valuation_view import ValuationView
from app.services.valuation_view_ingestion import ingest_valuation_views


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_valuation_view_ingestion_saves_rows() -> None:
    session = _build_session()
    analysis = AnalysisResult(
        disclosure_id=1,
        guidance_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
        dividend_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
        overall_score=Decimal("2.5"),
        total_score=Decimal("2.5"),
        should_notify=True,
        yoy_comparison_status=ComparisonStatus.OK,
        yoy_comparison_error_reason=ComparisonErrorReason.NONE,
        qoq_comparison_status=ComparisonStatus.OK,
        qoq_comparison_error_reason=ComparisonErrorReason.NONE,
        average_progress_comparison_status=ComparisonStatus.OK,
        average_progress_comparison_error_reason=ComparisonErrorReason.NONE,
    )
    session.add(analysis)
    session.commit()

    result = ingest_valuation_views(session)
    valuation = session.scalar(select(ValuationView).where(ValuationView.disclosure_id == 1))

    assert result["processed"] == 1
    assert result["saved"] == 1
    assert valuation is not None
    assert valuation.eps_revision_view is not None
    assert valuation.per_change_view is not None
    assert valuation.short_term_reaction_view is not None
