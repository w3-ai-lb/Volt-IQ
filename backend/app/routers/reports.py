"""
Reports router, the "Generate reports" admin use case.

Implements the "Report Generation" responsibility from Section V-ii of the
Software Architecture and the "Business reports" output of the Analytics
Dashboard Module (SRS Section VI-iv).

    GET /reports                      list the available report types
    GET /reports/{type}?from&to&format download a PDF or Excel report

Admin-only, like every other management endpoint.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.database import get_db
from app.models.customer import Customer
from app.reports import builder, render
from app.schemas.common import CamelModel

router = APIRouter(prefix="/reports", tags=["Reports"])

# Matches the six cards on src/pages/admin/ReportsPage.tsx.
CATALOGUE = [
    ("revenue", "Revenue Report", "Monthly revenue breakdown by region and plan"),
    ("consumption", "Consumption Report", "Aggregate consumption patterns and trends"),
    ("customers", "Customer Report", "Customer growth, churn, and segmentation"),
    ("anomalies", "Anomaly Report", "All detected anomalies and resolutions"),
    ("forecast", "Forecast Report", "Demand forecast predictions and a backtest diagnostic"),
    ("billing", "Billing Report", "Bills issued, payments, and outstanding balances"),
]

MAX_RANGE_DAYS = 366 * 3


class ReportTypeOut(CamelModel):
    id: str
    label: str
    description: str


@router.get("", response_model=list[ReportTypeOut])
def list_report_types(_: Customer = Depends(require_admin)):
    """The report types this backend can generate."""
    return [{"id": key, "label": label, "description": description}
            for key, label, description in CATALOGUE]


@router.get("/{report_type}")
def generate_report(
    report_type: str,
    # `from` is a Python keyword, so the parameter is aliased.
    date_from: date = Query(..., alias="from", description="Start date, YYYY-MM-DD"),
    date_to: date = Query(..., alias="to", description="End date, YYYY-MM-DD"),
    format: str = Query("pdf", pattern="^(pdf|excel)$"),
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """Generate a report and return it as a file download."""
    if report_type not in builder.REPORT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown report type '{report_type}'. "
                   f"Available: {', '.join(builder.REPORT_TYPES)}",
        )

    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The start date must not be after the end date",
        )

    # Guard against a range so wide the query would scan the whole table.
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The date range must not exceed 3 years",
        )

    today = datetime.now(UTC).date()
    if date_from > today + timedelta(days=1):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The start date is in the future, there is nothing to report on yet",
        )

    report = builder.build(db, report_type, date_from, date_to)
    payload = render.RENDERERS[format](report)

    filename = f"{report.filename_stem}.{render.EXTENSIONS[format]}"
    return Response(
        content=payload,
        media_type=render.MEDIA_TYPES[format],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Lets the browser read the filename when the request is made by JS.
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
