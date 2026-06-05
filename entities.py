from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), default="viewer", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notification_email: Mapped[bool] = mapped_column(Boolean, default=True)
    reset_token: Mapped[str] = mapped_column(String(120), default="")

    workbooks: Mapped[List["DemandWorkbook"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    alerts: Mapped[List["Alert"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    automations: Mapped[List["AutomationSchedule"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    integrations: Mapped[List["IntegrationEndpoint"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class DemandWorkbook(Base):
    __tablename__ = "demand_workbooks"
    __table_args__ = (Index("ix_workbooks_owner_state", "owner_id", "state"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    rows_loaded: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(40), default="ready", index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    owner: Mapped[Account] = relationship(back_populates="workbooks")
    observations: Mapped[List["DemandObservation"]] = relationship(back_populates="workbook", cascade="all, delete-orphan")
    scenarios: Mapped[List["PlanningScenario"]] = relationship(back_populates="workbook", cascade="all, delete-orphan")


class DemandObservation(Base):
    __tablename__ = "demand_observations"
    __table_args__ = (
        Index("ix_observation_workbook_period", "workbook_id", "period_date"),
        Index("ix_observation_filters", "workbook_id", "segment", "market"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workbook_id: Mapped[int] = mapped_column(ForeignKey("demand_workbooks.id"), index=True)
    period_date = mapped_column(Date, index=True)
    item_name: Mapped[str] = mapped_column(String(255), index=True)
    segment: Mapped[str] = mapped_column(String(120), default="Core", index=True)
    market: Mapped[str] = mapped_column(String(120), default="National", index=True)
    units: Mapped[float] = mapped_column(Float)
    revenue: Mapped[float] = mapped_column(Float)

    workbook: Mapped[DemandWorkbook] = relationship(back_populates="observations")


class PlanningScenario(Base):
    __tablename__ = "planning_scenarios"
    __table_args__ = (Index("ix_scenarios_workbook_created", "workbook_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workbook_id: Mapped[int] = mapped_column(ForeignKey("demand_workbooks.id"), index=True)
    algorithm: Mapped[str] = mapped_column(String(80), index=True)
    horizon: Mapped[int] = mapped_column(Integer, default=6)
    rmse: Mapped[float] = mapped_column(Float, default=0)
    mae: Mapped[float] = mapped_column(Float, default=0)
    quality_score: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    workbook: Mapped[DemandWorkbook] = relationship(back_populates="scenarios")
    projections: Mapped[List["ProjectionPoint"]] = relationship(back_populates="scenario", cascade="all, delete-orphan")


class ProjectionPoint(Base):
    __tablename__ = "projection_points"
    __table_args__ = (Index("ix_projection_scenario_target", "scenario_id", "target_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("planning_scenarios.id"), index=True)
    item_name: Mapped[str] = mapped_column(String(255), index=True)
    target_date = mapped_column(Date, index=True)
    expected_units: Mapped[float] = mapped_column(Float)
    low_estimate: Mapped[float] = mapped_column(Float)
    high_estimate: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0)

    scenario: Mapped[PlanningScenario] = relationship(back_populates="projections")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    headline: Mapped[str] = mapped_column(String(160))
    detail: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(40), default="info")
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    account: Mapped[Account] = relationship(back_populates="alerts")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    event_name: Mapped[str] = mapped_column(String(120), index=True)
    reference: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ApiActivity(Base):
    __tablename__ = "api_activity"
    __table_args__ = (Index("ix_api_activity_created_status", "created_at", "status_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    method: Mapped[str] = mapped_column(String(12), index=True)
    path: Mapped[str] = mapped_column(String(255), index=True)
    status_code: Mapped[int] = mapped_column(Integer, index=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AutomationSchedule(Base):
    __tablename__ = "automation_schedules"
    __table_args__ = (Index("ix_automation_account_status", "account_id", "enabled"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    workbook_id: Mapped[int] = mapped_column(ForeignKey("demand_workbooks.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    algorithm: Mapped[str] = mapped_column(String(80), default="ensemble")
    horizon: Mapped[int] = mapped_column(Integer, default=6)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    account: Mapped[Account] = relationship(back_populates="automations")


class IntegrationEndpoint(Base):
    __tablename__ = "integration_endpoints"
    __table_args__ = (Index("ix_integration_account_provider", "account_id", "provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(80), default="external_api", index=True)
    direction: Mapped[str] = mapped_column(String(40), default="push")
    endpoint_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(40), default="ready", index=True)
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    account: Mapped[Account] = relationship(back_populates="integrations")
