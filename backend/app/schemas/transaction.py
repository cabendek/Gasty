import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class TransactionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: Decimal
    merchant: str
    transaction_date: datetime
    transaction_type: str
    source: str
    source_email_id: str
    raw_subject: str | None
    needs_review: bool
    category_id: uuid.UUID | None
    description: str | None
    is_duplicate_of: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionList(BaseModel):
    items: list[TransactionOut]
    total: int
    skip: int
    limit: int
