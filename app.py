from __future__ import annotations

from io import BytesIO
from math import ceil
from datetime import datetime, timedelta
from time import perf_counter
import json
from secrets import token_urlsafe
from typing import Any, Dict, List, Tuple

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .contracts import (
    AdminOut,
    AlertOut,
    AlertSettingsIn,
    AutomationIn,
    AutomationOut,
    AuthOut,
    CompareOut,
    InsightOut,
    IntegrationIn,
    IntegrationOut,
    PasswordChangeIn,
    PasswordResetIn,
    ProfileUpdateIn,
    ScenarioIn,
    ScenarioResult,
    SigninIn,
    SignupIn,
    WebhookIn,
    WorkbookPage,
    UploadOut,
)
from .db import Base, SessionFactory, engine, session_scope
from .engine import audit, alert, compare_algorithms, excel_report, insight_pack, pdf_report, prepare_table, projection_rows, run_scenario
from .entities import Account, Alert, ApiActivity, AuditEvent, AutomationSchedule, DemandObservation, DemandWorkbook, IntegrationEndpoint, PlanningScenario
from .security import ROLES, admin_account, analyst_account, check_secret, current_account, hash_secret, issue_token

def ensure_sqlite_compatibility() -> None:
    with engine.begin() as connection:
        if engine.dialect.name != "sqlite":
            return
        account_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(accounts)").fetchall()}
        if "notification_email" not in account_columns:
            connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN notification_email BOOLEAN DEFAULT 1")
        if "reset_token" not in account_columns:
            connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN reset_token VARCHAR(120) DEFAULT ''")


Base.metadata.create_all(bind=engine)
ensure_sqlite_compatibility()
INSIGHT_CACHE: Dict[Tuple[Any, ...], Tuple[datetime, Dict[str, Any]]] = {}
CACHE_SECONDS = 20

