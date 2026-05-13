import { useEffect } from "react";
import { create } from "zustand";
import { getJson } from "../utils/api";

export type ServiceCapability = {
  configured?: boolean;
  supported?: boolean;
  ready?: boolean;
  reachable?: boolean;
  degraded?: boolean;
  message?: string | null;
  [key: string]: unknown;
};

export type HostDescriptor = {
  hostname?: string | null;
  platform?: string | null;
  pythonVersion?: string | null;
  mode?: string | null;
  modeSource?: string | null;
  port?: number | null;
  localUrl?: string | null;
  lanIp?: string | null;
  lanUrl?: string | null;
};

export type HostHealthSnapshot = {
  success?: boolean;
  status?: string;
  freshAtMs?: number;
  ready?: boolean;
  degraded?: boolean;
  errorCode?: string | null;
  message?: string | null;
  serverTimeMs?: number;
  serverUtcOffsetMinutes?: number;
  serverLocalHour?: number;
  host?: HostDescriptor;
  services?: Record<string, ServiceCapability>;
};

export type SystemHealthSnapshot = {
  success?: boolean;
  freshAtMs?: number;
  degraded?: boolean;
  errorCode?: string | null;
  message?: string | null;
  host?: HostDescriptor;
  cpuUsage?: number | null;
  cpuTemp?: number | null;
  ramUsage?: number | null;
  uptime?: number | null;
  powerDraw?: number | null;
  ping?: number | null;
};

export type AiStateSnapshot = {
  success?: boolean;
  freshAtMs?: number;
  degraded?: boolean;
  errorCode?: string | null;
  message?: string | null;
  visionModel?: string | null;
  voiceModel?: string | null;
  isProcessing?: boolean;
  currentTask?: string | null;
  mode?: string | null;
  audioState?: string | null;
  visionLayer?: string | null;
  speedLimit?: number | null;
  coolingMode?: string | null;
  servoTorque?: string | null;
};

export type RobotStatusSnapshot = {
  success?: boolean;
  state?: Record<string, unknown>;
  heartbeat_healthy?: boolean;
  timestamp_ms?: number;
  error?: string;
};

type HostRuntimePhase = "idle" | "loading" | "ready";

type HostRuntimeState = {
  phase: HostRuntimePhase;
  health: HostHealthSnapshot | null;
  system: SystemHealthSnapshot | null;
  ai: AiStateSnapshot | null;
  robotStatus: RobotStatusSnapshot | null;
  error: string | null;
  loadedAtMs: number;
  lastSuccessAtMs: number;
  setState: (patch: Partial<Omit<HostRuntimeState, "setState">>) => void;
};

const useHostRuntimeStore = create<HostRuntimeState>((set) => ({
  phase: "idle",
  health: null,
  system: null,
  ai: null,
  robotStatus: null,
  error: null,
  loadedAtMs: 0,
  lastSuccessAtMs: 0,
  setState: (patch) => set(patch),
}));

let inFlight: Promise<void> | null = null;
let subscriberCount = 0;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let failureCount = 0;
let visibilityBound = false;

function withTimeout<T>(promise: Promise<T>, label: string, timeoutMs: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`${label} timed out after ${timeoutMs}ms`));
    }, timeoutMs);

    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

function firstRejectedReason(results: PromiseSettledResult<unknown>[]): string | null {
  for (const result of results) {
    if (result.status === "rejected") {
      return String(result.reason);
    }
  }
  return null;
}

function scheduleNext(delayMs: number) {
  if (pollTimer) clearTimeout(pollTimer);
  if (subscriberCount <= 0) return;
  pollTimer = setTimeout(() => {
    void tickHostRuntime();
  }, delayMs);
}

function nextDelayMs(): number {
  if (document.hidden) {
    return failureCount === 0 ? 6000 : Math.min(30000, 6000 * 2 ** Math.max(failureCount - 1, 0));
  }
  return failureCount === 0 ? 1400 : Math.min(30000, 1800 * 2 ** failureCount);
}

function bindVisibilityListener() {
  if (visibilityBound) return;
  visibilityBound = true;
  document.addEventListener("visibilitychange", onVisibilityChange);
}

function unbindVisibilityListener() {
  if (!visibilityBound) return;
  visibilityBound = false;
  document.removeEventListener("visibilitychange", onVisibilityChange);
}

function onVisibilityChange() {
  if (document.hidden) return;
  scheduleNext(120);
}

export async function refreshHostRuntime(force = false): Promise<void> {
  const store = useHostRuntimeStore.getState();
  if (inFlight) {
    return await inFlight;
  }

  inFlight = (async () => {
    if (store.phase === "idle") {
      store.setState({ phase: "loading", error: null });
    }

    const [healthResult, systemResult, aiResult, statusResult] = await Promise.allSettled([
      withTimeout(getJson<HostHealthSnapshot>("/api/health"), "health", 5000),
      withTimeout(getJson<SystemHealthSnapshot>("/api/health/system"), "system", 4500),
      withTimeout(getJson<AiStateSnapshot>("/api/ai/state"), "ai", 4500),
      withTimeout(getJson<RobotStatusSnapshot>("/api/status"), "status", 3000),
    ]);

    const results = [healthResult, systemResult, aiResult, statusResult];
    const nowMs = Date.now();
    const current = useHostRuntimeStore.getState();
    const anySuccess = results.some((result) => result.status === "fulfilled");
    const patch: Partial<Omit<HostRuntimeState, "setState">> = {
      phase: anySuccess || current.lastSuccessAtMs > 0 ? "ready" : "loading",
      loadedAtMs: nowMs,
      error: anySuccess ? null : firstRejectedReason(results),
    };

    if (healthResult.status === "fulfilled") patch.health = healthResult.value;
    if (systemResult.status === "fulfilled") patch.system = systemResult.value;
    if (aiResult.status === "fulfilled") patch.ai = aiResult.value;
    if (statusResult.status === "fulfilled") patch.robotStatus = statusResult.value;
    if (anySuccess) patch.lastSuccessAtMs = nowMs;

    current.setState(patch);
    failureCount = anySuccess ? 0 : Math.min(failureCount + 1, 5);
  })();

  try {
    await inFlight;
  } finally {
    inFlight = null;
    if (force && subscriberCount <= 0) {
      if (pollTimer) clearTimeout(pollTimer);
      pollTimer = null;
      unbindVisibilityListener();
    }
  }
}

async function tickHostRuntime() {
  if (subscriberCount <= 0) return;
  await refreshHostRuntime();
  scheduleNext(nextDelayMs());
}

export function startHostRuntimePolling(): void {
  subscriberCount += 1;
  if (subscriberCount > 1) return;
  bindVisibilityListener();
  void tickHostRuntime();
}

export function stopHostRuntimePolling(): void {
  subscriberCount = Math.max(0, subscriberCount - 1);
  if (subscriberCount > 0) return;
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
  unbindVisibilityListener();
}

export function useHostRuntime(args?: { autoStart?: boolean }) {
  const autoStart = Boolean(args?.autoStart);
  const state = useHostRuntimeStore();

  useEffect(() => {
    if (!autoStart) return;
    startHostRuntimePolling();
    return () => {
      stopHostRuntimePolling();
    };
  }, [autoStart]);

  return {
    ...state,
    refresh: async (force = true) => await refreshHostRuntime(force),
  };
}
