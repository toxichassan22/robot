import { useMemo } from "react";
import { Activity, AlertTriangle, Cpu, Pause, Play, Wind, Zap } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { useHostRuntime } from "../hooks/useHostRuntime";
import { useNotificationStore } from "../stores/notificationStore";
import { putJson } from "../utils/api";

type SysStatus = {
  success?: boolean;
  freshAtMs?: number;
  degraded?: boolean;
  errorCode?: string | null;
  message?: string | null;
  cpuUsage: number | null;
  cpuTemp: number | null;
  ramUsage: number | null;
  uptime: number | null;
  powerDraw: number | null;
  ping: number | null;
};

type AiState = {
  success?: boolean;
  freshAtMs?: number;
  degraded?: boolean;
  errorCode?: string | null;
  message?: string | null;
  visionModel: string | null;
  voiceModel: string | null;
  isProcessing: boolean;
  currentTask: string;
  mode: string | null;
  audioState: string | null;
  visionLayer: string | null;
  speedLimit: number | null;
  coolingMode: string | null;
  servoTorque: string | null;
};

const EMPTY_SYS: SysStatus = {
  cpuUsage: null,
  cpuTemp: null,
  ramUsage: null,
  uptime: null,
  powerDraw: null,
  ping: null,
};

const EMPTY_AI: AiState = {
  visionModel: null,
  voiceModel: null,
  isProcessing: false,
  currentTask: "IDLE",
  mode: null,
  audioState: null,
  visionLayer: null,
  speedLimit: null,
  coolingMode: null,
  servoTorque: null,
};

function formatNumber(value: number | null | undefined, digits = 0): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "--";
  }
  return digits > 0 ? value.toFixed(digits) : String(Math.round(value));
}

function formatStatus(value: string | null | undefined): string {
  const text = String(value ?? "").trim();
  return text || "NOT REPORTED";
}

