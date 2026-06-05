import React, { useCallback, useEffect, useState } from "react";
import gateway from "./services/gateway";
import { useIdentity } from "./state/IdentityProvider";
import EntryScreen from "./views/EntryScreen";
import ControlShell from "./views/ControlShell";
import OverviewDesk from "./views/OverviewDesk";
import ImportDesk from "./views/ImportDesk";
import ScenarioDesk from "./views/ScenarioDesk";
import ExportDesk from "./views/ExportDesk";
import AdminDesk from "./views/AdminDesk";
import AnalyticsDesk from "./views/AnalyticsDesk";
import MonitoringDesk from "./views/MonitoringDesk";
import AutomationDesk from "./views/AutomationDesk";
import IntegrationsDesk from "./views/IntegrationsDesk";
import ProfileDesk from "./views/ProfileDesk";

export default function Workspace() {
  const { account } = useIdentity();
  const [desk, setDesk] = useState("overview");
  const [workbooks, setWorkbooks] = useState([]);
  const [activeWorkbook, setActiveWorkbook] = useState("");
  const [insights, setInsights] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(null);
  const [dimensions, setDimensions] = useState({ items: [], segments: [], markets: [] });
  const [filters, setFilters] = useState({ q: "", segment: "", market: "" });
  const [theme, setTheme] = useState(() => localStorage.getItem("enhancement_theme") || "light");

  useEffect(() => {
    document.body.classList.toggle("dark", theme === "dark");
    localStorage.setItem("enhancement_theme", theme);
  }, [theme]);

  const loadWorkbooks = useCallback(async () => {
    const { data } = await gateway.get("/workbooks?size=100");
    setWorkbooks(data.records || []);
    if (!activeWorkbook && data.records?.length) setActiveWorkbook(String(data.records[0].id));
  }, [activeWorkbook]);

  const loadAlerts = useCallback(async () => {
    const { data } = await gateway.get("/alerts");
    setAlerts(data);
  }, []);

  const loadInsights = useCallback(async () => {
    if (!activeWorkbook) {
      setInsights(null);
      return;
    }
    setBusy(true);
    try {
      const { data } = await gateway.get(`/insights/${activeWorkbook}`, { params: filters });
      setInsights(data);
    } finally {
      setBusy(false);
    }
  }, [activeWorkbook, filters]);

  const loadLive = useCallback(async () => {
    if (!activeWorkbook) return setLive(null);
    const { data } = await gateway.get(`/live/${activeWorkbook}`, { params: { segment: filters.segment, market: filters.market } });
    setLive(data);
  }, [activeWorkbook, filters.market, filters.segment]);

  const loadDimensions = useCallback(async () => {
    if (!activeWorkbook) return setDimensions({ items: [], segments: [], markets: [] });
    const { data } = await gateway.get(`/workbooks/${activeWorkbook}/dimensions`);
    setDimensions(data);
  }, [activeWorkbook]);

  const refresh = async () => {
    await loadWorkbooks();
    await loadAlerts();
    await loadInsights();
    await loadLive();
  };

  useEffect(() => {
    if (account) {
      loadWorkbooks();
      loadAlerts();
    }
  }, [account, loadWorkbooks, loadAlerts]);

  useEffect(() => {
    if (account) {
      loadInsights();
      loadLive();
      loadDimensions();
    }
  }, [account, loadInsights, loadLive, loadDimensions]);

  useEffect(() => {
    if (!account || !activeWorkbook) return undefined;
    const timer = window.setInterval(() => {
      loadInsights();
      loadLive();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [account, activeWorkbook, loadInsights, loadLive]);

  if (!account) return <EntryScreen />;

  const shared = { workbooks, activeWorkbook, setActiveWorkbook, insights, busy, refresh, live, filters, setFilters, dimensions };

  return (
    <ControlShell desk={desk} setDesk={setDesk} alerts={alerts} refreshAlerts={loadAlerts} theme={theme} setTheme={setTheme}>
      {desk === "overview" && <OverviewDesk {...shared} />}
      {desk === "analytics" && <AnalyticsDesk {...shared} />}
      {desk === "import" && <ImportDesk afterImport={async (id) => { setActiveWorkbook(String(id)); await refresh(); setDesk("scenarios"); }} />}
      {desk === "scenarios" && <ScenarioDesk {...shared} />}
      {desk === "automation" && <AutomationDesk {...shared} />}
      {desk === "integrations" && <IntegrationsDesk />}
      {desk === "exports" && <ExportDesk {...shared} />}
      {desk === "profile" && <ProfileDesk />}
      {desk === "admin" && <AdminDesk />}
      {desk === "monitoring" && <MonitoringDesk {...shared} />}
    </ControlShell>
  );
}
