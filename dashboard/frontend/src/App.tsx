import { Suspense, lazy } from "react";
import { BrowserRouter as Router, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ToastHost } from "./components/Toast";
import { useHostRuntime } from "./hooks/useHostRuntime";
import { useRobotSettings } from "./hooks/useRobotSettings";

const Landing = lazy(() => import("./pages/Landing"));
const SdLogicContent = lazy(() => import("./pages/SdLogic").then((module) => ({ default: module.SdLogicContent })));
const SettingsContent = lazy(() => import("./pages/Settings").then((module) => ({ default: module.SettingsContent })));
const MotionContent = lazy(() => import("./pages/Motion").then((module) => ({ default: module.MotionContent })));
const TestZoneContent = lazy(() => import("./pages/TestZone").then((module) => ({ default: module.TestZoneContent })));
const ChestDisplay = lazy(() => import("./pages/ChestDisplay").then((module) => ({ default: module.ChestDisplay })));

function ShellLayout() {
  const location = useLocation();

  const titleMap: Record<string, string> = {
    "/console": "SYSTEMS & AI",
    "/motion": "MANUAL MOTION",
    "/test": "DIAGNOSTICS & TESTING",
    "/settings": "CONFIGURATION",
  };

  return (
    <AppShell title={titleMap[location.pathname] ?? "Interface"}>
      <Outlet />
    </AppShell>
  );
}

function AppBootstrap() {
  useRobotSettings({ autoLoad: true });
  useHostRuntime({ autoStart: true });
  return null;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/chest" element={<ChestDisplay />} />
      <Route element={<ShellLayout />}>
        <Route path="/console" element={<SdLogicContent />} />
        <Route path="/motion" element={<MotionContent />} />
        <Route path="/test" element={<TestZoneContent />} />
        <Route path="/settings" element={<SettingsContent />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <Router>
      <AppBootstrap />
      <Suspense fallback={<div className="p-4 text-sm text-slate-300">Loading…</div>}>
        <AppRoutes />
      </Suspense>
      <ToastHost />
    </Router>
  );
}
