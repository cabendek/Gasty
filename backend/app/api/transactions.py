import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models.parse_error import ParseError
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import TransactionList, TransactionOut

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionList)
def list_transactions(
    skip: int = 0,
    limit: int = 50,
    needs_review: bool | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    if needs_review is not None:
        q = q.filter(Transaction.needs_review == needs_review)
    total = q.count()
    items = q.order_by(Transaction.transaction_date.desc()).offset(skip).limit(limit).all()
    return TransactionList(items=items, total=total, skip=skip, limit=limit)


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == current_user.id)
        .first()
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/health")
def admin_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    week_ago = datetime.utcnow() - timedelta(days=7)

    tx_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.user_id == current_user.id, Transaction.created_at >= week_ago)
        .scalar()
    ) or 0

    err_count = (
        db.query(func.count(ParseError.id))
        .filter(ParseError.user_id == current_user.id, ParseError.created_at >= week_ago)
        .scalar()
    ) or 0

    total = tx_count + err_count
    parse_rate = (tx_count / total) if total > 0 else 1.0

    needs_review_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.user_id == current_user.id, Transaction.needs_review == True)  # noqa: E712
        .scalar()
    ) or 0

    expiring_soon = (
        db.query(User)
        .filter(
            User.gmail_connection_status == "connected",
            User.gmail_watch_expiry <= datetime.utcnow() + timedelta(days=2),
        )
        .count()
    )

    return {
        "parse_rate_last_7d": round(parse_rate, 4),
        "transactions_last_7d": tx_count,
        "parse_errors_last_7d": err_count,
        "needs_review_count": needs_review_count,
        "watches_expiring_soon": expiring_soon,
    }
