import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import LandingScene from "../components/LandingScene";
import { useHostRuntime } from "../hooks/useHostRuntime";
import { useTheme } from "../hooks/useTheme";

export default function Landing() {
  const { theme, isDark } = useTheme();
  const { health, phase } = useHostRuntime({ autoStart: true });
  const isDay = !isDark;
  const healthOk = Boolean(health?.success ?? (health?.status === "ok"));
  const statusLine = phase === "loading" && !health ? "CONNECTING" : healthOk ? (health?.degraded ? "DEGRADED" : "ONLINE") : "OFFLINE";
  const runtimeCaption =
    health?.host?.lanUrl ||
    health?.host?.localUrl ||
    health?.message ||
    (phase === "loading" ? "Waiting for host runtime..." : "Host runtime unavailable");

  return (
    <div
      data-testid="landing-page"
      className={`absolute inset-0 overflow-hidden font-sans tracking-wide ${isDay ? "bg-[#edf6ff] text-slate-950" : "bg-black text-white"}`}
    >
      <div className="absolute inset-0">
        <LandingScene theme={theme} />
      </div>
      <div
        className="absolute inset-0"
        style={{
          background: isDay
            ? "linear-gradient(180deg, rgba(255,255,255,0.04), rgba(15,23,42,0.08) 46%, rgba(15,23,42,0.42) 100%)"
            : "radial-gradient(circle at top, rgba(255,255,255,0.16), transparent 32%), linear-gradient(180deg, rgba(0,0,0,0.08), rgba(0,0,0,0.82))",
        }}
      />

      <div className="relative z-10 flex h-full flex-col items-center justify-center text-center animate-[ts-fade-in_1s_ease-out] px-4">
        <div
          className={`relative mb-6 flex h-14 w-14 items-center justify-center rounded-full backdrop-blur-sm sm:mb-8 sm:h-20 sm:w-20 ${
            isDay ? "border border-slate-900/12 bg-white/35" : "border border-white/20 bg-black/20"
          }`}
        >
          <div
            className={`h-7 w-7 rounded-full sm:h-10 sm:w-10 ${
              isDay
                ? "bg-[#ffd76d] shadow-[0_14px_28px_rgba(245,158,11,0.22)]"
                : "bg-white shadow-[0_0_30px_rgba(255,255,255,0.8)]"
            }`}
          />
          <div
            className={`absolute inset-0 rounded-full ${
              isDay ? "border border-slate-900/18 shadow-[0_14px_28px_rgba(15,23,42,0.08)]" : "border border-white/40 animate-[ping_3s_cubic-bezier(0,0,0.2,1)_infinite]"
            }`}
          />
        </div>

        <h1
          className={`mb-4 text-5xl font-bold leading-none tracking-tighter sm:text-8xl md:text-9xl ${
            isDay ? "text-slate-950 drop-shadow-[0_18px_36px_rgba(15,23,42,0.10)]" : "text-white drop-shadow-2xl"
          }`}
        >
          SYSTEM
          <span
            className={`mt-2 block text-3xl font-light tracking-[0.16em] sm:text-6xl md:text-7xl md:tracking-[0.2em] ${
              isDay ? "text-slate-800/70" : "text-white/50"
            }`}
          >
            {statusLine}
          </span>
        </h1>

        <Link
          to="/console"
          className={`group relative flex items-center rounded-full px-6 py-3.5 transition-all duration-500 overflow-hidden backdrop-blur-sm sm:px-12 sm:py-5 ${
            isDay
              ? "bg-slate-950/80 hover:bg-slate-950 text-white border border-slate-950/10 hover:border-slate-950/80"
              : "bg-white/5 hover:bg-white text-white hover:text-black border border-white/20 hover:border-white"
          }`}
        >
          <div
            className={`absolute inset-0 translate-y-full group-hover:translate-y-0 transition-transform duration-500 ease-out ${
              isDay ? "bg-white/10" : "bg-white/20"
            }`}
          />
          
          <span className="relative z-10 flex items-center gap-3 text-[11px] font-bold tracking-[0.22em] uppercase sm:text-sm sm:tracking-[0.3em]">
            ابدأ التحكم
            <ChevronRight className="h-4 w-4 sm:h-5 sm:w-5 transform group-hover:translate-x-2 transition-transform duration-300" />
          </span>
        </Link>

        <div className={`mt-4 max-w-[28rem] px-4 text-[10px] font-mono tracking-[0.18em] uppercase sm:mt-5 sm:text-[11px] ${isDay ? "text-slate-700/80" : "text-white/60"}`}>
          {runtimeCaption}
        </div>
      </div>

      <div
        className={`absolute left-0 right-0 text-center pointer-events-none ${isDay ? "opacity-70" : "opacity-50"}`}
        style={{ bottom: "max(1.5rem, calc(env(safe-area-inset-bottom, 0px) + 1rem))" }}
      >
        <div
          className="w-[1px] h-12 mx-auto mb-4"
          style={{
            background: isDay
              ? "linear-gradient(180deg, rgba(15,23,42,0), rgba(15,23,42,0.42), rgba(15,23,42,0))"
              : "linear-gradient(180deg, rgba(255,255,255,0), rgba(255,255,255,0.4), rgba(255,255,255,0))",
          }}
        />
        <span className={`text-[10px] font-mono tracking-[0.44em] uppercase ${isDay ? "text-slate-700" : "text-white"}`}>V.0.5 - Secure Connection</span>
      </div>
    </div>
  );
}
