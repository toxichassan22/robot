import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Provider = "ollama";

export type ThemePreference = "light" | "dark" | "auto";
export type ExecutionDevice = "cpu" | "gpu";
export type ChatterboxVoiceMode = "predefined" | "clone";

export type BasicSettings = {
  provider: Provider;

  ollamaBaseUrl: string;
  ollamaModel: string;
  llmDevice: ExecutionDevice;
  vlmBaseUrl: string;
  vlmModel: string;
  vlmCloudUrl: string;
  vlmCloudModel: string;
  vlmOnline: boolean;
  vlmDevice: ExecutionDevice;

  allowedTopics: string[];
  robotLanguage: string;
  ttsVoiceGender: "male" | "female";
  ttsProvider: "gemini" | "edge" | "pyttsx3" | "gtts" | "coqui" | "chatterbox";
  chatterboxBaseUrl: string;
  chatterboxInstallDir: string;
  chatterboxVoiceMode: ChatterboxVoiceMode;
  chatterboxReferenceAudio: string;
  ttsCacheDir: string;
  gestureDetectionEnabled: boolean;
  gestureBindings: Record<string, string>;
  cameraResolution: string;
  cameraFps: number;

  sttLang: string;
  sttOnline: boolean;
  ttsLang: string;
  ttsOnline: boolean;
  ttsVoiceURI: string;
  ttsRate: number;

  themePreference: ThemePreference;

  llmCacheEnabled: boolean;
};

export type SettingsProfile = {
  id: string;
  name: string;
  createdAtMs: number;
  settings: BasicSettings;
};

export type SettingsState = BasicSettings & {
  profiles: SettingsProfile[];
  activeProfileId: string;
  saveProfile: (name: string) => void;
  deleteProfile: (id: string) => void;
  applyProfile: (id: string) => void;
  importProfiles: (profiles: SettingsProfile[]) => void;

  set: (patch: Partial<SettingsState>) => void;
};

export type SettingsSnapshot = BasicSettings & {
  profiles: SettingsProfile[];
  activeProfileId: string;
};

