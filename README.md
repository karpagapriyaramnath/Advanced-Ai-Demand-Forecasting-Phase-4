# Advanced AI Demand Forecasting Enhancement

Developed for Priya

A full-stack enterprise demand intelligence platform with FastAPI, React, JWT authentication, live analytics, AI-optimized forecasting, reports, monitoring, and access controls.

## Implemented Phase 4 Enhancements

Phase 4 adds intelligent automation, enterprise integrations, advanced AI recommendations, reporting improvements, security controls, scalability updates, and new frontend management screens.

### Phase 4 Delivery

- Smart automation schedules for recurring forecast generation, configurable intervals, manual run-now execution, and automated user alerts.
- Enterprise integration management for inventory systems, ERP, external APIs, signed settings, sync tracking, and webhook intake at `/api/v1/integrations/webhook`.
- Advanced AI recommendations for product demand actions, customer segment signals, demand spikes, low-stock prediction, and inventory optimization suggestions.
- Forecast comparison, historical forecast history, confidence scores, generated business insights, and cached analytics responses.
- User profile management, password update/reset workflow, notification preferences, activity tracking, account status management, role controls, and audit logs.
- Dashboard enhancements including advanced KPI cards, live monitoring, reusable dashboard summary endpoint, and JSON summary download.
- Alert improvements with configurable alert settings, forecast completion alerts, integration sync alerts, import failure alerts, and report/export audit activity.
- Security and backend improvements including JWT role validation, API activity monitoring, secure file type validation, database indexes, SQLite compatibility migration, and analytics caching.
- Frontend improvements with Automation, Integrations, Profile, Admin status controls, dashboard summary download, and corrected API URL handling.

## Enterprise Features

- Live dashboard refresh and sales monitoring every 15 seconds.
- Ensemble forecasting, automated model retraining, anomaly detection, and seasonal analysis.
- Region/category analytics, revenue prediction, inventory risk intelligence, and AI insight narratives.
- Roles: `super_admin`, `analyst`, and `viewer`; the first registered account becomes Super Admin.
- Global search, advanced dashboard filters, dark/light mode, forecast history, API metrics, and audit logs.
- Excel analytics summary/forecast comparison workbook and PDF executive insight brief.

Analysts can import workbooks and run forecasting operations. Viewers have read-only dashboard access. Super Admins can assign roles and review system monitoring.

## Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn server.app:app --reload --host 127.0.0.1 --port 8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Frontend

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5274 --strictPort
```

App:

```text
http://127.0.0.1:5274
```

Register the first user to become Super Admin, import `sample_priya_demand.csv`, and run an Ensemble scenario to populate all analytics panels.
