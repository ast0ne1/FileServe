from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(260), default="index.html")
    page_type: Mapped[str] = mapped_column(String(20), default="html")
    auth_username: Mapped[str] = mapped_column(String(200), default="")
    auth_password_hash: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(Text, default="")
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    last_opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def is_protected(self) -> bool:
        return bool(self.auth_username and self.auth_password_hash)

    @property
    def type_label(self) -> str:
        return {"html": "HTML", "pdf": "PDF", "docx": "Word"}.get(self.page_type, self.page_type)

    @property
    def last_opened_label(self) -> str:
        if self.last_opened_at is None:
            return ""
        value = self.last_opened_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%d %b %Y %H:%M")

    @property
    def expiry_date_value(self) -> str:
        if self.expires_at is None:
            return ""
        value = self.expires_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date().isoformat()

    @property
    def expiry_label(self) -> str:
        if self.expires_at is None:
            return ""
        value = self.expires_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%d %b %Y")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
