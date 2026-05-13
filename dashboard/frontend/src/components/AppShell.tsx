import { useState, useEffect, useRef, useCallback, useMemo, type CSSProperties } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  HouseWifi, Compass, Settings, ShieldAlert, Cpu, Check, Activity, FlaskConical
} from "lucide-react";
import { clearRobotSessionFromStorage, describeRobotErrorCode } from "../utils/api";
import { useNotificationStore } from "../stores/notificationStore";
import { useHostRuntime } from "../hooks/useHostRuntime";
import { useTheme } from "../hooks/useTheme";
import DayClouds from "./DayClouds";

type BackgroundNode = {
  x: number;
  y: number;
  r: number;
  delay: number;
  twinkle: number;
  opacity: number;
  color: string;
  shadow: string;
};

const sparkleClipPath =
  "polygon(50% 0%, 61% 39%, 100% 50%, 61% 61%, 50% 100%, 39% 61%, 0% 50%, 39% 39%)";

function createNodePosition(isDay: boolean): { x: number; y: number } {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const x = Math.random() * 100;
    const y = Math.random() * 100;

    if (!isDay) {
      return { x, y };
    }

    const sunDx = x - 11.5;
    const sunDy = y - 10.5;
    if ((sunDx * sunDx) / (15 * 15) + (sunDy * sunDy) / (12 * 12) > 1) {
      return { x, y };
    }
  }

  return { x: 26 + Math.random() * 70, y: 18 + Math.random() * 78 };
}

function buildBackgroundNodes(compact: boolean, isDay: boolean): BackgroundNode[] {
  const targetCount = isDay ? (compact ? 14 : 24) : compact ? 42 : 92;
  const palette = isDay
    ? [
        { color: "rgba(15, 92, 255, 1)", shadow: "0 0 0 1px rgba(255,255,255,0.72), 0 0 12px rgba(96,165,250,0.58), 0 8px 22px rgba(15,92,255,0.52)" },
        { color: "rgba(255, 179, 0, 1)", shadow: "0 0 0 1px rgba(255,247,214,0.76), 0 0 12px rgba(255,179,0,0.56), 0 8px 22px rgba(249,115,22,0.46)" },
        { color: "rgba(37, 99, 235, 1)", shadow: "0 0 0 1px rgba(219,234,254,0.7), 0 0 10px rgba(37,99,235,0.52), 0 8px 20px rgba(30,64,175,0.44)" },
      ]
    : [{ color: "rgba(255,255,255,0.76)", shadow: "0 0 10px rgba(255,255,255,0.85)" }];

  return Array.from({ length: targetCount }).map((_, index) => ({
    ...(palette[index % palette.length]),
    ...createNodePosition(isDay),
    r: Math.random() * (isDay ? 2.2 : 4) + (isDay ? 1.3 : 1.8),
    delay: Math.random() * 5,
    twinkle: Math.random() * 4 + 1.6,
    opacity: Math.random() * (isDay ? 0.08 : 0.5) + (isDay ? 0.7 : 0.34),
  }));
}

