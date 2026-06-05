from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class SignupIn(BaseModel):
    full_name: str = Field(..., examples=["Priya"])
    email: EmailStr = Field(..., examples=["priya@forecast.ai"])
    password: str = Field(..., min_length=6, examples=["Priya@123"])


class SigninIn(BaseModel):
    email: EmailStr = Field(..., examples=["priya@forecast.ai"])
    password: str = Field(..., examples=["Priya@123"])


class AccountOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    active: bool
    notification_email: bool = True

    class Config:
        from_attributes = True


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    account: AccountOut


class WorkbookOut(BaseModel):
    id: int
    title: str
    rows_loaded: int
    state: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class WorkbookPage(BaseModel):
    records: List[WorkbookOut]
    total: int
    page: int
    size: int


class UploadOut(BaseModel):
    workbook: WorkbookOut
    profile: Dict[str, Any]


class ScenarioIn(BaseModel):
    algorithm: str = Field("ensemble", examples=["ensemble"])
    horizon: int = Field(6, ge=1, le=24, examples=[9])


class ProfileUpdateIn(BaseModel):
    full_name: Optional[str] = None
    notification_email: Optional[bool] = None


class PasswordResetIn(BaseModel):
    email: EmailStr


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


class AutomationIn(BaseModel):
    workbook_id: int
    name: str = Field("Daily ensemble forecast")
    interval_minutes: int = Field(1440, ge=15, le=43200)
    algorithm: str = Field("ensemble")
    horizon: int = Field(6, ge=1, le=24)
    enabled: bool = True


class AutomationOut(BaseModel):
    id: int
    workbook_id: int
    name: str
    interval_minutes: int
    algorithm: str
    horizon: int
    enabled: bool
    next_run_at: datetime
    last_run_at: Optional[datetime]

    class Config:
        from_attributes = True


class IntegrationIn(BaseModel):
    name: str = Field("Inventory API")
    provider: str = Field("external_api")
    direction: str = Field("push")
    endpoint_url: str = ""
    settings: Dict[str, Any] = Field(default_factory=dict)


class IntegrationOut(BaseModel):
    id: int
    name: str
    provider: str
    direction: str
    endpoint_url: str
    status: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    last_sync_at: Optional[datetime]


class WebhookIn(BaseModel):
    workbook_id: Optional[int] = None
    event: str = "sales.updated"
    payload: Dict[str, Any] = Field(default_factory=dict)


class AlertSettingsIn(BaseModel):
    low_stock_threshold: float = Field(1.0, ge=0)
    spike_threshold: float = Field(1.8, ge=1)
    email_notifications: bool = True


class ProjectionOut(BaseModel):
    target_date: date
    item_name: str
    expected_units: float
    low_estimate: float
    high_estimate: float
    confidence: float


class ScenarioOut(BaseModel):
    id: int
    workbook_id: int
    algorithm: str
    horizon: int
    rmse: float
    mae: float
    quality_score: float
    confidence: float
    created_at: datetime

    class Config:
        from_attributes = True


class ScenarioResult(BaseModel):
    scenario: ScenarioOut
    projections: List[ProjectionOut]


class CompareOut(BaseModel):
    algorithm: str
    rmse: float
    mae: float
    quality_score: float
    confidence: float


class InsightOut(BaseModel):
    revenue: float
    units: float
    avg_value: float
    quality_score: float
    confidence: float
    monthly_revenue: List[Dict[str, Any]]
    segment_mix: List[Dict[str, Any]]
    market_mix: List[Dict[str, Any]]
    top_items: List[Dict[str, Any]]
    projections: List[ProjectionOut]
    audit_trail: List[Dict[str, Any]]
    anomalies: List[Dict[str, Any]] = Field(default_factory=list)
    seasonal_trends: List[Dict[str, Any]] = Field(default_factory=list)
    revenue_prediction: List[Dict[str, Any]] = Field(default_factory=list)
    inventory_risks: List[Dict[str, Any]] = Field(default_factory=list)
    generated_insights: List[str] = Field(default_factory=list)


class AlertOut(BaseModel):
    id: int
    headline: str
    detail: str
    level: str
    seen: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AdminOut(BaseModel):
    accounts: int
    workbooks: int
    observations: int
    scenarios: int
    alerts: int
    recent_events: List[Dict[str, Any]]
    api_requests: int = 0
    avg_response_ms: float = 0