export function pickSettingsSnapshot(source: Pick<SettingsState, keyof SettingsSnapshot>): SettingsSnapshot {
  return {
    provider: source.provider,
    ollamaBaseUrl: source.ollamaBaseUrl,
    ollamaModel: source.ollamaModel,
    llmDevice: source.llmDevice,
    vlmBaseUrl: source.vlmBaseUrl,
    vlmModel: source.vlmModel,
    vlmCloudUrl: source.vlmCloudUrl,
    vlmCloudModel: source.vlmCloudModel,
    vlmOnline: source.vlmOnline,
    vlmDevice: source.vlmDevice,
    allowedTopics: [...source.allowedTopics],
    robotLanguage: source.robotLanguage,
    ttsVoiceGender: source.ttsVoiceGender,
    ttsProvider: source.ttsProvider,
    chatterboxBaseUrl: source.chatterboxBaseUrl,
    chatterboxInstallDir: source.chatterboxInstallDir,
    chatterboxVoiceMode: source.chatterboxVoiceMode,
    chatterboxReferenceAudio: source.chatterboxReferenceAudio,
    ttsCacheDir: source.ttsCacheDir,
    gestureDetectionEnabled: source.gestureDetectionEnabled,
    gestureBindings: { ...source.gestureBindings },
    cameraResolution: source.cameraResolution,
    cameraFps: source.cameraFps,
    sttLang: source.sttLang,
    sttOnline: source.sttOnline,
    ttsLang: source.ttsLang,
    ttsOnline: source.ttsOnline,
    ttsVoiceURI: source.ttsVoiceURI,
    ttsRate: source.ttsRate,
    themePreference: source.themePreference,
    llmCacheEnabled: source.llmCacheEnabled,
    profiles: source.profiles.map((profile) => ({
      ...profile,
      settings: {
        ...profile.settings,
        allowedTopics: [...profile.settings.allowedTopics],
        gestureBindings: { ...profile.settings.gestureBindings },
      },
    })),
    activeProfileId: source.activeProfileId,
  };
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      provider: "ollama",
      ollamaBaseUrl: "http://127.0.0.1:11434",
      ollamaModel: "gemma3:4b",
      llmDevice: "cpu",
      vlmBaseUrl: "http://127.0.0.1:11434",
      vlmModel: "moondream:latest",
      vlmCloudUrl: "",
      vlmCloudModel: "",
      vlmOnline: false,
      vlmDevice: "gpu",
      allowedTopics: [],
      robotLanguage: "ar-EG",
      ttsVoiceGender: "female",
      ttsProvider: "gemini",
      chatterboxBaseUrl: "http://127.0.0.1:8004",
      chatterboxInstallDir: "",
      chatterboxVoiceMode: "predefined",
      chatterboxReferenceAudio: "",
      ttsCacheDir: "./data/tts_cache",
      gestureDetectionEnabled: true,
      gestureBindings: {},
      cameraResolution: "640x480",
      cameraFps: 15,
      sttLang: "ar-EG",
      sttOnline: true,
      ttsLang: "ar-EG",
      ttsOnline: true,
      ttsVoiceURI: "",
      ttsRate: 1,
      themePreference: "auto",
      llmCacheEnabled: true,
      profiles: [],
      activeProfileId: "",
      saveProfile: (name) =>
        set((s) => {
          const trimmed = String(name || "").trim();
          if (!trimmed) return s;
          const id = `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
          const nextProfile: SettingsProfile = {
            id,
            name: trimmed,
            createdAtMs: Date.now(),
            settings: {
              provider: s.provider,
              ollamaBaseUrl: s.ollamaBaseUrl,
              ollamaModel: s.ollamaModel,
              llmDevice: s.llmDevice,
              vlmBaseUrl: s.vlmBaseUrl,
              vlmModel: s.vlmModel,
              vlmCloudUrl: s.vlmCloudUrl,
              vlmCloudModel: s.vlmCloudModel,
              vlmOnline: s.vlmOnline,
              vlmDevice: s.vlmDevice,
              allowedTopics: s.allowedTopics,
              robotLanguage: s.robotLanguage,
              ttsVoiceGender: s.ttsVoiceGender,
              ttsProvider: s.ttsProvider,
              chatterboxBaseUrl: s.chatterboxBaseUrl,
              chatterboxInstallDir: s.chatterboxInstallDir,
              chatterboxVoiceMode: s.chatterboxVoiceMode,
              chatterboxReferenceAudio: s.chatterboxReferenceAudio,
              ttsCacheDir: s.ttsCacheDir,
              gestureDetectionEnabled: s.gestureDetectionEnabled,
              gestureBindings: s.gestureBindings,
              cameraResolution: s.cameraResolution,
              cameraFps: s.cameraFps,
              sttLang: s.sttLang,
              ttsLang: s.ttsLang,
              ttsVoiceURI: s.ttsVoiceURI,
              ttsRate: s.ttsRate,
              themePreference: s.themePreference,
              llmCacheEnabled: s.llmCacheEnabled,
            } as SettingsProfile["settings"],
          };
          return { profiles: [nextProfile, ...s.profiles].slice(0, 20), activeProfileId: id };
        }),
      deleteProfile: (id) =>
        set((s) => ({
          profiles: s.profiles.filter((p) => p.id !== id),
          activeProfileId: s.activeProfileId === id ? "" : s.activeProfileId,
        })),
      applyProfile: (id) =>
        set((s) => {
          if (!id) {
            return { activeProfileId: "" };
          }
          const p = s.profiles.find((x) => x.id === id);
          if (!p) return s;
          return { ...p.settings, activeProfileId: id };
        }),
      importProfiles: (profiles) =>
        set((s) => {
          const incoming = Array.isArray(profiles) ? profiles : [];
          const safe = incoming
            .filter((p) => p && typeof p === "object" && typeof (p as SettingsProfile).id === "string" && typeof (p as SettingsProfile).name === "string")
            .slice(0, 20) as SettingsProfile[];
          const merged = [...safe, ...s.profiles].slice(0, 20);
          return { profiles: merged };
        }),
      set: (patch) => set(patch),
    }),
    {
      name: "local-robot-tester:settings",
      version: 12,
      migrate: (persistedState, version) => {
        const s = (persistedState || {}) as Record<string, unknown>;
        if (version >= 12) return s as unknown as SettingsState;
        const raw = (persistedState || {}) as Record<string, unknown>;
        const allowedTopics = Array.isArray(raw.allowedTopics)
          ? raw.allowedTopics.map((x) => String(x || "").trim()).filter(Boolean)
          : [];
        const robotLanguage = typeof raw.robotLanguage === "string" && raw.robotLanguage.trim() ? raw.robotLanguage.trim() : "";
        const ttsVoiceGender =
          typeof raw.ttsVoiceGender === "string" && raw.ttsVoiceGender.trim().toLowerCase() === "male" ? "male" : "female";
        const themePreference: ThemePreference = "auto";
        const llmDevice: ExecutionDevice = typeof raw.llmDevice === "string" && raw.llmDevice.trim().toLowerCase() === "gpu" ? "gpu" : "cpu";
        const vlmDevice: ExecutionDevice = typeof raw.vlmDevice === "string" && raw.vlmDevice.trim().toLowerCase() === "cpu" ? "cpu" : "gpu";
        const llmCacheEnabled = typeof raw.llmCacheEnabled === "boolean" ? raw.llmCacheEnabled : true;
        const ttsProviderRaw = typeof raw.ttsProvider === "string" ? raw.ttsProvider.trim().toLowerCase() : "";
        const ttsProvider =
          ttsProviderRaw === "gemini" ||
          ttsProviderRaw === "pyttsx3" ||
          ttsProviderRaw === "gtts" ||
          ttsProviderRaw === "coqui" ||
          ttsProviderRaw === "chatterbox"
            ? ((robotLanguage || (typeof raw.ttsLang === "string" ? raw.ttsLang : "") || "ar-EG").toLowerCase().startsWith("ar")
                ? (ttsProviderRaw === "chatterbox" ? "chatterbox" : "gemini")
                : (ttsProviderRaw as "gemini" | "pyttsx3" | "gtts" | "coqui" | "chatterbox"))
            : "gemini";
        const chatterboxBaseUrl =
          typeof raw.chatterboxBaseUrl === "string" && raw.chatterboxBaseUrl.trim() ? raw.chatterboxBaseUrl : "http://127.0.0.1:8004";
        const chatterboxInstallDir = typeof raw.chatterboxInstallDir === "string" ? raw.chatterboxInstallDir : "";
        const chatterboxVoiceMode: ChatterboxVoiceMode =
          typeof raw.chatterboxVoiceMode === "string" && raw.chatterboxVoiceMode.trim().toLowerCase() === "clone"
            ? "clone"
            : "predefined";
        const chatterboxReferenceAudio = typeof raw.chatterboxReferenceAudio === "string" ? raw.chatterboxReferenceAudio : "";
        const ttsCacheDir = typeof raw.ttsCacheDir === "string" ? raw.ttsCacheDir : "./data/tts_cache";
        const gestureDetectionEnabled = typeof raw.gestureDetectionEnabled === "boolean" ? raw.gestureDetectionEnabled : true;
        const gestureBindingsRaw = raw.gestureBindings;
        const gestureBindings: Record<string, string> = {};
        if (gestureBindingsRaw && typeof gestureBindingsRaw === "object" && !Array.isArray(gestureBindingsRaw)) {
          for (const [k, v] of Object.entries(gestureBindingsRaw as Record<string, unknown>)) {
            const key = String(k || "").trim().toLowerCase();
            const val = typeof v === "string" ? v.trim() : "";
            if (key && val) gestureBindings[key] = val;
          }
        }
        const cameraResolution = typeof raw.cameraResolution === "string" ? raw.cameraResolution : "640x480";
        const cameraFps = typeof raw.cameraFps === "number" && Number.isFinite(raw.cameraFps) ? raw.cameraFps : 15;
        const vlmCloudUrl = typeof raw.vlmCloudUrl === "string" ? raw.vlmCloudUrl : "";
        const vlmCloudModel = typeof raw.vlmCloudModel === "string" ? raw.vlmCloudModel : "";
        const vlmOnline = typeof raw.vlmOnline === "boolean" ? raw.vlmOnline : false;
        const sttOnline = typeof raw.sttOnline === "boolean" ? raw.sttOnline : false;
        const ttsOnline = typeof raw.ttsOnline === "boolean" ? raw.ttsOnline : true;

        return {
          provider: (typeof raw.provider === "string" ? (raw.provider as Provider) : "ollama") || "ollama",
          ollamaBaseUrl: typeof raw.ollamaBaseUrl === "string" ? raw.ollamaBaseUrl : "http://127.0.0.1:11434",
          ollamaModel: typeof raw.ollamaModel === "string" && raw.ollamaModel.trim() ? raw.ollamaModel : "gemma3:4b",
          llmDevice,
          vlmBaseUrl: typeof raw.vlmBaseUrl === "string" ? raw.vlmBaseUrl : "http://127.0.0.1:11434",
          vlmModel: typeof raw.vlmModel === "string" && raw.vlmModel.trim() ? raw.vlmModel : "moondream:latest",
          vlmCloudUrl,
          vlmCloudModel,
          vlmOnline,
          vlmDevice,
          allowedTopics,
          robotLanguage: robotLanguage || (typeof raw.ttsLang === "string" ? raw.ttsLang : "") || "ar-EG",
          ttsVoiceGender,
          ttsProvider,
          chatterboxBaseUrl,
          chatterboxInstallDir,
          chatterboxVoiceMode,
          chatterboxReferenceAudio,
          ttsCacheDir,
          gestureDetectionEnabled,
          gestureBindings,
          cameraResolution,
          cameraFps,
          sttLang: typeof raw.sttLang === "string" ? raw.sttLang : "ar-EG",
          sttOnline,
          ttsLang: typeof raw.ttsLang === "string" ? raw.ttsLang : "ar-EG",
          ttsOnline,
          ttsVoiceURI: typeof raw.ttsVoiceURI === "string" ? raw.ttsVoiceURI : "",
          ttsRate: typeof raw.ttsRate === "number" ? raw.ttsRate : 1,
          themePreference,
          llmCacheEnabled,
          profiles: [],
          activeProfileId: "",
        } as unknown as SettingsState;
      },
    },
  ),
);
