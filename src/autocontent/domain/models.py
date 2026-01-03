from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from autocontent.shared.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)

    projects: Mapped[List["Project"]] = relationship(back_populates="owner", cascade="all, delete")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(length=255), nullable=False)
    tz: Mapped[str] = mapped_column(String(length=64), nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="active")

    owner: Mapped[User] = relationship(back_populates="projects")
    settings: Mapped["ProjectSettings"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )


class ProjectSettings(Base):
    __tablename__ = "project_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), nullable=False, unique=True
    )
    language: Mapped[str] = mapped_column(String(length=16), nullable=False)
    niche: Mapped[str] = mapped_column(String(length=128), nullable=False)
    tone: Mapped[str] = mapped_column(String(length=64), nullable=False)
    template_id: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    max_post_len: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    safe_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    autopost_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    project: Mapped[Project] = relationship(back_populates="settings")


class ChannelBinding(Base):
    __tablename__ = "channel_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, unique=True)
    channel_id: Mapped[str] = mapped_column(String(length=128), nullable=False)
    channel_username: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="pending")
    last_check_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("project_id", "url", name="uq_sources_project_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(length=32), nullable=False, default="rss")
    url: Mapped[str] = mapped_column(String(length=512), nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="pending")
    fetch_interval_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    last_fetch_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_items_external"),
        UniqueConstraint("source_id", "link", name="uq_source_items_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(length=512), nullable=False)
    link: Mapped[str] = mapped_column(String(length=1024), nullable=False)
    title: Mapped[str] = mapped_column(String(length=512), nullable=False)
    published_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    facts_cache: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(length=128), nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="new")


class PostDraft(Base):
    __tablename__ = "post_drafts"
    __table_args__ = (UniqueConstraint("draft_hash", name="uq_post_drafts_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    source_item_id: Mapped[int] = mapped_column(ForeignKey("source_items.id"), nullable=False)
    template_id: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    draft_hash: Mapped[str] = mapped_column(String(length=128), nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="new")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PublicationLog(Base):
    __tablename__ = "publication_logs"
    __table_args__ = (UniqueConstraint("draft_id", name="uq_publication_draft"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("post_drafts.id"), nullable=False)
    scheduled_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tg_message_id: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="new")
    error_code: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