function formatUptime(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return "--";
  }

  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function SdLogicContent() {
  const notify = useNotificationStore((s) => s.push);
  const { system, ai: runtimeAi, phase, error, refresh } = useHostRuntime();
  const sys = useMemo(() => ({ ...EMPTY_SYS, ...(system || {}) }), [system]);
  const ai = useMemo(() => ({ ...EMPTY_AI, ...(runtimeAi || {}) }), [runtimeAi]);
  const statCardClass = "ts-surface-card rounded-[1.3rem] p-3 sm:rounded-[1.5rem] sm:p-4";
  const panelCardClass = "ts-surface-panel rounded-[1.7rem] sm:rounded-[2rem]";
  const controlRowClass = "ts-surface-card flex items-center justify-between gap-3 rounded-[1.25rem] p-3 transition-colors hover:border-[color:var(--ts-border-strong)] sm:gap-4 sm:rounded-[1.4rem] sm:p-4";
  const labelClass = "text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--ts-muted)] sm:tracking-[0.24em]";
  const subLabelClass = "text-xs font-semibold uppercase tracking-wide text-[var(--ts-muted)] sm:text-sm";
  const valueClass = "font-medium text-[var(--ts-text)]";

  const handleOverride = async (action: string) => {
    try {
      await putJson("/api/ai/override", { action });
      notify({ kind: "success", title: "Override Sent", message: action, ttlMs: 3000 });
    } catch {
      notify({ kind: "error", title: "Failed", message: "Override rejected", ttlMs: 3000 });
    }
  };

  return (
    <div className="flex flex-col gap-6 pt-0 sm:gap-12 sm:pt-4 animate-[ts-fade-in_0.5s_ease-out]">
        {phase === "loading" && !system && !runtimeAi ? (
          <div className="ts-surface-card rounded-[1.25rem] px-4 py-3 text-xs uppercase tracking-[0.18em] text-[var(--ts-muted)]">
            Connecting to host runtime...
          </div>
        ) : null}
        {(sys.degraded || ai.degraded || error) ? (
          <div className="ts-surface-card flex items-center justify-between gap-3 rounded-[1.25rem] px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <AlertTriangle className="h-4 w-4 flex-none text-amber-500" />
              <div className="min-w-0 text-xs uppercase tracking-[0.16em] text-[var(--ts-muted)]">
                {(ai.message || sys.message || error || "Host is running in degraded mode").slice(0, 180)}
              </div>
            </div>
            <button
              onClick={() => {
                void refresh(true);
              }}
              className="ts-btn ts-btn-ghost px-3 py-2 text-[10px] uppercase tracking-[0.18em]"
            >
              Refresh
            </button>
          </div>
        ) : null}
        <div className="grid grid-cols-2 gap-3 border-b border-[color:var(--ts-border)] pb-5 sm:gap-8 sm:pb-12 md:grid-cols-4">
          <div>
            <div className={`mb-2 ${labelClass}`}>Core Temp</div>
            <div className={`flex items-end text-[1.7rem] font-light tracking-tighter sm:text-6xl ${valueClass}`}>
              {formatNumber(sys.cpuTemp, 1)}
              <span className="ml-1 mb-1 text-base text-[var(--ts-muted)] sm:text-3xl">°C</span>
            </div>
          </div>
          <div>
            <div className={`mb-2 ${labelClass}`}>System Load</div>
            <div className={`flex items-end text-[1.7rem] font-light tracking-tighter sm:text-6xl ${valueClass}`}>
              {formatNumber(sys.cpuUsage)}
              <span className="ml-1 mb-1 text-base text-[var(--ts-muted)] sm:text-3xl">%</span>
            </div>
          </div>
          <div>
            <div className={`mb-2 ${labelClass}`}>Memory Use</div>
            <div className={`flex items-end text-[1.7rem] font-light tracking-tighter sm:text-6xl ${valueClass}`}>
              {formatNumber(sys.ramUsage)}
              <span className="ml-1 mb-1 text-base text-[var(--ts-muted)] sm:text-3xl">%</span>
            </div>
          </div>
          <div>
            <div className={`mb-2 ${labelClass}`}>Service Ping</div>
            <div className={`flex items-end text-[1.7rem] font-light tracking-tighter sm:text-6xl ${valueClass}`}>
              {formatNumber(sys.ping, 1)}
              <span className="ml-1 mb-1 text-base text-[var(--ts-muted)] sm:text-3xl">ms</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5 border-b border-[color:var(--ts-border)] pb-5 text-[var(--ts-text)] sm:grid-cols-4 sm:gap-4 sm:pb-10">
          <div className={statCardClass}>
            <div className={labelClass}>Uptime</div>
            <div className="mt-2 text-lg font-light text-[var(--ts-text)] sm:text-2xl">{formatUptime(sys.uptime)}</div>
          </div>
          <div className={statCardClass}>
            <div className={labelClass}>Power Draw</div>
            <div className="mt-2 text-lg font-light text-[var(--ts-text)] sm:text-2xl">
              {sys.powerDraw == null ? "--" : `${formatNumber(sys.powerDraw, 1)} W`}
            </div>
          </div>
          <div className={statCardClass}>
            <div className={labelClass}>Runtime Mode</div>
            <div className="mt-2 text-lg font-light text-[var(--ts-text)] sm:text-2xl">{formatStatus(ai.mode)}</div>
          </div>
          <div className={statCardClass}>
            <div className={labelClass}>Audio State</div>
            <div className="mt-2 text-lg font-light text-[var(--ts-text)] sm:text-2xl">{formatStatus(ai.audioState)}</div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 sm:gap-16 md:grid-cols-2">
          <div className="flex flex-col">
            <h3 className="mb-3 text-[15px] font-semibold tracking-[0.04em] text-[var(--ts-text)] sm:mb-8 sm:text-xl">Intelligence Core</h3>

            <div className={`relative mb-5 flex aspect-[5/4] w-full items-center justify-center overflow-hidden sm:mb-8 sm:aspect-video ${panelCardClass}`}>
              <div className={`absolute h-32 w-32 rounded-full border border-[color:var(--ts-border)] sm:h-48 sm:w-48 ${ai.isProcessing ? "animate-spin duration-[8s]" : ""}`} />
              <div className={`absolute h-24 w-24 rounded-full border border-[color:var(--ts-border-strong)] sm:h-32 sm:w-32 ${ai.isProcessing ? "animate-[spin_4s_linear_reverse_infinite]" : ""}`} />
              <Cpu className={`h-8 w-8 ${ai.isProcessing ? "text-[var(--ts-text)]" : "text-[var(--ts-text)]/75"} transition-colors duration-1000`} strokeWidth={1} />
            </div>

            <div className="space-y-4 sm:space-y-6">
              <div className="flex items-end justify-between gap-4 border-b border-[color:var(--ts-border)] pb-2">
                <span className={subLabelClass}>Vision Module</span>
                <span className="break-all text-right text-sm font-medium text-[var(--ts-text)] sm:text-lg">{formatStatus(ai.visionModel)}</span>
              </div>
              <div className="flex items-end justify-between gap-4 border-b border-[color:var(--ts-border)] pb-2">
                <span className={subLabelClass}>Voice Module</span>
                <span className="break-all text-right text-sm font-medium text-[var(--ts-text)] sm:text-lg">{formatStatus(ai.voiceModel)}</span>
              </div>
              <div className="flex items-end justify-between gap-4 border-b border-[color:var(--ts-border)] pb-2">
                <span className={subLabelClass}>Current Task</span>
                <span className="break-all text-right text-sm font-medium uppercase tracking-[0.16em] text-[var(--ts-text)] sm:text-lg sm:tracking-widest">{formatStatus(ai.currentTask)}</span>
              </div>
              <div className="flex items-end justify-between gap-4 border-b border-[color:var(--ts-border)] pb-2">
                <span className={subLabelClass}>Vision Layer</span>
                <span className="break-all text-right text-sm font-medium text-[var(--ts-text)] sm:text-lg">{formatStatus(ai.visionLayer)}</span>
              </div>
            </div>
          </div>

          <div className="flex flex-col">
            <h3 className="mb-3 text-[15px] font-semibold tracking-[0.04em] text-[var(--ts-text)] sm:mb-8 sm:text-xl">Hardware Control</h3>

            <div className="mb-6 grid grid-cols-2 gap-3 sm:mb-8 sm:gap-4">
              <div className={statCardClass}>
                <div className={labelClass}>Cooling Override</div>
                <div className="mt-2 text-sm font-light uppercase tracking-[0.18em] text-[var(--ts-text)] sm:text-base">{formatStatus(ai.coolingMode)}</div>
              </div>
              <div className={statCardClass}>
                <div className={labelClass}>Servo Torque</div>
                <div className="mt-2 text-sm font-light uppercase tracking-[0.18em] text-[var(--ts-text)] sm:text-base">{formatStatus(ai.servoTorque)}</div>
              </div>
              <div className={statCardClass}>
                <div className={labelClass}>Speed Limit</div>
                <div className="mt-2 text-sm font-light uppercase tracking-[0.18em] text-[var(--ts-text)] sm:text-base">
                  {ai.speedLimit == null ? "--" : `${formatNumber(ai.speedLimit * 100)}%`}
                </div>
              </div>
              <div className={statCardClass}>
                <div className={labelClass}>Loop State</div>
                <div className="mt-2 text-sm font-light uppercase tracking-[0.18em] text-[var(--ts-text)] sm:text-base">{formatStatus(ai.mode)}</div>
              </div>
            </div>

            <div className="mb-8 space-y-3 sm:mb-12 sm:space-y-4">
              <div className={controlRowClass}>
                <div className="flex items-center gap-4">
                  <Wind className="h-5 w-5 text-[var(--ts-muted)]" strokeWidth={1.5} />
                  <span className="text-xs uppercase tracking-[0.22em] text-[var(--ts-text)] sm:text-sm sm:tracking-widest">Cooling Fans</span>
                </div>
                <button onClick={() => void handleOverride("fans_max")} className="ts-btn ts-btn-ghost px-3 py-2 text-[10px] uppercase tracking-[0.24em] sm:px-4 sm:text-xs sm:tracking-widest">Force Max</button>
              </div>

              <div className={controlRowClass}>
                <div className="flex items-center gap-4">
                  <Zap className="h-5 w-5 text-[var(--ts-muted)]" strokeWidth={1.5} />
                  <span className="text-xs uppercase tracking-[0.22em] text-[var(--ts-text)] sm:text-sm sm:tracking-widest">Servo Torque</span>
                </div>
                <button onClick={() => void handleOverride("torque_release")} className="ts-btn ts-btn-ghost px-3 py-2 text-[10px] uppercase tracking-[0.24em] sm:px-4 sm:text-xs sm:tracking-widest">Release</button>
              </div>

              <div className={controlRowClass}>
                <div className="flex items-center gap-4">
                  <Activity className="h-5 w-5 text-[var(--ts-muted)]" strokeWidth={1.5} />
                  <span className="text-xs uppercase tracking-[0.22em] text-[var(--ts-text)] sm:text-sm sm:tracking-widest">System Loop</span>
                </div>
                <div className="flex gap-2">
                  <button title="Pause Loop" onClick={() => void handleOverride("loop_pause")} className="ts-btn ts-btn-ghost p-2"><Pause className="h-4 w-4" /></button>
                  <button title="Resume Loop" onClick={() => void handleOverride("loop_resume")} className="ts-btn ts-btn-ghost p-2"><Play className="h-4 w-4" /></button>
                </div>
              </div>
            </div>

            <div className="mt-auto">
              <button onClick={() => void handleOverride("emergency_halt")} className="flex w-full items-center justify-center gap-3 rounded-[1.6rem] border border-red-700/35 bg-red-600/88 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-white shadow-[0_16px_34px_rgba(220,38,38,0.2)] transition-colors hover:bg-red-700 sm:py-6 sm:text-base sm:tracking-[0.2em]">
                <AlertTriangle className="h-5 w-5" />
                Emergency Halt
              </button>
            </div>
          </div>
        </div>
    </div>
  );
}

export default function SdLogic() {
  return (
    <AppShell title="SYSTEMS & AI">
      <SdLogicContent />
    </AppShell>
  );
}