// The stunning global particle network animation effect
const GlobalParticles = ({ theme }: { theme: "light" | "dark" }) => {
  const sceneRef = useRef<HTMLDivElement | null>(null);
  const [nodes, setNodes] = useState<BackgroundNode[]>([]);
  const isDay = theme === "light";

  useEffect(() => {
    const syncBackgroundDensity = () => {
      const compact = window.innerWidth < 640;
      setNodes(buildBackgroundNodes(compact, isDay));
    };

    syncBackgroundDensity();
    window.addEventListener("resize", syncBackgroundDensity);

      return () => {
      window.removeEventListener("resize", syncBackgroundDensity);
    };
  }, [isDay]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    const setPointerGlow = (x: number | string, y: number | string) => {
      scene.style.setProperty("--ts-pointer-x", typeof x === "number" ? `${x}px` : x);
      scene.style.setProperty("--ts-pointer-y", typeof y === "number" ? `${y}px` : y);
    };

    const onPointerMove = (event: PointerEvent) => {
      setPointerGlow(event.clientX, event.clientY);
    };

    const resetPointerGlow = () => {
      setPointerGlow("50%", "35%");
    };

    resetPointerGlow();
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerleave", resetPointerGlow);

    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerleave", resetPointerGlow);
    };
  }, []);

  return (
    <>
    <div
      ref={sceneRef}
      className="fixed inset-0 overflow-hidden pointer-events-none z-0"
      style={
        {
          "--ts-pointer-x": "50%",
          "--ts-pointer-y": "35%",
        } as CSSProperties
      }
    >
      <div
        className="absolute inset-0"
        style={{
          background: isDay
            ? "linear-gradient(180deg, #d4e2f3 0%, #bccfe5 36%, #96b2d0 100%)"
            : "radial-gradient(circle at 22% 52%, rgba(255,255,255,0.045), transparent 24%), radial-gradient(circle at 84% 22%, rgba(72,86,124,0.08), transparent 26%), linear-gradient(180deg, #02040a 0%, #010204 52%, #000000 100%)",
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            isDay
              ? "radial-gradient(circle 14rem at 12% 10%, rgba(255,215,106,0.14) 0%, rgba(255,232,175,0.05) 40%, transparent 68%), radial-gradient(circle 22rem at 82% 16%, rgba(96,165,250,0.08) 0%, rgba(96,165,250,0.04) 24%, transparent 56%)"
              : "radial-gradient(circle 42rem at var(--ts-pointer-x) var(--ts-pointer-y), rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.075) 18%, rgba(255,255,255,0.03) 40%, rgba(255,255,255,0.01) 62%, transparent 84%)",
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            isDay
              ? "radial-gradient(circle 16rem at var(--ts-pointer-x) var(--ts-pointer-y), rgba(15,23,42,0.06) 0%, rgba(15,23,42,0.025) 26%, rgba(15,23,42,0.01) 40%, transparent 60%)"
              : "radial-gradient(circle 6.5rem at var(--ts-pointer-x) var(--ts-pointer-y), rgba(255,255,255,0.28) 0%, rgba(255,255,255,0.11) 40%, rgba(255,255,255,0.03) 64%, transparent 78%)",
          filter: isDay ? "blur(10px)" : "blur(18px)",
        }}
      />

      {isDay ? <DayClouds variant="app" /> : null}
      {!isDay ? (
        <div className="absolute inset-0 overflow-hidden">
          <ShootingStars />
        </div>
      ) : null}

      <div className={`absolute inset-0 overflow-hidden ${isDay ? "opacity-[1]" : "opacity-[0.42]"}`}>
      {isDay ? (
        <>
          <div className="absolute left-[5%] top-[4%] z-[3] h-36 w-36">
            <div className="absolute left-1/2 top-1/2 h-32 w-32 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#f4e3af]/85 bg-white/14 shadow-[0_0_0_1px_rgba(255,247,214,0.18)]" />
            <div className="absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#ffcc66] shadow-[0_20px_42px_rgba(249,115,22,0.18)] animate-[ts-sun-breathe_10s_ease-in-out_infinite]" />
          </div>
          <div className="absolute top-[15%] right-[12%] h-[18vh] w-[24vw] rounded-full bg-[#dbeafe]/16 blur-[56px]" />
          <div className="absolute bottom-[12%] left-[24%] h-[18vh] w-[18vw] rounded-full bg-white/10 blur-[72px]" />
        </>
      ) : (
        <>
          <div className="absolute top-1/4 left-1/4 w-[60vw] h-[60vh] bg-white/[0.04] rounded-full blur-[100px] animate-[pulse_6s_ease-in-out_infinite] mix-blend-screen" />
          <div className="absolute bottom-1/4 right-1/4 w-[50vw] h-[50vw] bg-white/[0.03] rounded-full blur-[120px] animate-[pulse_10s_ease-in-out_infinite_reverse] mix-blend-screen" />
        </>
      )}
      
      {/* Immersive Grid overlay */}
      <div className="absolute inset-0" style={{
        backgroundImage: isDay
          ? 'linear-gradient(rgba(15,23,42,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,0.025) 1px, transparent 1px), radial-gradient(circle at 1px 1px, rgba(15,23,42,0.03) 1px, transparent 0)'
          : 'linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)',
        backgroundSize: isDay ? '4rem 4rem, 4rem 4rem, 1.8rem 1.8rem' : '4rem 4rem',
        maskImage: 'radial-gradient(ellipse at center, black 10%, transparent 90%)',
        WebkitMaskImage: 'radial-gradient(ellipse at center, black 10%, transparent 90%)'
      }} />

      {/* Floating bright particles */}
      {nodes.map((n, i) => (
        <div
          key={i}
          className={`absolute ${isDay ? "" : "rounded-full"}`}
          style={{
            left: `${n.x}%`,
            top: `${n.y}%`,
            width: `${isDay ? n.r * 3.1 : n.r}px`,
            height: `${isDay ? n.r * 3.1 : n.r}px`,
            opacity: n.opacity,
            background: isDay
              ? `radial-gradient(circle at 50% 50%, rgba(255,255,255,0.96) 0%, rgba(255,255,255,0.96) 8%, ${n.color} 40%, rgba(255,255,255,0) 82%)`
              : n.color,
            boxShadow: n.shadow,
            clipPath: isDay ? sparkleClipPath : undefined,
            filter: isDay ? "drop-shadow(0 0 4px rgba(255,255,255,0.4))" : undefined,
            zIndex: 1,
            animation: `ts-float ${8 + n.delay}s infinite ease-in-out, ts-twinkle ${n.twinkle}s infinite ease-in-out`,
            animationDelay: `-${n.delay}s, -${n.twinkle}s`,
          }}
        />
      ))}
      </div>
      {isDay ? (
        <>
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_38%,rgba(15,23,42,0.05),rgba(15,23,42,0.015)_22%,transparent_52%)]" />
          <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.015),rgba(15,23,42,0.02)_22%,rgba(15,23,42,0.05)_62%,rgba(15,23,42,0.12))]" />
        </>
      ) : null}
    </div>
    </>
  );
};

