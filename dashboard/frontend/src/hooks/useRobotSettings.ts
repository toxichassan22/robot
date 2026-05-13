import { useCallback, useEffect } from "react";
import { create } from "zustand";
import { useSettingsStore, type ExecutionDevice, type SettingsProfile, type SettingsState } from "../stores/settingsStore";
import { getJson } from "../utils/api";

type RobotSettingsDto = {
  version: number;
  updatedAtMs: number;
  provider?: "ollama";
  allowedTopics: string[];
  robotLanguage: string;
  sttLang?: string;
  ttsLang?: string;
  ttsVoiceGender: "male" | "female";
  ttsProvider?: "gemini" | "edge" | "pyttsx3" | "gtts" | "coqui" | "chatterbox";
  chatterboxBaseUrl?: string;
  chatterboxInstallDir?: string;
  chatterboxVoiceMode?: "predefined" | "clone";
  chatterboxReferenceAudio?: string;
  ttsCacheDir?: string;
  ttsVoiceURI?: string;
  ttsRate?: number;
  gestureDetectionEnabled?: boolean;
  cameraResolution?: string;
  cameraFps?: number;
  gestureBindings?: Record<string, string>;
  ollamaBaseUrl: string;
  ollamaModel: string;
  llmDevice?: ExecutionDevice;
  vlmBaseUrl?: string;
  vlmModel?: string;
  vlmDevice?: ExecutionDevice;
  themePreference?: "light" | "dark" | "auto";
  llmCacheEnabled?: boolean;
  profiles?: SettingsProfile[];
  activeProfileId?: string;
};

type RobotSettingsResponse = { success: boolean; settings?: RobotSettingsDto; error?: string };

type LoadResult = { ok: boolean; fromCache: boolean; error?: string };

type RobotSettingsLoadState = {
  status: "idle" | "loading" | "success" | "error";
  error: string | null;
  loadedAtMs: number;
  setState: (patch: Partial<Omit<RobotSettingsLoadState, "setState">>) => void;
};

const useRobotSettingsLoadStore = create<RobotSettingsLoadState>((set) => ({
  status: "idle",
  error: null,
  loadedAtMs: 0,
  setState: (patch) => set(patch),
}));

let inFlight: Promise<LoadResult> | null = null;

function normalizeTopics(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  const items = v
    .map((x) => String(x ?? "").trim())
    .filter(Boolean)
    .slice(0, 50);
  return Array.from(new Set(items));
}

function normalizeString(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

function normalizeGender(v: unknown): "male" | "female" {
  return normalizeString(v).toLowerCase() === "male" ? "male" : "female";
}

function normalizeTtsProvider(v: unknown): "gemini" | "edge" | "pyttsx3" | "gtts" | "coqui" | "chatterbox" {
  const s = normalizeString(v).toLowerCase();
  if (s === "gemini") return "gemini";
  if (s === "edge") return "edge";
  if (s === "pyttsx3") return "pyttsx3";
  if (s === "gtts") return "gtts";
  if (s === "coqui") return "coqui";
  if (s === "chatterbox") return "chatterbox";
  return "edge";
}

function normalizeChatterboxVoiceMode(v: unknown): SettingsState["chatterboxVoiceMode"] {
  return normalizeString(v).toLowerCase() === "clone" ? "clone" : "predefined";
}

function normalizeBool(v: unknown, fallback: boolean): boolean {
  if (typeof v === "boolean") return v;
  const s = normalizeString(v).toLowerCase();
  if (s === "1" || s === "true" || s === "yes" || s === "on") return true;
  if (s === "0" || s === "false" || s === "no" || s === "off") return false;
  return fallback;
}

function normalizeNum(v: unknown, fallback: number): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeGestureBindings(v: unknown): Record<string, string> {
  if (!v || typeof v !== "object" || Array.isArray(v)) return {};
  const out: Record<string, string> = {};
  for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
    const key = String(k || "").trim().toLowerCase();
    const s = typeof val === "string" ? val.trim() : "";
    if (key && s) out[key] = s;
  }
  return out;
}

function normalizeThemePreference(v: unknown): SettingsState["themePreference"] {
  const s = normalizeString(v).toLowerCase();
  if (s === "light" || s === "dark") return s;
  return "auto";
}

function normalizeExecutionDevice(v: unknown, fallback: ExecutionDevice): ExecutionDevice {
  return normalizeString(v).toLowerCase() === "gpu" ? "gpu" : normalizeString(v).toLowerCase() === "cpu" ? "cpu" : fallback;
}

