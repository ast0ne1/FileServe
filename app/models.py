from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(20), default="user")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pages: Mapped[list["Page"]] = relationship(back_populates="owner")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), index=True)
    filename: Mapped[str] = mapped_column(String(260), default="index.html")
    page_type: Mapped[str] = mapped_column(String(20), default="html")
    auth_username: Mapped[str] = mapped_column(String(200), default="")
    auth_password_hash: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(Text, default="")
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    last_opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[Optional[User]] = relationship(back_populates="pages")

    @property
    def is_protected(self) -> bool:
        return bool(self.auth_username and self.auth_password_hash)

    @property
    def is_root_page(self) -> bool:
        return self.owner is None or self.owner.role == "admin"

    @property
    def owner_username(self) -> str:
        if self.owner is not None:
            return self.owner.username
        return "admin"

    @property
    def public_path(self) -> str:
        if self.is_root_page:
            return f"/{self.slug}"
        return f"/u/{self.owner_username}/{self.slug}"

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