// Shooting stars that spawn periodically
type ShootingStar = {
  id: number;
  startX: number;
  startY: number;
  angle: number;
  duration: number;
  length: number;
};

const ShootingStars = () => {
  const [stars, setStars] = useState<ShootingStar[]>([]);
  const idRef = useRef(0);

  useEffect(() => {
    const spawnStar = () => {
      const id = ++idRef.current;
      const fromTop = Math.random() > 0.4;
      const startX = fromTop ? Math.random() * 80 + 10 : 85 + Math.random() * 15;
      const startY = fromTop ? -5 : Math.random() * 40;
      const angle = 15 + Math.random() * 30;
      const duration = 0.8 + Math.random() * 0.7;
      const length = 80 + Math.random() * 120;

      setStars((prev) => [...prev, { id, startX, startY, angle, duration, length }]);
      setTimeout(() => {
        setStars((prev) => prev.filter((s) => s.id !== id));
      }, duration * 1000 + 200);
    };

    // Spawn first star quickly
    const firstTimeout = setTimeout(spawnStar, 800);

    const interval = setInterval(() => {
      spawnStar();
      // Sometimes spawn two at once
      if (Math.random() > 0.65) {
        setTimeout(spawnStar, 150 + Math.random() * 300);
      }
    }, 2000 + Math.random() * 2500);

    return () => {
      clearTimeout(firstTimeout);
      clearInterval(interval);
    };
  }, []);

  return (
    <>
      {stars.map((star) => (
        <div
          key={star.id}
          className="absolute"
          style={{
            left: `${star.startX}%`,
            top: `${star.startY}%`,
            transform: `rotate(${star.angle}deg)`,
          }}
        >
          <div
            className="ts-shooting-star"
            style={{
              width: `${star.length}px`,
              animationDuration: `${star.duration}s`,
            }}
          >
            <div
              className="absolute right-0 top-1/2 -translate-y-1/2 w-[3px] h-[3px] rounded-full bg-white"
              style={{ boxShadow: '0 0 6px 2px rgba(255,255,255,0.9), 0 0 14px 4px rgba(255,255,255,0.4)' }}
            />
            <div className="absolute right-[2px] top-1/2 -translate-y-1/2 h-[1.5px] bg-gradient-to-l from-white/90 via-white/30 to-transparent w-full rounded-full" />
            <div className="absolute right-[1px] top-1/2 -translate-y-1/2 h-[5px] bg-gradient-to-l from-white/20 via-white/5 to-transparent w-[60%] rounded-full blur-[2px]" />
          </div>
        </div>
      ))}
    </>
  );
};