function normalizeProfiles(v: unknown): SettingsProfile[] {
  if (!Array.isArray(v)) return [];

  const profiles: SettingsProfile[] = [];
  for (const entry of v) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const raw = entry as Record<string, unknown>;
    const id = normalizeString(raw.id);
    const name = normalizeString(raw.name);
    if (!id || !name) continue;

    const settingsRaw =
      raw.settings && typeof raw.settings === "object" && !Array.isArray(raw.settings)
        ? (raw.settings as Record<string, unknown>)
        : {};

    profiles.push({
      id,
      name,
      createdAtMs: normalizeNum(raw.createdAtMs, Date.now()),
      settings: {
        provider: "ollama",
        ollamaBaseUrl: normalizeString(settingsRaw.ollamaBaseUrl) || "http://127.0.0.1:11434",
        ollamaModel: normalizeString(settingsRaw.ollamaModel) || "gemma3:4b",
        llmDevice: normalizeExecutionDevice(settingsRaw.llmDevice, "cpu"),
        vlmBaseUrl: normalizeString(settingsRaw.vlmBaseUrl) || "http://127.0.0.1:11434",
        vlmModel: normalizeString(settingsRaw.vlmModel) || "moondream:latest",
        vlmCloudUrl: normalizeString(settingsRaw.vlmCloudUrl),
        vlmCloudModel: normalizeString(settingsRaw.vlmCloudModel),
        vlmOnline: normalizeBool(settingsRaw.vlmOnline, false),
        vlmDevice: normalizeExecutionDevice(settingsRaw.vlmDevice, "gpu"),
        allowedTopics: normalizeTopics(settingsRaw.allowedTopics),
        robotLanguage: normalizeString(settingsRaw.robotLanguage) || "ar-EG",
        ttsVoiceGender: normalizeGender(settingsRaw.ttsVoiceGender),
        ttsProvider: normalizeTtsProvider(settingsRaw.ttsProvider),
        chatterboxBaseUrl: normalizeString(settingsRaw.chatterboxBaseUrl) || "http://127.0.0.1:8004",
        chatterboxInstallDir: normalizeString(settingsRaw.chatterboxInstallDir),
        chatterboxVoiceMode: normalizeChatterboxVoiceMode(settingsRaw.chatterboxVoiceMode),
        chatterboxReferenceAudio: normalizeString(settingsRaw.chatterboxReferenceAudio),
        ttsCacheDir: normalizeString(settingsRaw.ttsCacheDir) || "./data/tts_cache",
        gestureDetectionEnabled: normalizeBool(settingsRaw.gestureDetectionEnabled, true),
        gestureBindings: normalizeGestureBindings(settingsRaw.gestureBindings),
        cameraResolution: normalizeString(settingsRaw.cameraResolution) || "640x480",
        cameraFps: normalizeNum(settingsRaw.cameraFps, 15),
        sttLang: normalizeString(settingsRaw.sttLang) || normalizeString(settingsRaw.robotLanguage) || "ar-EG",
        sttOnline: normalizeBool(settingsRaw.sttOnline, true),
        ttsLang: normalizeString(settingsRaw.ttsLang) || normalizeString(settingsRaw.robotLanguage) || "ar-EG",
        ttsOnline: normalizeBool(settingsRaw.ttsOnline, true),
        ttsVoiceURI: normalizeString(settingsRaw.ttsVoiceURI),
        ttsRate: normalizeNum(settingsRaw.ttsRate, 1),
        themePreference: normalizeThemePreference(settingsRaw.themePreference),
        llmCacheEnabled: normalizeBool(settingsRaw.llmCacheEnabled, true),
      },
    });
  }

  return profiles.slice(0, 20);
}

