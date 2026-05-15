import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.encrypted_string import EncryptedString


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    supabase_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    gmail_access_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    gmail_refresh_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    gmail_watch_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gmail_connection_status: Mapped[str] = mapped_column(
        Enum("connected", "needs_reauth", "never_connected", name="gmail_connection_status_enum"),
        default="never_connected",
        nullable=False,
    )
    expo_push_token: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