// Bottom Dock with smooth sliding indicator
type NavItem = { to: string; icon: React.ComponentType<any>; label: string };

const BottomDock = ({ navItems, currentPath, theme }: { navItems: NavItem[]; currentPath: string; theme: "light" | "dark" }) => {
  const navRef = useRef<HTMLElement | null>(null);
  const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  const [indicatorStyle, setIndicatorStyle] = useState<{ x: number; size: number } | null>(null);
  const [isFirstRender, setIsFirstRender] = useState(true);
  const isDay = theme === "light";

  const activeIndex = useMemo(() => {
    return navItems.findIndex(
      (item) => currentPath === item.to || (item.to !== "/" && currentPath.startsWith(item.to))
    );
  }, [navItems, currentPath]);

  const updateIndicator = useCallback(() => {
    const nav = navRef.current;
    const activeEl = itemRefs.current[activeIndex];
    if (!nav || !activeEl || activeIndex < 0) {
      setIndicatorStyle(null);
      return;
    }

    const navRect = nav.getBoundingClientRect();
    const elRect = activeEl.getBoundingClientRect();
    const size = Math.min(elRect.width, elRect.height) - 2;
    const x = elRect.left - navRect.left + (elRect.width - size) / 2;
    setIndicatorStyle({ x, size });
  }, [activeIndex]);

  useEffect(() => {
    updateIndicator();
    // After the first render, disable the "first render" flag so transitions kick in
    const timer = setTimeout(() => setIsFirstRender(false), 50);
    return () => clearTimeout(timer);
  }, [updateIndicator]);

  useEffect(() => {
    window.addEventListener("resize", updateIndicator);
    return () => window.removeEventListener("resize", updateIndicator);
  }, [updateIndicator]);

  return (
    <nav
      ref={navRef}
      className={`fixed bottom-[calc(env(safe-area-inset-bottom,0px)+0.75rem)] left-1/2 z-50 flex w-[min(calc(100vw-1.5rem),22rem)] -translate-x-1/2 items-center justify-between gap-0 rounded-full px-1.5 py-1.5 sm:bottom-6 sm:w-auto sm:gap-2 sm:p-2 ${
        isDay
          ? "border border-white/65 bg-white/72 shadow-[0_20px_45px_rgba(15,23,42,0.18)] backdrop-blur-2xl"
          : "ts-glass shadow-2xl"
      }`}
    >
      <div
        className={`pointer-events-none absolute rounded-full ${isDay ? "" : "bg-white"}`}
        style={{
          width: indicatorStyle ? `${indicatorStyle.size}px` : "40px",
          height: indicatorStyle ? `${indicatorStyle.size}px` : "40px",
          top: "50%",
          left: 0,
          transform: indicatorStyle ? `translate(${indicatorStyle.x}px, -50%)` : "translate(0px, -50%)",
          opacity: indicatorStyle ? 1 : 0,
          background: isDay ? "linear-gradient(180deg, #1d4ed8 0%, #0f172a 100%)" : undefined,
          boxShadow: isDay
            ? "0 12px 26px rgba(37,99,235,0.22), 0 4px 12px rgba(15,23,42,0.20)"
            : "0 0 0 1px rgba(255,255,255,0.98), 0 0 10px rgba(255,255,255,0.35)",
          transition: isFirstRender
            ? "none"
            : "transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), opacity 0.2s ease, width 0.25s ease, height 0.25s ease",
          zIndex: 0,
        }}
      />

      {navItems.map((item, index) => {
        const isActive = activeIndex === index;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            ref={(el) => { itemRefs.current[index] = el; }}
            className={`relative z-10 flex h-11 w-11 flex-1 items-center justify-center rounded-full p-2.5 transition-opacity duration-300 sm:h-12 sm:w-12 sm:flex-none sm:p-3 
              ${
                isDay
                  ? isActive
                    ? "text-white opacity-100"
                    : "text-slate-600 opacity-100 hover:text-slate-900"
                  : isActive
                    ? "text-black opacity-100"
                    : "text-white/70 opacity-50 hover:opacity-80"
              }`}
            title={item.label}
            aria-label={item.label}
          >
            <item.icon
              className="h-5 w-5 sm:h-6 sm:w-6"
              strokeWidth={isActive ? 2.35 : 1.65}
            />
          </NavLink>
        );
      })}
    </nav>
  );
};

