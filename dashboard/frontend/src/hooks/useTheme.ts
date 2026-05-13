import { useEffect, useMemo, useState } from "react";
import { useSettingsStore, type SettingsState, type ThemePreference } from "../stores/settingsStore";
import { useHostRuntime } from "./useHostRuntime";

export type Theme = "light" | "dark";

type ServerClock = {
  serverTimeMs: number;
  serverUtcOffsetMinutes: number;
  syncedAtMs: number;
};

const DAY_START_HOUR = 6;
const NIGHT_START_HOUR = 18;

function resolveHour(serverClock: ServerClock | null, nowMs: number): number {
  if (!serverClock) {
    return new Date(nowMs).getHours();
  }

  const serverNowMs = serverClock.serverTimeMs + (nowMs - serverClock.syncedAtMs);
  const shiftedMs = serverNowMs + serverClock.serverUtcOffsetMinutes * 60_000;
  return new Date(shiftedMs).getUTCHours();
}

export function resolveTheme(preference: ThemePreference, serverClock: ServerClock | null, nowMs = Date.now()): Theme {
  if (preference === "light" || preference === "dark") {
    return preference;
  }

  const hour = resolveHour(serverClock, nowMs);
  return hour >= DAY_START_HOUR && hour < NIGHT_START_HOUR ? "light" : "dark";
}

export function useTheme() {
  const preference = useSettingsStore((s: SettingsState) => s.themePreference);
  const set = useSettingsStore((s: SettingsState) => s.set);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const { health, loadedAtMs } = useHostRuntime();

  const serverClock = useMemo<ServerClock | null>(() => {
    if (preference !== "auto") return null;
    if (typeof health?.serverTimeMs !== "number" || typeof health?.serverUtcOffsetMinutes !== "number") {
      return null;
    }
    return {
      serverTimeMs: health.serverTimeMs,
      serverUtcOffsetMinutes: health.serverUtcOffsetMinutes,
      syncedAtMs: loadedAtMs || Date.now(),
    };
  }, [health?.serverTimeMs, health?.serverUtcOffsetMinutes, loadedAtMs, preference]);

  useEffect(() => {
    const tick = () => setNowMs(Date.now());
    tick();

    const timer = window.setInterval(tick, 30_000);
    const onVisibility = () => {
      if (!document.hidden) {
        tick();
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.clearInterval(timer);
    };
  }, [preference]);

  const theme = useMemo(() => resolveTheme(preference, serverClock, nowMs), [nowMs, preference, serverClock]);
  const isDark = theme === "dark";

  useEffect(() => {
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(theme);
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  return {
    theme,
    preference,
    setPreference: (nextPreference: ThemePreference) => set({ themePreference: nextPreference }),
    isDark,
  };
}