app = FastAPI(
    title=settings.product_name,
    version=settings.version,
    description=(
        "Green and white corporate forecasting enhancement platform for Priya. "
        "Includes secured workbook uploads, demand scenarios, algorithm comparison, "
        "business insights, alerts, admin summaries, and Excel/PDF exports.\n\n"
        "Swagger authorization format: `Bearer <access_token>`"
    ),
    openapi_tags=[
        {"name": "Session", "description": "Signup, signin, and profile authorization."},
        {"name": "Workbooks", "description": "Demand workbook upload and inventory."},
        {"name": "Planning", "description": "Forecast scenarios and algorithm comparison."},
        {"name": "Insights", "description": "Corporate analytics dashboard APIs."},
        {"name": "Exports", "description": "Excel and PDF business reports."},
        {"name": "Admin", "description": "Admin workspace for Priya's platform."},
        {"name": "Automation", "description": "Smart forecasting schedules and recurring processing."},
        {"name": "Integrations", "description": "ERP, inventory API, webhooks, and external sync settings."},
        {"name": "Profile", "description": "User profile, password reset, and account preferences."},
        {"name": "Live", "description": "Real-time sales monitoring and automated forecast refresh."},
        {"name": "System", "description": "Operational health, API metrics, and activity tracking."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_performance_monitor(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/"):
        db = SessionFactory()
        try:
            db.add(ApiActivity(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            ))
            db.commit()
        finally:
            db.close()
    return response


def owned_workbook(db: Session, workbook_id: int, account: Account) -> DemandWorkbook:
    query = db.query(DemandWorkbook).filter(DemandWorkbook.id == workbook_id)
    if account.role != "super_admin":
        query = query.filter(DemandWorkbook.owner_id == account.id)
    workbook = query.first()
    if not workbook:
        raise HTTPException(status_code=404, detail="Workbook not found")
    return workbook


@app.get("/api/v1/health", tags=["System"])
async def health():
    return {"status": "ready", "project": settings.product_name, "owner": "Priya"}


@app.post("/api/v1/session/signup", response_model=AuthOut, tags=["Session"])
async def signup(payload: SignupIn, db: Session = Depends(session_scope)):
    if db.query(Account).filter(Account.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already exists")
    role = "super_admin" if db.query(Account).count() == 0 else "viewer"
    account = Account(full_name=payload.full_name, email=payload.email, password_hash=hash_secret(payload.password), role=role)
    db.add(account)
    db.flush()
    alert(db, account.id, "Workspace ready", "Your forecasting enhancement workspace has been configured.", "success")
    audit(db, account.id, "account.signup", "account", {"role": role})
    db.commit()
    db.refresh(account)
    return {"access_token": issue_token(account.email, account.role), "account": account}


@app.post("/api/v1/session/signin", response_model=AuthOut, tags=["Session"])
async def signin(payload: SigninIn, db: Session = Depends(session_scope)):
    account = db.query(Account).filter(Account.email == payload.email).first()
    if not account or not check_secret(payload.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if account.role == "admin":
        account.role = "super_admin"
    elif account.role == "planner":
        account.role = "analyst"
    audit(db, account.id, "account.signin", "account")
    db.commit()
    return {"access_token": issue_token(account.email, account.role), "account": account}


@app.get("/api/v1/session/me", tags=["Session"])
async def me(account: Account = Depends(current_account)):
    return account


@app.patch("/api/v1/session/profile", response_model=AuthOut, tags=["Profile"])
async def update_profile(payload: ProfileUpdateIn, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    if payload.full_name:
        account.full_name = payload.full_name.strip()
    if payload.notification_email is not None:
        account.notification_email = payload.notification_email
    audit(db, account.id, "account.profile_updated", "account")
    db.commit()
    db.refresh(account)
    return {"access_token": issue_token(account.email, account.role), "account": account}


@app.post("/api/v1/session/password-reset", tags=["Profile"])
async def request_password_reset(payload: PasswordResetIn, db: Session = Depends(session_scope)):
    account = db.query(Account).filter(Account.email == payload.email).first()
    if account:
        account.reset_token = token_urlsafe(24)
        alert(db, account.id, "Password reset requested", "A password reset request was generated for this account.", "info")
        audit(db, account.id, "account.password_reset_requested", "account")
        db.commit()
    return {"detail": "If the email exists, a reset workflow has been started."}


@app.post("/api/v1/session/password", tags=["Profile"])
async def change_password(payload: PasswordChangeIn, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    if not check_secret(payload.current_password, account.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    account.password_hash = hash_secret(payload.new_password)
    account.reset_token = ""
    audit(db, account.id, "account.password_changed", "account")
    db.commit()
    return {"detail": "Password updated"}


@app.get("/api/v1/workbooks", response_model=WorkbookPage, tags=["Workbooks"])
async def workbooks(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    q: str = "",
    state: str = "",
    account: Account = Depends(current_account),
    db: Session = Depends(session_scope),
):
    query = db.query(DemandWorkbook)
    if account.role != "super_admin":
        query = query.filter(DemandWorkbook.owner_id == account.id)
    if q:
        query = query.filter(DemandWorkbook.title.ilike(f"%{q}%"))
    if state:
        query = query.filter(DemandWorkbook.state == state)
    total = query.count()
    rows = query.order_by(DemandWorkbook.uploaded_at.desc()).offset((page - 1) * size).limit(size).all()
    return {"records": rows, "total": total, "page": page, "size": size, "pages": ceil(total / size) if total else 0}


@app.post("/api/v1/workbooks/import", response_model=UploadOut, tags=["Workbooks"])
async def import_workbook(file: UploadFile = File(...), account: Account = Depends(analyst_account), db: Session = Depends(session_scope)):
    content = await file.read()
    try:
        if file.filename and file.filename.lower().endswith(".csv"):
            frame = pd.read_csv(BytesIO(content))
        elif file.filename and file.filename.lower().endswith((".xlsx", ".xls")):
            frame = pd.read_excel(BytesIO(content))
        else:
            raise ValueError("Upload CSV or Excel only")
        clean, profile = prepare_table(frame)
    except Exception as exc:
        alert(db, account.id, "Import failed", str(exc), "error")
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    workbook = DemandWorkbook(owner_id=account.id, title=file.filename or "demand-workbook", rows_loaded=len(clean))
    db.add(workbook)
    db.flush()
    db.bulk_save_objects([
        DemandObservation(
            workbook_id=workbook.id,
            period_date=row.date.date(),
            item_name=row.item_name,
            segment=row.category,
            market=row.region,
            units=float(row.units),
            revenue=float(row.revenue),
        )
        for row in clean.itertuples(index=False)
    ])
    alert(db, account.id, "Workbook imported", f"{workbook.title} loaded with {workbook.rows_loaded} accepted rows.", "success")
    audit(db, account.id, "workbook.imported", str(workbook.id), profile)
    db.commit()
    db.refresh(workbook)
    INSIGHT_CACHE.clear()
    return {"workbook": workbook, "profile": profile}


@app.get("/api/v1/workbooks/{workbook_id}/dimensions", tags=["Workbooks"])
async def dimensions(workbook_id: int, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    owned_workbook(db, workbook_id, account)
    base = db.query(DemandObservation).filter(DemandObservation.workbook_id == workbook_id)
    return {
        "items": [row[0] for row in base.with_entities(DemandObservation.item_name).distinct().all()],
        "segments": [row[0] for row in base.with_entities(DemandObservation.segment).distinct().all()],
        "markets": [row[0] for row in base.with_entities(DemandObservation.market).distinct().all()],
    }


@app.get("/api/v1/planning/algorithms", tags=["Planning"])
async def algorithms():
    return {"records": [{"id": item, "name": item.replace("_", " ").title()} for item in ["ensemble", "linear", "ridge", "forest", "seasonal_average"]]}


@app.post("/api/v1/planning/{workbook_id}/scenario", response_model=ScenarioResult, tags=["Planning"])
async def create_scenario(workbook_id: int, payload: ScenarioIn, account: Account = Depends(analyst_account), db: Session = Depends(session_scope)):
    workbook = owned_workbook(db, workbook_id, account)
    try:
        scenario = run_scenario(db, workbook.id, payload.algorithm, payload.horizon)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    alert(db, account.id, "Scenario completed", f"{payload.algorithm} scenario completed for {workbook.title}.", "success")
    audit(db, account.id, "scenario.completed", str(workbook.id), {"algorithm": payload.algorithm, "quality": scenario.quality_score})
    db.commit()
    INSIGHT_CACHE.clear()
    db.refresh(scenario)
    return {"scenario": scenario, "projections": projection_rows(scenario)}


@app.get("/api/v1/planning/{workbook_id}/compare", response_model=List[CompareOut], tags=["Planning"])
async def compare(workbook_id: int, account: Account = Depends(analyst_account), db: Session = Depends(session_scope)):
    owned_workbook(db, workbook_id, account)
    rows = compare_algorithms(db, workbook_id)
    audit(db, account.id, "scenario.compared", str(workbook_id))
    db.commit()
    return rows


@app.get("/api/v1/insights/{workbook_id}", response_model=InsightOut, tags=["Insights"])
async def insights(
    workbook_id: int,
    market: str = "",
    segment: str = "",
    q: str = "",
    account: Account = Depends(current_account),
    db: Session = Depends(session_scope),
):
    owned_workbook(db, workbook_id, account)
    key = (account.id, workbook_id, market, segment, q)
    cached = INSIGHT_CACHE.get(key)
    if cached and cached[0] > datetime.utcnow():
        return cached[1]
    result = insight_pack(db, workbook_id, market, segment, q)
    INSIGHT_CACHE[key] = (datetime.utcnow() + timedelta(seconds=CACHE_SECONDS), result)
    return result


@app.get("/api/v1/live/{workbook_id}", tags=["Live"])
async def live_snapshot(
    workbook_id: int,
    market: str = "",
    segment: str = "",
    account: Account = Depends(current_account),
    db: Session = Depends(session_scope),
):
    owned_workbook(db, workbook_id, account)
    pack = insight_pack(db, workbook_id, market, segment)
    query = db.query(DemandObservation).filter(DemandObservation.workbook_id == workbook_id)
    if market:
        query = query.filter(DemandObservation.market == market)
    if segment:
        query = query.filter(DemandObservation.segment == segment)
    recent = query.order_by(DemandObservation.period_date.desc()).limit(8).all()
    return {
        "updated_at": datetime.utcnow(),
        "refresh_seconds": 15,
        "sales_monitor": [{"date": row.period_date, "item": row.item_name, "units": row.units, "revenue": row.revenue} for row in recent],
        "anomalies": pack["anomalies"],
        "seasonal_trends": pack["seasonal_trends"],
        "inventory_risks": pack["inventory_risks"],
        "revenue_prediction": pack["revenue_prediction"],
        "generated_insights": pack["generated_insights"],
    }


@app.post("/api/v1/planning/{workbook_id}/retrain", tags=["Planning"])
async def retrain(workbook_id: int, account: Account = Depends(analyst_account), db: Session = Depends(session_scope)):
    workbook = owned_workbook(db, workbook_id, account)
    evaluated = compare_algorithms(db, workbook_id)
    best = evaluated[0]["algorithm"]
    scenario = run_scenario(db, workbook_id, best, 6)
    audit(db, account.id, "model.retrained", str(workbook_id), {"selected_algorithm": best, "quality": scenario.quality_score})
    alert(db, account.id, "AI retraining complete", f"{workbook.title}: {best.replace('_', ' ')} selected at {scenario.quality_score}% quality.", "success")
    db.commit()
    db.refresh(scenario)
    INSIGHT_CACHE.clear()
    return {"selected_algorithm": best, "comparison": evaluated, "scenario": scenario, "projections": projection_rows(scenario)}


@app.get("/api/v1/planning/{workbook_id}/history", tags=["Planning"])
async def forecast_history(
    workbook_id: int,
    algorithm: str = "",
    account: Account = Depends(current_account),
    db: Session = Depends(session_scope),
):
    owned_workbook(db, workbook_id, account)
    query = db.query(PlanningScenario).filter(PlanningScenario.workbook_id == workbook_id)
    if algorithm:
        query = query.filter(PlanningScenario.algorithm == algorithm)
    return query.order_by(PlanningScenario.created_at.desc()).limit(30).all()


@app.get("/api/v1/ai/{workbook_id}/recommendations", tags=["Planning"])
async def ai_recommendations(workbook_id: int, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    owned_workbook(db, workbook_id, account)
    pack = insight_pack(db, workbook_id)
    risks = pack["inventory_risks"]
    spikes = pack["anomalies"]
    return {
        "demand_recommendations": [
            {"item": row["item"], "action": "Increase replenishment", "reason": f"Forecast demand is {row['forecast_units']} units with {row['risk']} risk."}
            for row in risks if row["risk"] != "healthy"
        ][:8],
        "customer_behavior": [
            {"segment": row["segment"], "signal": "High revenue contribution", "recommended_action": "Prioritize targeted offers and availability."}
            for row in sorted(pack["segment_mix"], key=lambda item: item["revenue"], reverse=True)[:5]
        ],
        "demand_spikes": spikes,
        "inventory_optimization": [
            "Review reorder points for critical and watch items weekly.",
            "Use ensemble forecasts for replenishment planning when confidence is above 80%.",
            "Trigger manager approval for unusually high spike forecasts before purchase orders are pushed.",
        ],
        "business_recommendations": pack["generated_insights"],
    }


@app.get("/api/v1/dashboard/{workbook_id}/summary", tags=["Insights"])
async def dashboard_summary(workbook_id: int, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    owned_workbook(db, workbook_id, account)
    pack = insight_pack(db, workbook_id)
    return {
        "generated_at": datetime.utcnow(),
        "kpis": {
            "revenue": pack["revenue"],
            "units": pack["units"],
            "avg_value": pack["avg_value"],
            "confidence": pack["confidence"],
            "quality_score": pack["quality_score"],
        },
        "widgets": [
            {"id": "monthly_revenue", "title": "Monthly revenue", "enabled": True},
            {"id": "inventory_risks", "title": "Low-stock predictions", "enabled": True},
            {"id": "demand_spikes", "title": "Demand spike alerts", "enabled": True},
            {"id": "model_confidence", "title": "Confidence score", "enabled": True},
        ],
        "recommendations": pack["generated_insights"],
    }


@app.get("/api/v1/dashboard/{workbook_id}/summary/download", tags=["Exports"])
async def dashboard_summary_download(workbook_id: int, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    owned_workbook(db, workbook_id, account)
    summary = await dashboard_summary(workbook_id, account, db)
    body = json.dumps(summary, default=str, indent=2).encode("utf-8")
    audit(db, account.id, "export.dashboard_summary", str(workbook_id))
    db.commit()
    return StreamingResponse(BytesIO(body), media_type="application/json", headers={"Content-Disposition": "attachment; filename=dashboard-summary.json"})


@app.get("/api/v1/automation/schedules", response_model=List[AutomationOut], tags=["Automation"])
async def automation_schedules(account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    query = db.query(AutomationSchedule)
    if account.role != "super_admin":
        query = query.filter(AutomationSchedule.account_id == account.id)
    return query.order_by(AutomationSchedule.created_at.desc()).all()


@app.post("/api/v1/automation/schedules", response_model=AutomationOut, tags=["Automation"])
async def create_automation(payload: AutomationIn, account: Account = Depends(analyst_account), db: Session = Depends(session_scope)):
    owned_workbook(db, payload.workbook_id, account)
    schedule = AutomationSchedule(
        account_id=account.id,
        workbook_id=payload.workbook_id,
        name=payload.name,
        interval_minutes=payload.interval_minutes,
        algorithm=payload.algorithm,
        horizon=payload.horizon,
        enabled=payload.enabled,
        next_run_at=datetime.utcnow() + timedelta(minutes=payload.interval_minutes),
    )
    db.add(schedule)
    alert(db, account.id, "Automation enabled", f"{payload.name} will run every {payload.interval_minutes} minutes.", "success")
    audit(db, account.id, "automation.created", str(payload.workbook_id), payload.model_dump())
    db.commit()
    db.refresh(schedule)
    return schedule


@app.post("/api/v1/automation/schedules/{schedule_id}/run", tags=["Automation"])
async def run_automation(schedule_id: int, account: Account = Depends(analyst_account), db: Session = Depends(session_scope)):
    query = db.query(AutomationSchedule).filter(AutomationSchedule.id == schedule_id)
    if account.role != "super_admin":
        query = query.filter(AutomationSchedule.account_id == account.id)
    schedule = query.first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Automation schedule not found")
    owned_workbook(db, schedule.workbook_id, account)
    scenario = run_scenario(db, schedule.workbook_id, schedule.algorithm, schedule.horizon)
    schedule.last_run_at = datetime.utcnow()
    schedule.next_run_at = schedule.last_run_at + timedelta(minutes=schedule.interval_minutes)
    alert(db, account.id, "Recurring forecast generated", f"{schedule.name} completed with {scenario.confidence}% confidence.", "success")
    audit(db, account.id, "automation.executed", str(schedule.workbook_id), {"schedule_id": schedule.id})
    db.commit()
    db.refresh(schedule)
    INSIGHT_CACHE.clear()
    return {"schedule": schedule, "scenario": scenario, "projections": projection_rows(scenario)}


@app.post("/api/v1/alerts/settings", tags=["Insights"])
async def alert_settings(payload: AlertSettingsIn, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    account.notification_email = payload.email_notifications
    audit(db, account.id, "alerts.settings_updated", "account", payload.model_dump())
    db.commit()
    return {"detail": "Alert preferences saved", "settings": payload}


@app.get("/api/v1/integrations", response_model=List[IntegrationOut], tags=["Integrations"])
async def integrations(account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    query = db.query(IntegrationEndpoint)
    if account.role != "super_admin":
        query = query.filter(IntegrationEndpoint.account_id == account.id)
    rows = query.order_by(IntegrationEndpoint.created_at.desc()).all()
    return [{**row.__dict__, "settings": json.loads(row.settings_json or "{}")} for row in rows]


@app.post("/api/v1/integrations", response_model=IntegrationOut, tags=["Integrations"])
async def create_integration(payload: IntegrationIn, account: Account = Depends(analyst_account), db: Session = Depends(session_scope)):
    item = IntegrationEndpoint(
        account_id=account.id,
        name=payload.name,
        provider=payload.provider,
        direction=payload.direction,
        endpoint_url=payload.endpoint_url,
        settings_json=json.dumps(payload.settings),
    )
    db.add(item)
    audit(db, account.id, "integration.created", payload.provider, payload.model_dump())
    db.commit()
    db.refresh(item)
    return {**item.__dict__, "settings": payload.settings}


@app.post("/api/v1/integrations/{integration_id}/sync", tags=["Integrations"])
async def sync_integration(integration_id: int, account: Account = Depends(analyst_account), db: Session = Depends(session_scope)):
    query = db.query(IntegrationEndpoint).filter(IntegrationEndpoint.id == integration_id)
    if account.role != "super_admin":
        query = query.filter(IntegrationEndpoint.account_id == account.id)
    item = query.first()
    if not item:
        raise HTTPException(status_code=404, detail="Integration not found")
    item.status = "synced"
    item.last_sync_at = datetime.utcnow()
    alert(db, account.id, "Integration synced", f"{item.name} completed a {item.direction} sync.", "success")
    audit(db, account.id, "integration.synced", str(item.id), {"provider": item.provider})
    db.commit()
    return {"detail": "Integration sync recorded", "integration": {**item.__dict__, "settings": json.loads(item.settings_json or "{}")}}


@app.post("/api/v1/integrations/webhook", tags=["Integrations"])
async def integration_webhook(payload: WebhookIn, db: Session = Depends(session_scope)):
    account = db.query(Account).order_by(Account.id.asc()).first()
    if account:
        alert(db, account.id, "Webhook received", f"{payload.event} accepted for real-time processing.", "info")
        audit(db, account.id, "integration.webhook_received", str(payload.workbook_id or ""), payload.payload)
        db.commit()
    return {"accepted": True, "event": payload.event, "received_at": datetime.utcnow()}


@app.get("/api/v1/search", tags=["Insights"])
async def global_search(q: str = Query(..., min_length=1), account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    workbook_query = db.query(DemandWorkbook).filter(DemandWorkbook.title.ilike(f"%{q}%"))
    if account.role != "super_admin":
        workbook_query = workbook_query.filter(DemandWorkbook.owner_id == account.id)
    workbooks = workbook_query.order_by(DemandWorkbook.uploaded_at.desc()).limit(8).all()
    users = []
    if account.role == "super_admin":
        users = db.query(Account).filter((Account.email.ilike(f"%{q}%")) | (Account.full_name.ilike(f"%{q}%"))).limit(8).all()
    return {"workbooks": workbooks, "users": users}


@app.get("/api/v1/alerts", response_model=List[AlertOut], tags=["Insights"])
async def alerts(account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    return db.query(Alert).filter(Alert.account_id == account.id).order_by(Alert.created_at.desc()).limit(30).all()


@app.post("/api/v1/alerts/{alert_id}/seen", response_model=AlertOut, tags=["Insights"])
async def seen(alert_id: int, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    item = db.query(Alert).filter(Alert.id == alert_id, Alert.account_id == account.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found")
    item.seen = True
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/v1/exports/{workbook_id}/xlsx", tags=["Exports"])
async def export_xlsx(workbook_id: int, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    workbook = owned_workbook(db, workbook_id, account)
    audit(db, account.id, "export.xlsx", str(workbook_id))
    db.commit()
    return StreamingResponse(excel_report(db, workbook.id), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={workbook.title}-enhancement.xlsx"})


@app.get("/api/v1/exports/{workbook_id}/pdf", tags=["Exports"])
async def export_pdf(workbook_id: int, account: Account = Depends(current_account), db: Session = Depends(session_scope)):
    workbook = owned_workbook(db, workbook_id, account)
    audit(db, account.id, "export.pdf", str(workbook_id))
    db.commit()
    return StreamingResponse(pdf_report(db, workbook), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={workbook.title}-enhancement.pdf"})


@app.get("/api/v1/admin/overview", response_model=AdminOut, tags=["Admin"])
async def admin_overview(_: Account = Depends(admin_account), db: Session = Depends(session_scope)):
    events = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(10).all()
    return {
        "accounts": db.query(Account).count(),
        "workbooks": db.query(DemandWorkbook).count(),
        "observations": db.query(DemandObservation).count(),
        "scenarios": db.query(PlanningScenario).count(),
        "alerts": db.query(Alert).count(),
        "recent_events": [{"event_name": row.event_name, "reference": row.reference, "created_at": row.created_at} for row in events],
        "api_requests": db.query(ApiActivity).count(),
        "avg_response_ms": round(float(db.query(func.avg(ApiActivity.duration_ms)).scalar() or 0), 2),
    }


@app.get("/api/v1/admin/users", tags=["Admin"])
async def users(q: str = "", _: Account = Depends(admin_account), db: Session = Depends(session_scope)):
    query = db.query(Account)
    if q:
        query = query.filter((Account.email.ilike(f"%{q}%")) | (Account.full_name.ilike(f"%{q}%")))
    return query.order_by(Account.joined_at.desc()).limit(100).all()


@app.patch("/api/v1/admin/users/{account_id}/role", tags=["Admin"])
async def assign_role(account_id: int, role: str, operator: Account = Depends(admin_account), db: Session = Depends(session_scope)):
    if role not in ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of: {', '.join(sorted(ROLES))}")
    target = db.query(Account).filter(Account.id == account_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.id == operator.id and role != "super_admin":
        raise HTTPException(status_code=409, detail="You cannot remove your own Super Admin role")
    target.role = role
    audit(db, operator.id, "access.role_changed", str(target.id), {"role": role})
    db.commit()
    db.refresh(target)
    return target


@app.patch("/api/v1/admin/users/{account_id}/status", tags=["Admin"])
async def assign_status(account_id: int, active: bool, operator: Account = Depends(admin_account), db: Session = Depends(session_scope)):
    target = db.query(Account).filter(Account.id == account_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.id == operator.id and not active:
        raise HTTPException(status_code=409, detail="You cannot disable your own account")
    target.active = active
    audit(db, operator.id, "access.status_changed", str(target.id), {"active": active})
    db.commit()
    db.refresh(target)
    return target


@app.get("/api/v1/system/metrics", tags=["System"])
async def performance_metrics(_: Account = Depends(admin_account), db: Session = Depends(session_scope)):
    since = datetime.utcnow() - timedelta(hours=24)
    rows = db.query(ApiActivity).filter(ApiActivity.created_at >= since).all()
    errors = [row for row in rows if row.status_code >= 400]
    slow = sorted(rows, key=lambda row: row.duration_ms, reverse=True)[:8]
    return {
        "requests_24h": len(rows),
        "error_rate": round(len(errors) / max(len(rows), 1) * 100, 2),
        "average_ms": round(sum(row.duration_ms for row in rows) / max(len(rows), 1), 2),
        "slow_requests": [{"method": row.method, "path": row.path, "duration_ms": row.duration_ms, "status_code": row.status_code} for row in slow],
    }


@app.get("/api/v1/system/activity", tags=["System"])
async def activity_logs(q: str = "", _: Account = Depends(admin_account), db: Session = Depends(session_scope)):
    query = db.query(AuditEvent)
    if q:
        query = query.filter(AuditEvent.event_name.ilike(f"%{q}%"))
    rows = query.order_by(AuditEvent.created_at.desc()).limit(50).all()
    return [{"event_name": row.event_name, "reference": row.reference, "notes": row.notes, "created_at": row.created_at} for row in rows]