export function AppShell({ title, children }: { title?: string; children: React.ReactNode }) {
  const location = useLocation();
  const mainRef = useRef<HTMLElement | null>(null);
  const { theme, isDark } = useTheme();
  const [authOpen, setAuthOpen] = useState(false);
  const [authPin, setAuthPin] = useState("");
  const [authMsg, setAuthMsg] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const { health, phase } = useHostRuntime({ autoStart: true });

  const notifications = useNotificationStore((s) => s.items);
  const isDay = !isDark;
  const chromeTone = isDay ? "text-slate-800/65" : "text-white/50";
  const healthOk = Boolean(health?.success ?? (health?.status === "ok"));
  const healthDegraded = Boolean(health?.degraded);
  const healthLabel = phase === "loading" && !health ? "Connecting" : healthOk ? (healthDegraded ? "Degraded" : "Connected") : "Offline";
  const healthTone = healthOk
    ? healthDegraded
      ? isDay
        ? "text-amber-600"
        : "text-amber-400"
      : isDay
        ? "text-slate-800/65"
        : "text-white/50"
    : isDay
      ? "text-rose-600"
      : "text-red-500";

  useEffect(() => {
    const handler = () => { setAuthOpen(true); setAuthMsg("Enter PIN"); };
    window.addEventListener("robot-auth:request", handler);
    return () => window.removeEventListener("robot-auth:request", handler);
  }, []);

  useEffect(() => {
    if (mainRef.current) {
      mainRef.current.scrollTop = 0;
    }
  }, [location.pathname]);

  const closeAuth = (ok: boolean) => {
    setAuthOpen(false); setAuthPin(""); setAuthMsg("");
    window.dispatchEvent(new CustomEvent("robot-auth:result", { detail: { ok } }));
  };

  const submitAuth = async () => {
    if (!authPin || authBusy) return;
    setAuthBusy(true); setAuthMsg("");
    try {
      const r = await fetch("/api/settings/auth", {
        method: "POST", headers: { "Content-Type": "application/json", "x-robot-pin": authPin }, credentials: "include",
      });
      const res = await r.json() as { sessionToken?: string; sessionExpiresAtMs?: number };
      if (r.ok && res.sessionToken) {
        try {
          sessionStorage.setItem("local-robot-tester:robot-session", res.sessionToken);
          if (typeof res.sessionExpiresAtMs === "number" && Number.isFinite(res.sessionExpiresAtMs)) {
            sessionStorage.setItem("local-robot-tester:robot-session-exp", String(res.sessionExpiresAtMs));
          }
        } catch (storageError) {
          void storageError;
        }
        closeAuth(true);
      } else {
        const code = typeof (res as { error?: unknown }).error === "string" ? String((res as { error?: unknown }).error) : null;
        setAuthMsg(describeRobotErrorCode(code) || "Authorization failed");
        clearRobotSessionFromStorage();
      }
    } catch {
      setAuthMsg("Network error");
      clearRobotSessionFromStorage();
    }
    finally { setAuthBusy(false); }
  };

  const navItems = [
    { to: "/", icon: HouseWifi, label: "Home" },
    { to: "/console", icon: Cpu, label: "Systems" },
    { to: "/motion", icon: Compass, label: "Controls" },
    { to: "/test", icon: FlaskConical, label: "Diagnostics" },
    { to: "/settings", icon: Settings, label: "Settings" },
  ];

  return (
    <div className="relative flex h-screen min-h-dvh w-screen flex-col overflow-hidden bg-[var(--ts-body-bg)] text-ts-text">
      
      {/* Global Animated Background Layer */}
      <GlobalParticles theme={theme} />

      {isDay ? (
        <div className="pointer-events-none absolute inset-0 z-[1] bg-[linear-gradient(180deg,rgba(255,255,255,0.02),rgba(255,255,255,0.01)_20%,rgba(15,23,42,0.04)_74%,rgba(15,23,42,0.08))]" />
      ) : null}
      
      {/* Invisible Top Status Area (Only visible icons) */}
      <header
        className="absolute top-0 left-0 right-0 z-40 flex items-center justify-between px-3 pb-2 pointer-events-none sm:px-8 sm:pb-3"
        style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top, 0px))" }}
      >
        <div className="flex items-center gap-2">
          {healthOk ? <Check className={`h-4 w-4 ${healthTone}`} /> : <ShieldAlert className={`h-4 w-4 ${healthTone}`} />}
          <span className={`text-[10px] sm:text-[11px] font-bold tracking-[0.18em] sm:tracking-[0.2em] uppercase ${chromeTone}`}>
            {healthLabel}
          </span>
        </div>
        <div className={`max-w-[48vw] truncate text-right text-[10px] font-bold tracking-[0.18em] uppercase sm:max-w-none sm:text-[11px] sm:tracking-[0.2em] ${chromeTone}`}>
          {title || "Interface"}
        </div>
      </header>

      {/* Main Content Area (Expands to bottom dock) */}
      <main
        ref={mainRef}
        className={`relative z-10 mx-auto flex-1 w-full max-w-6xl overflow-auto overscroll-contain px-4 pt-14 pb-28 sm:px-6 sm:pt-20 sm:pb-32 ${
          isDay ? "ts-day-content" : ""
        }`}
        style={{
          paddingTop: "max(3.5rem, calc(env(safe-area-inset-top, 0px) + 2.75rem))",
          paddingBottom: "max(7rem, calc(env(safe-area-inset-bottom, 0px) + 5.5rem))",
        }}
      >
        {children}
      </main>

      {/* Tesla-style Bottom Dock */}
      <BottomDock navItems={navItems} currentPath={location.pathname} theme={theme} />

      {/* Toasts - Minimalist */}
      <div
        className="fixed right-4 left-4 z-[60] flex flex-col gap-3 pointer-events-none sm:left-auto sm:right-8 sm:w-80"
        style={{ top: "max(4rem, calc(env(safe-area-inset-top, 0px) + 3.25rem))" }}
      >
        {notifications.map((n) => (
          <div key={n.id} className="bg-ts-panel border-l-2 border-white text-white p-4 rounded-r-xl shadow-2xl pointer-events-auto animate-[ts-slide-up_0.3s_ease-out]">
            <div className="flex items-start gap-3">
              {n.kind === "error" && <ShieldAlert className="h-4 w-4 text-red-500 mt-0.5 flex-none" />}
              {n.kind === "success" && <Activity className="h-4 w-4 text-white mt-0.5 flex-none" />}
              <div className="flex-1">
                <div className="font-semibold text-sm">{n.title}</div>
                {n.message && <div className="text-xs text-ts-muted mt-1">{n.message}</div>}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Auth Modal - Minimalist */}
      {authOpen && (
        <div className={`fixed inset-0 z-[70] flex items-center justify-center px-4 backdrop-blur-md ${isDay ? "bg-slate-950/60" : "bg-black/80"}`}>
          <div className="flex w-full max-w-sm flex-col items-center">
            <ShieldAlert className="h-8 w-8 text-white mb-6" />
            <div className="text-xl font-light mb-8">Override Required</div>
            <input
              value={authPin}
              onChange={(e) => setAuthPin(e.target.value)}
              type="password"
              inputMode="numeric"
              autoFocus
              className="mb-2 w-full border-b border-white/20 bg-transparent px-2 py-4 text-center text-3xl tracking-[0.35em] text-white transition-colors focus:border-white focus:outline-none sm:text-4xl sm:tracking-[0.5em]"
              placeholder="••••"
              onKeyDown={(e) => {
                if (e.key === "Enter") void submitAuth();
                if (e.key === "Escape") closeAuth(false);
              }}
            />
            {authMsg && <div className="text-sm text-red-500 mb-8">{authMsg}</div>}
            
            <div className="mt-8 flex gap-4 w-full">
              <button disabled={authBusy} onClick={() => closeAuth(false)} className="ts-btn flex-1 py-3.5 text-white/50 hover:text-white sm:py-4">Cancel</button>
              <button disabled={authBusy} onClick={submitAuth} className="ts-btn ts-btn-primary flex-1 rounded-full py-3.5 sm:py-4">Authorize</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
