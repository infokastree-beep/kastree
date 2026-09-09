"""Public Kastree Convert — one-time TB conversion (no Clerk, no org).

Reuses Phase 1 ``extract_trial_balance_from_pdf``. Does not create
``trial_balances`` or touch subscriber Upload / billing subscription paths.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

import stripe
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.schemas.pdf_extract import ExtractedTbRowOut, PdfTbExtractResponse
from app.services.pdf_tb_extract import PdfTbExtractError, extract_trial_balance_from_pdf
from app.services.rate_limit import enforce_rate_limit
from app.services.standalone_convert import (
    CONVERT_AMOUNT_EUR_CENTS,
    CONVERT_PRODUCT,
    frontend_base_url,
    load_conversion,
    load_conversion_by_session,
    mark_paid_by_session,
    rows_to_xlsx_bytes,
    save_conversion,
    update_conversion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/solutions/convert", tags=["solutions-convert"])


class ConvertCheckoutRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal


class ConvertCheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ConvertCheckoutRow] = Field(min_length=1)
    customer_email: str | None = None


class ConvertCheckoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkout_url: str
    session_id: str
    conversion_id: uuid.UUID
    amount_eur: str = "19.00"


class ConvertStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversion_id: uuid.UUID
    status: Literal["pending_payment", "paid", "expired"]
    paid: bool
    download_ready: bool


def _require_stripe() -> None:
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured",
        )
    stripe.api_key = settings.stripe_secret_key


@router.post("/extract", response_model=PdfTbExtractResponse)
async def convert_extract_pdf(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> PdfTbExtractResponse:
    """Public PDF extract — same Phase 1 engine; rate-limited; no TB created."""
    enforce_rate_limit(
        request,
        key_prefix="convert_extract",
        max_requests=settings.convert_extract_rate_limit_per_ip_per_hour,
        window=timedelta(hours=1),
    )
    filename = file.filename or "trial-balance.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 50MB limit")
    try:
        result = extract_trial_balance_from_pdf(content)
    except PdfTbExtractError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return PdfTbExtractResponse(
        rows=[
            ExtractedTbRowOut(
                account_code=row.account_code,
                account_name=row.account_name,
                debit=row.debit,
                credit=row.credit,
                row_index=row.row_index,
            )
            for row in result.rows
        ],
        method=result.method,
        page_count=result.page_count,
        warnings=result.warnings,
    )


@router.post("/checkout", response_model=ConvertCheckoutResponse)
async def convert_checkout(
    request: Request,
    body: ConvertCheckoutRequest,
) -> ConvertCheckoutResponse:
    """Create a one-time Stripe Checkout Session for the confirmed review rows."""
    enforce_rate_limit(
        request,
        key_prefix="convert_checkout",
        max_requests=settings.convert_checkout_rate_limit_per_ip_per_hour,
        window=timedelta(hours=1),
    )
    _require_stripe()

    rows_payload: list[dict[str, Any]] = [
        {
            "account_code": row.account_code,
            "account_name": row.account_name,
            "debit": format(row.debit, "f"),
            "credit": format(row.credit, "f"),
        }
        for row in body.rows
    ]
    email = (body.customer_email or "").strip() or None
    conversion_id = save_conversion(rows=rows_payload, customer_email=email)

    base = frontend_base_url()
    success_url = (
        f"{base}/solutions/convert/success"
        f"?session_id={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = f"{base}/solutions/convert/cancel"

    line_item: dict[str, object]
    if settings.stripe_price_id_convert:
        line_item = {
            "price": settings.stripe_price_id_convert,
            "quantity": 1,
        }
    else:
        line_item = {
            "price_data": {
                "currency": "eur",
                "unit_amount": CONVERT_AMOUNT_EUR_CENTS,
                "product_data": {
                    "name": "Kastree Convert — trial balance conversion",
                    "description": "One-time PDF/Excel trial balance → structured Excel",
                },
            },
            "quantity": 1,
        }

    params: dict[str, object] = {
        "mode": "payment",
        "line_items": [line_item],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {
            "product": CONVERT_PRODUCT,
            "conversion_id": str(conversion_id),
        },
        "payment_intent_data": {
            "metadata": {
                "product": CONVERT_PRODUCT,
                "conversion_id": str(conversion_id),
            }
        },
        # Account has Managed Payments on by default; Convert is a simple
        # one-time Checkout and must opt out of that product-tax path.
        "managed_payments": {"enabled": False},
    }
    if email:
        params["customer_email"] = email
    # Automated E2E only: apply a 100% coupon when configured (never set in normal prod).
    if settings.convert_e2e_coupon_id:
        params["discounts"] = [{"coupon": settings.convert_e2e_coupon_id}]

    try:
        session = stripe.checkout.Session.create(**params)
    except stripe.StripeError as exc:
        logger.exception("convert_checkout_stripe_error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stripe Checkout failed: {exc.user_message or str(exc)}",
        ) from exc

    session_id = str(session["id"])
    checkout_url = str(session["url"])
    update_conversion(conversion_id, stripe_session_id=session_id)

    return ConvertCheckoutResponse(
        checkout_url=checkout_url,
        session_id=session_id,
        conversion_id=conversion_id,
    )


@router.get("/status", response_model=ConvertStatusResponse)
async def convert_status(session_id: str) -> ConvertStatusResponse:
    """Poll payment status; also sync from Stripe if webhook is slow."""
    if not session_id.startswith("cs_"):
        raise HTTPException(status_code=400, detail="Invalid session_id")
    data = load_conversion_by_session(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Conversion not found")

    if data.get("status") != "paid":
        _require_stripe()
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            if str(session.get("payment_status")) == "paid":
                updated = mark_paid_by_session(session_id)
                if updated is not None:
                    data = updated
        except stripe.StripeError:
            logger.exception("convert_status_stripe_retrieve_failed")

    status_value = str(data.get("status", "pending_payment"))
    if status_value not in {"pending_payment", "paid", "expired"}:
        status_value = "pending_payment"
    paid = status_value == "paid"
    return ConvertStatusResponse(
        conversion_id=uuid.UUID(str(data["id"])),
        status=status_value,  # type: ignore[arg-type]
        paid=paid,
        download_ready=paid,
    )


@router.get("/download")
async def convert_download(session_id: str) -> Response:
    """Stream the converted .xlsx after payment is confirmed."""
    if not session_id.startswith("cs_"):
        raise HTTPException(status_code=400, detail="Invalid session_id")
    data = load_conversion_by_session(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Conversion not found")

    if data.get("status") != "paid":
        _require_stripe()
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            if str(session.get("payment_status")) == "paid":
                updated = mark_paid_by_session(session_id)
                if updated is not None:
                    data = updated
        except stripe.StripeError as exc:
            raise HTTPException(
                status_code=502,
                detail="Could not verify payment with Stripe",
            ) from exc

    if data.get("status") != "paid":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment required before download",
        )

    rows = data.get("rows") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=422, detail="No rows to export")

    content = rows_to_xlsx_bytes(rows)
    update_conversion(
        uuid.UUID(str(data["id"])),
        download_count=int(data.get("download_count") or 0) + 1,
    )
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                'attachment; filename="kastree-converted-trial-balance.xlsx"'
            )
        },
    )
