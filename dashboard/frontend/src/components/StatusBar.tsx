import { Activity, Thermometer, Eye, Mic, AlertTriangle, ShieldCheck, ShieldAlert, PauseCircle } from "lucide-react";
import { cn } from "../lib/utils";
import { useRobotStatus, RobotMode, ThermalLevel, AudioState } from "../hooks/useRobotStatus";
import { useState } from "react";
import { ModeSelector } from "./ModeSelector";

export function StatusBar() {
  const { status, error, isLoading } = useRobotStatus();
  const [isModeSelectorOpen, setIsModeSelectorOpen] = useState(false);

  if (error) {
    return (
      <div className="flex w-full items-center justify-center bg-red-500/10 py-2 text-xs font-medium text-red-500 border-b border-red-500/20 animate-in fade-in slide-in-from-top-2">
        <AlertTriangle className="mr-2 h-3 w-3" />
        Connection Lost - Retrying...
      </div>
    );
  }

  if (isLoading && !status) {
    return <StatusBarSkeleton />;
  }

  if (!status) return null;

  return (
    <>
      <div className="flex w-full flex-col md:flex-row items-stretch md:items-center gap-2 md:gap-4 border-b border-white/5 bg-[#0B1221]/60 px-4 md:px-6 py-2 transition-all duration-300">
        <div className="flex flex-1 items-center justify-between md:justify-start gap-4">
          <ModeIndicator
            mode={status.state.mode}
            onClick={() => setIsModeSelectorOpen(true)}
          />
          <div className="hidden md:block h-4 w-px bg-white/10" />
          <HeartbeatIndicator healthy={status.heartbeat_healthy} />
          <div className="hidden md:block h-4 w-px bg-white/10" />
          <ThermalIndicator level={status.state.thermal_level} temp={status.state.temp_c} />
        </div>

        {/* Mobile Divider */}
        <div className="h-px w-full bg-white/5 md:hidden" />

        <div className="flex items-center justify-between md:justify-end gap-4">
          <VisionIndicator layer={status.state.vision_layer} />
          {status.state.audio_state !== "SLEEP" && (
            <>
              <div className="hidden md:block h-4 w-px bg-white/10" />
              <AudioIndicator state={status.state.audio_state} />
            </>
          )}
        </div>
      </div>

      <ModeSelector
        isOpen={isModeSelectorOpen}
        onClose={() => setIsModeSelectorOpen(false)}
        currentMode={status.state.mode}
      />
    </>
  );
}

function StatusBarSkeleton() {
  return (
    <div className="flex w-full flex-col md:flex-row items-center gap-4 border-b border-white/5 bg-[#0B1221]/60 px-6 py-2 animate-pulse">
      <div className="flex flex-1 items-center gap-4 w-full md:w-auto">
        <div className="h-6 w-24 rounded-full bg-white/5" />
        <div className="hidden md:block h-4 w-px bg-white/10" />
        <div className="h-4 w-16 bg-white/5 rounded" />
        <div className="hidden md:block h-4 w-px bg-white/10" />
        <div className="h-4 w-16 bg-white/5 rounded" />
      </div>
    </div>
  );
}

function ModeIndicator({ mode, onClick }: { mode: RobotMode; onClick: () => void }) {
  const isEmergency = mode === "EMERGENCY";
  const isNav = mode === "NAV";

  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 transition-all duration-300 hover:opacity-80 active:scale-95",
        isNav && "bg-green-500/10 text-green-400 ring-green-500/20",
        mode === "IDLE" && "bg-orange-500/10 text-orange-400 ring-orange-500/20",
        isEmergency && "bg-red-500/20 text-red-500 ring-red-500/50"
      )}
    >
      {isNav ? <ShieldCheck className="h-3 w-3 transition-transform duration-300" /> :
        mode === "IDLE" ? <PauseCircle className="h-3 w-3 transition-transform duration-300" /> :
          <ShieldAlert className="h-3 w-3 transition-transform duration-300" />}
      <span>{mode}</span>
    </button>
  );
}

function HeartbeatIndicator({ healthy }: { healthy: boolean }) {
  return (
    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground transition-colors duration-300" title="ESP32 Heartbeat">
      <Activity className={cn(
        "h-3.5 w-3.5 transition-all duration-300",
        healthy ? "text-green-500" : "text-red-500"
      )} />
      <span className="inline">ESP32</span>
    </div>
  );
}

function ThermalIndicator({ level, temp }: { level: ThermalLevel; temp: number }) {
  const getColor = () => {
    switch (level) {
      case "CRITICAL": return "text-red-500 decoration-red-500";
      case "HOT": return "text-orange-500 decoration-orange-500";
      case "WARM": return "text-yellow-500 decoration-yellow-500";
      default: return "text-blue-400 decoration-blue-400"; // Normal cool
    }
  };

  return (
    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground transition-colors duration-300">
      <Thermometer className={cn("h-3.5 w-3.5 transition-colors duration-300", getColor())} />
      <span>{temp.toFixed(1)}°C</span>
    </div>
  );
}

function VisionIndicator({ layer }: { layer: number }) {
  return (
    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
      <Eye className="h-3.5 w-3.5 text-purple-400" />
      <span>L{layer}</span>
    </div>
  );
}

function AudioIndicator({ state }: { state: AudioState }) {
  return (
    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
      <Mic className={cn(
        "h-3.5 w-3.5 transition-colors duration-300",
        state === "ACTIVE" || state === "PROCESSING" ? "text-primary" : "text-muted-foreground"
      )} />
      <span className="capitalize text-xs">{state.toLowerCase().replace('_', ' ')}</span>
    </div>
  );
}