export function useRobotSettings(args?: { autoLoad?: boolean }) {
  const autoLoad = Boolean(args?.autoLoad);

  const setSettings = useSettingsStore((s: SettingsState) => s.set);
  const currentBaseUrl = useSettingsStore((s: SettingsState) => s.ollamaBaseUrl);
  const currentModel = useSettingsStore((s: SettingsState) => s.ollamaModel);

  const status = useRobotSettingsLoadStore((s) => s.status);
  const error = useRobotSettingsLoadStore((s) => s.error);
  const loadedAtMs = useRobotSettingsLoadStore((s) => s.loadedAtMs);
  const setLoadState = useRobotSettingsLoadStore((s) => s.setState);

  const load = useCallback(
    async (opts?: { force?: boolean }): Promise<LoadResult> => {
      const force = Boolean(opts?.force);
      const snapshot = useRobotSettingsLoadStore.getState();

      if (!force && snapshot.status === "success") {
        return { ok: true, fromCache: true };
      }

      if (inFlight) return await inFlight;

      inFlight = (async () => {
        setLoadState({ status: "loading", error: null });
        try {
          const r = await getJson<RobotSettingsResponse>("/api/robot-settings");
          if (!r.success || !r.settings) {
            const msg = r.error || "فشل تحميل إعدادات الروبوت";
            setLoadState({ status: "error", error: msg });
            return { ok: false, fromCache: false, error: msg };
          }

          const robotLanguage = normalizeString(r.settings.robotLanguage) || "ar-EG";
          const ollamaBaseUrl = normalizeString(r.settings.ollamaBaseUrl) || currentBaseUrl || "http://127.0.0.1:11434";
          const hasOllamaModel = Object.prototype.hasOwnProperty.call(r.settings, "ollamaModel");
          const ollamaModelRaw = hasOllamaModel ? r.settings.ollamaModel : undefined;
          const ollamaModel =
            !hasOllamaModel || ollamaModelRaw == null ? currentModel || "" : typeof ollamaModelRaw === "string" ? ollamaModelRaw.trim() : "";
          const profiles = normalizeProfiles((r.settings as RobotSettingsDto).profiles);
          const activeProfileId = normalizeString((r.settings as RobotSettingsDto).activeProfileId);

          setSettings({
            provider: "ollama",
            allowedTopics: normalizeTopics(r.settings.allowedTopics),
            robotLanguage,
            sttLang: normalizeString((r.settings as RobotSettingsDto).sttLang) || robotLanguage,
            ttsLang: normalizeString((r.settings as RobotSettingsDto).ttsLang) || robotLanguage,
            ttsVoiceGender: normalizeGender(r.settings.ttsVoiceGender),
            ttsProvider: normalizeTtsProvider((r.settings as RobotSettingsDto).ttsProvider),
            chatterboxBaseUrl: normalizeString((r.settings as RobotSettingsDto).chatterboxBaseUrl) || "http://127.0.0.1:8004",
            chatterboxInstallDir: normalizeString((r.settings as RobotSettingsDto).chatterboxInstallDir),
            chatterboxVoiceMode: normalizeChatterboxVoiceMode((r.settings as RobotSettingsDto).chatterboxVoiceMode),
            chatterboxReferenceAudio: normalizeString((r.settings as RobotSettingsDto).chatterboxReferenceAudio),
            ttsCacheDir: normalizeString((r.settings as RobotSettingsDto).ttsCacheDir) || "./data/tts_cache",
            ttsVoiceURI: normalizeString((r.settings as RobotSettingsDto).ttsVoiceURI),
            ttsRate: normalizeNum((r.settings as RobotSettingsDto).ttsRate, 1),
            gestureDetectionEnabled: normalizeBool((r.settings as RobotSettingsDto).gestureDetectionEnabled, true),
            gestureBindings: normalizeGestureBindings((r.settings as RobotSettingsDto).gestureBindings),
            cameraResolution: normalizeString((r.settings as RobotSettingsDto).cameraResolution) || "640x480",
            cameraFps: normalizeNum((r.settings as RobotSettingsDto).cameraFps, 15),
            ollamaBaseUrl,
            ollamaModel,
            llmDevice: normalizeExecutionDevice((r.settings as RobotSettingsDto).llmDevice, "cpu"),
            vlmBaseUrl: normalizeString((r.settings as RobotSettingsDto).vlmBaseUrl) || "http://127.0.0.1:11434",
            vlmModel: normalizeString((r.settings as RobotSettingsDto).vlmModel) || "moondream:latest",
            vlmDevice: normalizeExecutionDevice((r.settings as RobotSettingsDto).vlmDevice, "gpu"),
            themePreference: normalizeThemePreference((r.settings as RobotSettingsDto).themePreference),
            llmCacheEnabled: normalizeBool((r.settings as RobotSettingsDto).llmCacheEnabled, true),
            profiles,
            activeProfileId: profiles.some((profile) => profile.id === activeProfileId) ? activeProfileId : "",
          });

          setLoadState({ status: "success", error: null, loadedAtMs: Date.now() });
          return { ok: true, fromCache: false };
        } catch (e) {
          const msg = String(e);
          setLoadState({ status: "error", error: msg });
          return { ok: false, fromCache: false, error: msg };
        } finally {
          inFlight = null;
        }
      })();

      return await inFlight;
    },
    [currentBaseUrl, currentModel, setLoadState, setSettings],
  );

  useEffect(() => {
    if (!autoLoad) return;
    void load().catch(() => undefined);
  }, [autoLoad, load]);

  return {
    load,
    loading: status === "loading",
    status,
    error,
    loadedAtMs,
  };
}
