import { useState, useCallback, useEffect, useRef } from "react";
import { AppShell } from "../components/AppShell";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, AlertOctagon, RotateCcw, Power } from "lucide-react";
import { useHostRuntime } from "../hooks/useHostRuntime";
import { putJson } from "../utils/api";
import { useNotificationStore } from "../stores/notificationStore";

type MotionAck = {
  success?: boolean;
  accepted?: boolean;
  queued?: boolean;
  commandType?: string;
  commandId?: string;
  queuedAtMs?: number;
  payload?: Record<string, unknown>;
};

export function MotionContent() {
  const notify = useNotificationStore(s => s.push);
  const { health } = useHostRuntime();
  const [speed, setSpeed] = useState(50);
  const [duration, setDuration] = useState(1.0);
  const holdInterval = useRef<NodeJS.Timeout | null>(null);
  const headingClass = "text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--ts-muted)] sm:text-sm sm:tracking-[0.3em]";
  const navBtnClass = "ts-surface-card flex h-16 w-16 touch-manipulation items-center justify-center rounded-[1.15rem] text-[var(--ts-text)] transition-all duration-200 hover:border-[color:var(--ts-border-strong)] hover:bg-[color:var(--ts-surface-bg-strong)] active:scale-[0.98] sm:h-24 sm:w-24 sm:rounded-[1.45rem]";
  const navIconClass = "h-7 w-7 stroke-[2.15] sm:h-9 sm:w-9";
  const actionCardClass = "ts-surface-card group flex h-32 flex-col items-center justify-center rounded-[1.3rem] px-3 text-[var(--ts-text)] transition-colors hover:border-[color:var(--ts-border-strong)] hover:bg-[color:var(--ts-surface-bg-strong)] sm:aspect-square sm:h-auto sm:rounded-[1.45rem] sm:px-4";

  useEffect(() => {
    return () => {
      if (holdInterval.current) {
        clearInterval(holdInterval.current);
        holdInterval.current = null;
      }
    };
  }, []);

  const motionUnavailable = health?.services?.motion && health.services.motion.ready === false;

  const move = useCallback(async (dir: string) => {
    if (motionUnavailable) {
      notify({ kind: "error", title: "Motion Offline", message: "Motion backend is not ready on host", ttlMs: 3000 });
      return;
    }
    try {
      await putJson<MotionAck>("/api/motion/move", { direction: dir, speed, durationMs: Math.round(duration * 1000) });
    } catch {
      notify({ kind: "error", title: "Motion Error", message: "Failed to dispatch command", ttlMs: 3000 });
    }
  }, [speed, duration, notify, motionUnavailable]);

  const halt = useCallback(async () => {
    if (motionUnavailable) {
      notify({ kind: "error", title: "Motion Offline", message: "Motion backend is not ready on host", ttlMs: 3000 });
      return;
    }
    try {
      const response = await putJson<MotionAck>("/api/motion/stop", {});
      notify({
        kind: "warning",
        title: response.queued ? "Halt Queued" : "Halt Sent",
        message: "Emergency stop command accepted by host.",
        ttlMs: 2600,
      });
    }
    catch { notify({ kind: "error", title: "Halt Error", message: "Emergency stop failed", ttlMs: 3000 }); }
  }, [motionUnavailable, notify]);

  const calibrate = useCallback(async () => {
    if (motionUnavailable) {
      notify({ kind: "error", title: "Servo Offline", message: "Motion backend is not ready on host", ttlMs: 3000 });
      return;
    }
    try {
      const response = await putJson<MotionAck>("/api/motion/calibrate", {});
      notify({
        kind: "success",
        title: response.queued ? "Servo Queued" : "Servo Sent",
        message: "Neutral calibration pose accepted by host.",
        ttlMs: 3000,
      });
    } catch {
      notify({ kind: "error", title: "Servo Error", message: "Calibration command failed", ttlMs: 3000 });
    }
  }, [motionUnavailable, notify]);

  const wakeAi = useCallback(async () => {
    try {
      await putJson("/api/ai/wake", {});
      notify({ kind: "success", title: "AI Wake", message: "Audio core set to active", ttlMs: 3000 });
    } catch {
      notify({ kind: "error", title: "AI Wake Error", message: "Wake request failed", ttlMs: 3000 });
    }
  }, [notify]);

  const handlePointerDown = (dir: string) => {
    if (holdInterval.current) clearInterval(holdInterval.current);
    void move(dir);
    // Continuous movement if held
    holdInterval.current = setInterval(() => void move(dir), 300);
  };
  const handlePointerUp = () => {
    if (holdInterval.current) {
      clearInterval(holdInterval.current);
      holdInterval.current = null;
    }
    void putJson<MotionAck>("/api/motion/stop", {}).catch(() => {
      notify({ kind: "error", title: "Motion Error", message: "Failed to stop movement", ttlMs: 3000 });
    });
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 pt-0 sm:gap-16 sm:pt-4 md:flex-row animate-[ts-fade-in_0.5s_ease-out]">
      {motionUnavailable ? (
        <div className="ts-surface-card md:col-span-2 mb-2 rounded-[1.25rem] px-4 py-3 text-xs uppercase tracking-[0.18em] text-amber-500">
          Motion backend is running in degraded mode on host.
        </div>
      ) : null}
        
      {/* Left: Steering Pad (D-Pad) */}
      <div className="w-full md:w-1/2 flex flex-col items-center">
        <h3 className={`mb-4 w-full text-center sm:mb-12 md:text-left ${headingClass}`}>
          Directional Control
        </h3>

        <div className="grid select-none grid-cols-3 grid-rows-3 gap-2.5 touch-none sm:gap-4">
          <div className="col-start-2">
            <button 
              onPointerDown={() => handlePointerDown("forward")} onPointerUp={handlePointerUp} onPointerLeave={handlePointerUp} onPointerCancel={handlePointerUp}
              className={navBtnClass} aria-label="Forward">
              <ArrowUp className={navIconClass} />
            </button>
          </div>
          <div className="row-start-2 col-start-1">
            <button 
              onPointerDown={() => handlePointerDown("left")} onPointerUp={handlePointerUp} onPointerLeave={handlePointerUp} onPointerCancel={handlePointerUp}
              className={navBtnClass} aria-label="Left">
              <ArrowLeft className={navIconClass} />
            </button>
          </div>
          <div className="row-start-2 col-start-2 flex items-center justify-center">
            <div className="h-2.5 w-2.5 rounded-full bg-[color:var(--ts-border-strong)] shadow-[0_0_0_4px_rgba(148,163,184,0.14)]" />
          </div>
          <div className="row-start-2 col-start-3">
            <button 
              onPointerDown={() => handlePointerDown("right")} onPointerUp={handlePointerUp} onPointerLeave={handlePointerUp} onPointerCancel={handlePointerUp}
              className={navBtnClass} aria-label="Right">
              <ArrowRight className={navIconClass} />
            </button>
          </div>
          <div className="row-start-3 col-start-2">
            <button 
              onPointerDown={() => handlePointerDown("backward")} onPointerUp={handlePointerUp} onPointerLeave={handlePointerUp} onPointerCancel={handlePointerUp}
              className={navBtnClass} aria-label="Backward">
              <ArrowDown className={navIconClass} />
            </button>
          </div>
        </div>
      </div>

      {/* Right: Telemetry & Sliders */}
      <div className="w-full md:w-1/2 flex flex-col">
        <h3 className={`mb-4 sm:mb-12 ${headingClass}`}>
          Propulsion Parameters
        </h3>

        <div className="space-y-6 sm:space-y-12">
          <div>
            <div className="flex justify-between items-end mb-4">
              <label className="text-sm font-semibold tracking-widest uppercase text-[var(--ts-muted)]">Velocity Limit</label>
              <div className="text-[1.75rem] font-medium tracking-tight text-[var(--ts-text)] sm:text-4xl">{speed}<span className="ml-1 text-base text-[var(--ts-muted)] sm:text-xl">%</span></div>
            </div>
            <input 
              type="range" min="10" max="100" step="10" value={speed} 
              onChange={(e) => setSpeed(Number(e.target.value))}
              className="ts-slider mt-2" 
              title="Speed"
            />
          </div>

          <div>
            <div className="flex justify-between items-end mb-4">
              <label className="text-sm font-semibold tracking-widest uppercase text-[var(--ts-muted)]">Step Duration</label>
              <div className="text-[1.75rem] font-medium tracking-tight text-[var(--ts-text)] sm:text-4xl">{duration.toFixed(1)}<span className="ml-1 text-base text-[var(--ts-muted)] sm:text-xl">s</span></div>
            </div>
            <input 
              type="range" min="0.1" max="5.0" step="0.1" value={duration} 
              onChange={(e) => setDuration(Number(e.target.value))}
              className="ts-slider mt-2" 
              title="Duration"
            />
          </div>
        </div>

        <div className="mt-8 grid grid-cols-2 gap-3 border-t border-[color:var(--ts-border)] pt-5 sm:mt-16 sm:gap-4 sm:pt-8">
          <button onClick={() => void calibrate()} className={actionCardClass}>
            <RotateCcw className="mb-3 h-6 w-6 stroke-[1.6] text-[var(--ts-text)]" />
            <span className="text-[10px] font-semibold tracking-widest uppercase text-[var(--ts-text)]">Calibrate Servos</span>
          </button>
          <button onClick={() => void wakeAi()} className={actionCardClass}>
            <Power className="mb-3 h-6 w-6 stroke-[1.6] text-[var(--ts-text)]" />
            <span className="text-[10px] font-semibold tracking-widest uppercase text-[var(--ts-text)]">Wake Up AI</span>
          </button>
          <button onClick={halt} className="col-span-full mt-2 flex flex-col items-center justify-center rounded-[1.6rem] border border-red-700/35 bg-red-600/88 p-5 font-semibold uppercase tracking-[0.2em] text-white shadow-[0_16px_34px_rgba(220,38,38,0.22)] transition-colors hover:bg-red-700 sm:mt-4 sm:p-8 sm:tracking-[0.3em]">
            <AlertOctagon className="mb-3 h-7 w-7 sm:mb-4 sm:h-8 sm:w-8" strokeWidth={1.5} />
            Total Engine Halt
          </button>
        </div>
      </div>

    </div>
  );
}

export default function Motion() {
  return (
    <AppShell title="MANUAL MOTION">
      <MotionContent />
    </AppShell>
  );
}
