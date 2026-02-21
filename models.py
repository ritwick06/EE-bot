"""
SQLAlchemy ORM models for the Discord moderation bot.

Tables:
  - users          : Tracked Discord users
  - messages       : Message metadata & flag status
  - mod_actions    : Kick / ban / warn / timeout records
  - warnings       : User warnings
  - user_events    : Join / leave / verify / flag audit log
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared base with common timestamp columns."""
    pass


# ── Users ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    discord_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    messages: Mapped[list["Message"]] = relationship(back_populates="user")
    mod_actions_received: Mapped[list["ModAction"]] = relationship(
        back_populates="target_user",
        foreign_keys="ModAction.target_user_id",
    )
    warnings: Mapped[list["Warning"]] = relationship(back_populates="user")
    events: Mapped[list["UserEvent"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User discord_id={self.discord_id} username={self.username!r}>"


# ── Messages ─────────────────────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.discord_id", ondelete="CASCADE"), nullable=False
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flag_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flag_severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_messages_user_id", "user_id"),
        Index("ix_messages_guild_id", "guild_id"),
        Index("ix_messages_flagged", "flagged"),
        Index("ix_messages_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Message id={self.id} flagged={self.flagged}>"


# ── Moderation Actions ───────────────────────────────────────────────────────

class ActionType(str):
    """Enum-like constants for moderation action types."""
    KICK = "kick"
    BAN = "ban"
    WARN = "warn"
    TIMEOUT = "timeout"
    UNBAN = "unban"
    UNTIMEOUT = "untimeout"


class ModAction(Base):
    __tablename__ = "mod_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.discord_id", ondelete="CASCADE"), nullable=False
    )
    moderator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    target_user: Mapped["User"] = relationship(
        back_populates="mod_actions_received",
        foreign_keys=[target_user_id],
    )

    __table_args__ = (
        Index("ix_mod_actions_target", "target_user_id"),
        Index("ix_mod_actions_type", "action_type"),
        Index("ix_mod_actions_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ModAction id={self.id} type={self.action_type} "
            f"target={self.target_user_id}>"
        )


# ── Warnings ─────────────────────────────────────────────────────────────────

class Warning(Base):
    __tablename__ = "warnings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.discord_id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    issued_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="warnings")

    __table_args__ = (
        Index("ix_warnings_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Warning id={self.id} user={self.user_id}>"


# ── User Events (Audit Log) ─────────────────────────────────────────────────

class UserEvent(Base):
    __tablename__ = "user_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.discord_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="events")

    __table_args__ = (
        Index("ix_user_events_user_id", "user_id"),
        Index("ix_user_events_type", "event_type"),
        Index("ix_user_events_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<UserEvent id={self.id} type={self.event_type}>"
