import { useEffect, useRef, useState } from "react";
import { AppShell } from "../components/AppShell";
import {
  Camera,
  Cpu,
  LogOut,
  MonitorSpeaker,
  Paintbrush,
  Save,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { getJson, getRobotAuthHeaders, logoutRobotSession, postJson, putJson } from "../utils/api";
import { useHostRuntime } from "../hooks/useHostRuntime";
import { pickSettingsSnapshot, useSettingsStore, type SettingsState } from "../stores/settingsStore";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { useNotificationStore, type NotificationState } from "../stores/notificationStore";
import { useRobotSettings } from "../hooks/useRobotSettings";

function topicsToText(topics: string[]): string {
  return topics.join(", ");
}

function parseTopicsText(raw: string): string[] {
  const items = raw
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 50);
  return Array.from(new Set(items));
}

function gestureBindingsToText(bindings: Record<string, string>): string {
  return JSON.stringify(bindings, null, 2);
}

function parseGestureBindingsText(raw: string): { ok: true; value: Record<string, string> } | { ok: false; error: string } {
  const text = raw.trim();
  if (!text) {
    return { ok: true, value: {} };
  }

  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, error: "Gesture bindings must be a JSON object." };
    }

    const clean: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      const cleanKey = String(key || "").trim().toLowerCase();
      const cleanValue = typeof value === "string" ? value.trim() : "";
      if (!cleanKey || !cleanValue) continue;
      clean[cleanKey] = cleanValue;
    }

    return { ok: true, value: clean };
  } catch {
    return { ok: false, error: "Gesture bindings JSON is invalid." };
  }
}

function statusText(args: {
  loading: boolean;
  saving: boolean;
  saveError: string | null;
  gestureBindingsError: string | null;
  hasPendingChanges: boolean;
  savedAtMs: number;
  status: string;
}): string {
  if (args.loading) return "Loading host settings";
  if (args.saving) return "Saving configuration to host";
  if (args.saveError) return args.saveError;
  if (args.gestureBindingsError) return args.gestureBindingsError;
  if (args.hasPendingChanges) return "Unsaved changes pending";
  if (args.savedAtMs > 0) return `Saved to host at ${new Date(args.savedAtMs).toLocaleTimeString()}`;
  if (args.status === "success") return "Host configuration loaded";
  return "Editing host configuration";
}

type EdgeVoiceDto = {
  ShortName: string;
  Gender?: string;
  Locale?: string;
  FriendlyName?: string;
  Provider?: string;
};

type TtsVoicesResponse = {
  success: boolean;
  voices?: EdgeVoiceDto[];
  error?: string;
};

type TtsSpeakResponse = {
  success: boolean;
  audio?: string;
  format?: string;
  voice?: string;
  normalizedText?: string;
  error?: string;
  voiceMode?: string;
};

type ChatterboxReferenceFilesResponse = {
  success: boolean;
  files?: string[];
  error?: string;
};

type ChatterboxReferenceUploadResponse = {
  success?: boolean;
  message?: string;
  uploaded_files?: string[];
  all_reference_files?: string[];
  errors?: Array<{ filename?: string; error?: string }>;
  error?: string;
};

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return Array.from(
    new Set(
      value
        .map((item) => (typeof item === "string" ? item.trim() : ""))
        .filter(Boolean),
    ),
  );
}

function firstReferenceUploadError(payload: ChatterboxReferenceUploadResponse | null): string | null {
  if (!payload) return null;
  const errors = Array.isArray(payload.errors) ? payload.errors : [];
  for (const entry of errors) {
    const message = typeof entry?.error === "string" ? entry.error.trim() : "";
    const filename = typeof entry?.filename === "string" ? entry.filename.trim() : "";
    if (message && filename) return `${filename}: ${message}`;
    if (message) return message;
  }
  if (typeof payload.error === "string" && payload.error.trim()) return payload.error.trim();
  return null;
}

function clampTtsRate(value: number): number {
  const numeric = Number.isFinite(value) ? value : 1;
  return Math.min(1.5, Math.max(0.6, Number(numeric.toFixed(2))));
}

function previewSpeechText(language: string): string {
  const lang = String(language || "").trim().toLowerCase();
  if (lang.startsWith("ar")) {
    return "إزيك يا باشا، أنا جاهز أساعدك دلوقتي.";
  }
  return "Hello, I am ready to help you right now.";
}

function SettingsSkeletonLine(props: { className?: string }) {
  return <div className={`animate-pulse rounded-full bg-white/6 ${props.className || ""}`.trim()} />;
}

function SettingsSkeletonCard(props: { fields?: number; wide?: boolean }) {
  const fields = Math.max(1, props.fields ?? 3);
  return (
    <div className={`ts-surface-card animate-pulse rounded-[1.5rem] p-4 sm:p-5 ${props.wide ? "md:col-span-2" : ""}`.trim()}>
      <SettingsSkeletonLine className="h-3 w-28" />
      <div className="mt-4 space-y-3">
        {Array.from({ length: fields }).map((_, index) => (
          <div key={index} className="space-y-2">
            <SettingsSkeletonLine className="h-2.5 w-20 bg-white/5" />
            <SettingsSkeletonLine className="h-11 w-full rounded-[1rem] bg-white/5" />
          </div>
        ))}
      </div>
    </div>
  );
}

function SettingsSectionSkeleton(props: { titleWidth: string; cards: Array<{ fields?: number; wide?: boolean }> }) {
  return (
    <section>
      <div className="mb-5 flex items-center gap-3 sm:mb-8 sm:gap-4">
        <div className="h-4 w-4 animate-pulse rounded-full bg-white/8 sm:h-5 sm:w-5" />
        <SettingsSkeletonLine className={`h-5 ${props.titleWidth}`} />
      </div>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 md:gap-8">
        {props.cards.map((card, index) => (
          <SettingsSkeletonCard key={`${props.titleWidth}-${index}`} fields={card.fields} wide={card.wide} />
        ))}
      </div>
    </section>
  );
}

function SettingsInitialSkeleton() {
  return (
    <div className="mx-auto max-w-4xl animate-[ts-fade-in_0.35s_ease-out] pt-0 pb-28 sm:pt-4 sm:pb-16">
      <div className="ts-surface-panel mb-8 animate-pulse rounded-[1.5rem] p-4 sm:mb-16 sm:rounded-[1.75rem] sm:p-6">
        <SettingsSkeletonLine className="h-4 w-40" />
        <SettingsSkeletonLine className="mt-3 h-3 w-64 bg-white/5" />
        <SettingsSkeletonLine className="mt-6 h-11 w-full rounded-[999px] bg-white/5 sm:w-48" />
      </div>

      <div className="space-y-8 sm:space-y-24">
        <SettingsSectionSkeleton
          titleWidth="w-56"
          cards={[
            { fields: 2 },
            { fields: 2 },
            { fields: 2 },
            { fields: 2 },
          ]}
        />
        <SettingsSectionSkeleton
          titleWidth="w-52"
          cards={[
            { fields: 3 },
            { fields: 3 },
            { fields: 2, wide: true },
          ]}
        />
        <SettingsSectionSkeleton
          titleWidth="w-44"
          cards={[
            { fields: 2 },
            { fields: 3 },
          ]}
        />
        <SettingsSectionSkeleton
          titleWidth="w-40"
          cards={[
            { fields: 1 },
            { fields: 1 },
          ]}
        />
        <SettingsSectionSkeleton
          titleWidth="w-44"
          cards={[
            { fields: 2 },
            { fields: 3 },
          ]}
        />
      </div>
    </div>
  );
}

export function SettingsContent() {
  const pushNotif = useNotificationStore((s: NotificationState) => s.push);
  const s = useSettingsStore();
  const { load, loading, loadedAtMs, status } = useRobotSettings({ autoLoad: true });
  const { health, refresh: refreshHostRuntime } = useHostRuntime();

  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [vlmModels, setVlmModels] = useState<string[]>([]);
  const [ollamaLoading, setOllamaLoading] = useState(false);
  const [profileName, setProfileName] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedAtMs, setSavedAtMs] = useState(0);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [allowedTopicsText, setAllowedTopicsText] = useState(topicsToText(s.allowedTopics));
  const [gestureBindingsDraft, setGestureBindingsDraft] = useState(gestureBindingsToText(s.gestureBindings));
  const [gestureBindingsError, setGestureBindingsError] = useState<string | null>(null);
  const [ttsVoices, setTtsVoices] = useState<EdgeVoiceDto[]>([]);
  const [ttsVoicesLoading, setTtsVoicesLoading] = useState(false);
  const [ttsVoicesError, setTtsVoicesError] = useState<string | null>(null);
  const [referenceFiles, setReferenceFiles] = useState<string[]>([]);
  const [referenceFilesLoading, setReferenceFilesLoading] = useState(false);
  const [referenceFilesError, setReferenceFilesError] = useState<string | null>(null);
  const [uploadingReferenceAudio, setUploadingReferenceAudio] = useState(false);
  const [previewingVoice, setPreviewingVoice] = useState(false);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const referenceAudioInputRef = useRef<HTMLInputElement | null>(null);
  const lastSavedSnapshotRef = useRef("");
  const labelClass =
    "text-[11px] font-semibold tracking-[0.16em] uppercase text-[var(--ts-muted)] sm:text-xs sm:tracking-[0.22em]";
  const helperClass = "text-[11px] leading-5 text-[var(--ts-muted)] sm:text-xs";
  const probeButtonClass =
    "ts-btn ts-btn-ghost w-full border-[color:var(--ts-border-strong)] bg-[color:var(--ts-surface-bg)] px-5 py-2.5 text-[11px] uppercase tracking-[0.18em] whitespace-nowrap text-[var(--ts-text)] hover:bg-[color:var(--ts-surface-bg-strong)] sm:w-auto sm:px-6 sm:text-xs sm:tracking-widest";

  const currentSnapshotKey = JSON.stringify(pickSettingsSnapshot(s));
  const hasPendingChanges = currentSnapshotKey !== lastSavedSnapshotRef.current || Boolean(gestureBindingsError);
  const mobileSaveLabel = saving ? "Saving..." : hasPendingChanges ? "Save" : "Saved";
  const hostLabel = health?.host?.mode ? String(health.host.mode).toUpperCase() : "HOST";
  const hostUrl = health?.host?.lanUrl || health?.host?.localUrl || "http://127.0.0.1:8000";
  const hostRuntimeLabel = health?.degraded ? "DEGRADED" : health?.ready ? "READY" : "BOOTING";
  const ttsLanguage = s.ttsLang || s.robotLanguage || "ar-EG";
  const isChatterboxProvider = s.ttsProvider === "chatterbox";
  const isChatterboxCloneMode = isChatterboxProvider && s.chatterboxVoiceMode === "clone";
  const requestedLocale = String(ttsLanguage || "ar-EG").trim().toLowerCase();
  const requestedLanguageFamily = requestedLocale.split("-")[0] || "ar";
  const exactLocaleVoices = ttsVoices.filter((voice) => String(voice.Locale || "").trim().toLowerCase() === requestedLocale);
  const familyLocaleVoices = ttsVoices.filter((voice) =>
    String(voice.Locale || "").trim().toLowerCase().startsWith(`${requestedLanguageFamily}-`),
  );
  const visibleTtsVoices =
    s.ttsProvider === "chatterbox"
      ? ttsVoices
      : exactLocaleVoices.length > 0
        ? exactLocaleVoices
        : familyLocaleVoices;

  useUnsavedChangesGuard(hasPendingChanges, "You have unsaved settings changes. Leave this page?");

  const updateSetting = (patch: Partial<SettingsState>) => {
    s.set(patch);
    setSaveError(null);
  };

  const syncToRobot = async () => {
    if (gestureBindingsError) {
      pushNotif({
        kind: "error",
        title: "Save Blocked",
        message: "Fix invalid gesture bindings JSON before saving.",
        ttlMs: 3500,
      });
      return false;
    }

    const parsedGestureBindings = parseGestureBindingsText(gestureBindingsDraft);
    if (!parsedGestureBindings.ok) {
      setGestureBindingsError(parsedGestureBindings.error);
      pushNotif({
        kind: "error",
        title: "Save Blocked",
        message: parsedGestureBindings.error,
        ttlMs: 3500,
      });
      return false;
    }

    setSaveError(null);
    setSaving(true);
    try {
      const current = useSettingsStore.getState();
      await putJson("/api/robot-settings", {
        settings: pickSettingsSnapshot(current),
      });
      lastSavedSnapshotRef.current = JSON.stringify(pickSettingsSnapshot(useSettingsStore.getState()));
      setSavedAtMs(Date.now());
      pushNotif({
        kind: "success",
        title: "Settings Saved",
        message: "All settings were stored on the host.",
        ttlMs: 2500,
      });
      return true;
    } catch (error) {
      const message = String(error);
      setSaveError(message);
      pushNotif({
        kind: "error",
        title: "Save Failed",
        message,
        ttlMs: 4500,
      });
      return false;
    } finally {
      setSaving(false);
    }
  };

  const loadModels = async (type: "ollama" | "vlm") => {
    setOllamaLoading(true);
    try {
      const baseUrl = type === "ollama" ? s.ollamaBaseUrl : s.vlmBaseUrl;
      const endpoint = type === "ollama" ? "/api/llm/ollama-models" : "/api/vision/vlm-models";
      const data = await getJson<{ success: boolean; models: string[] }>(
        `${endpoint}?baseUrl=${encodeURIComponent(baseUrl)}`,
      );
      if (data.success) {
        if (type === "ollama") setOllamaModels(data.models);
        else setVlmModels(data.models);
        pushNotif({
          kind: "success",
          title: "Node Probe",
          message: `Found ${data.models.length} models`,
          ttlMs: 3000,
        });
      }
    } catch (error) {
      pushNotif({ kind: "error", title: "Probe Failed", message: String(error), ttlMs: 5000 });
    } finally {
      setOllamaLoading(false);
    }
  };

  const loadTtsVoices = async (args?: { silent?: boolean }) => {
    if (ttsVoicesLoading) return;
    setTtsVoicesLoading(true);
    setTtsVoicesError(null);
    try {
      const query = new URLSearchParams({
        provider: s.ttsProvider,
      });
      if (s.ttsProvider === "chatterbox" && s.chatterboxBaseUrl.trim()) {
        query.set("baseUrl", s.chatterboxBaseUrl.trim());
      }
      const response = await getJson<TtsVoicesResponse>(`/api/tts/voices?${query.toString()}`);
      if (!response.success || !Array.isArray(response.voices)) {
        const message = response.error || "Could not load voice list.";
        setTtsVoicesError(message);
        if (!args?.silent) {
          pushNotif({ kind: "error", title: "Voices", message, ttlMs: 3500 });
        }
        return;
      }

      const sortedVoices = [...response.voices].sort((a, b) => a.ShortName.localeCompare(b.ShortName));
      setTtsVoices(sortedVoices);
      if (!args?.silent) {
        pushNotif({
          kind: "success",
          title: "Voices Loaded",
          message: `Found ${sortedVoices.length} available voices.`,
          ttlMs: 2500,
        });
      }
    } catch (error) {
      const message = String(error);
      setTtsVoicesError(message);
      if (!args?.silent) {
        pushNotif({ kind: "error", title: "Voices", message, ttlMs: 3500 });
      }
    } finally {
      setTtsVoicesLoading(false);
    }
  };

  const loadChatterboxReferenceFiles = async (args?: { silent?: boolean }) => {
    if (referenceFilesLoading) return;
    setReferenceFilesLoading(true);
    setReferenceFilesError(null);
    try {
      const query = new URLSearchParams();
      if (s.chatterboxBaseUrl.trim()) {
        query.set("baseUrl", s.chatterboxBaseUrl.trim());
      }
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const response = await getJson<ChatterboxReferenceFilesResponse>(`/api/tts/chatterbox/reference-files${suffix}`);
      if (!response.success) {
        const message = response.error || "Could not load reference audio files.";
        setReferenceFilesError(message);
        if (!args?.silent) {
          pushNotif({ kind: "error", title: "Reference Files", message, ttlMs: 3500 });
        }
        return;
      }

      const files = normalizeStringList(response.files).sort((a, b) => a.localeCompare(b));
      setReferenceFiles(files);
      if (!args?.silent) {
        pushNotif({
          kind: "success",
          title: "Reference Files",
          message: files.length > 0 ? `Found ${files.length} uploaded reference files.` : "No reference audio uploaded yet.",
          ttlMs: 2600,
        });
      }
    } catch (error) {
      const message = String(error);
      setReferenceFilesError(message);
      if (!args?.silent) {
        pushNotif({ kind: "error", title: "Reference Files", message, ttlMs: 3500 });
      }
    } finally {
      setReferenceFilesLoading(false);
    }
  };

  const uploadReferenceAudio = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    setUploadingReferenceAudio(true);
    setReferenceFilesError(null);
    try {
      const formData = new FormData();
      formData.append("files", file);

      const query = new URLSearchParams();
      if (s.chatterboxBaseUrl.trim()) {
        query.set("baseUrl", s.chatterboxBaseUrl.trim());
      }
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const response = await fetch(`/api/tts/chatterbox/reference-files${suffix}`, {
        method: "POST",
        body: formData,
        headers: getRobotAuthHeaders(),
        credentials: "include",
      });

      const payload = (await response.json().catch(() => null)) as ChatterboxReferenceUploadResponse | null;
      const uploadedFiles = normalizeStringList(payload?.uploaded_files);
      const allReferenceFiles = normalizeStringList(payload?.all_reference_files);

      if (!response.ok || payload?.success === false) {
        throw new Error(firstReferenceUploadError(payload) || `Reference upload failed (${response.status})`);
      }

      if (allReferenceFiles.length > 0) {
        setReferenceFiles(allReferenceFiles.sort((a, b) => a.localeCompare(b)));
      } else {
        await loadChatterboxReferenceFiles({ silent: true });
      }

      if (uploadedFiles.length > 0) {
        updateSetting({
          chatterboxVoiceMode: "clone",
          chatterboxReferenceAudio: uploadedFiles[0],
        });
      }

      pushNotif({
        kind: "success",
        title: "Reference Uploaded",
        message: uploadedFiles.length > 0 ? `${uploadedFiles[0]} is ready for Chatterbox clone mode.` : "Reference audio uploaded successfully.",
        ttlMs: 3200,
      });
    } catch (error) {
      const message = String(error);
      setReferenceFilesError(message);
      pushNotif({
        kind: "error",
        title: "Upload Failed",
        message,
        ttlMs: 4200,
      });
    } finally {
      setUploadingReferenceAudio(false);
      if (referenceAudioInputRef.current) {
        referenceAudioInputRef.current.value = "";
      }
    }
  };

  const previewCurrentVoice = async () => {
    if (previewingVoice) return;
    setPreviewingVoice(true);
    try {
      previewAudioRef.current?.pause();
      previewAudioRef.current = null;

      const response = await postJson<TtsSpeakResponse>("/api/tts/speak", {
        text: previewSpeechText(ttsLanguage),
        lang: ttsLanguage,
        voice: s.ttsVoiceURI || undefined,
        provider: s.ttsProvider,
        baseUrl: s.ttsProvider === "chatterbox" ? s.chatterboxBaseUrl : undefined,
        voiceGender: s.ttsVoiceGender,
        rate: s.ttsRate,
        chatterboxVoiceMode: s.ttsProvider === "chatterbox" ? s.chatterboxVoiceMode : undefined,
        referenceAudio: s.ttsProvider === "chatterbox" ? s.chatterboxReferenceAudio || undefined : undefined,
      });

      if (!response.success || !response.audio) {
        throw new Error(response.error || "Voice preview failed.");
      }

      const format = response.format || "mp3";
      const audio = new Audio(`data:audio/${format};base64,${response.audio}`);
      previewAudioRef.current = audio;
      audio.onended = () => {
        if (previewAudioRef.current === audio) {
          previewAudioRef.current = null;
        }
        setPreviewingVoice(false);
      };
      audio.onerror = () => {
        if (previewAudioRef.current === audio) {
          previewAudioRef.current = null;
        }
        setPreviewingVoice(false);
        pushNotif({
          kind: "error",
          title: "Preview Failed",
          message: "Browser audio playback failed for the generated preview.",
          ttlMs: 3500,
        });
      };

      const playPromise = audio.play();
      if (playPromise) {
        await playPromise;
      }

      pushNotif({
        kind: "info",
        title: "Voice Preview",
        message: response.voice ? `Playing ${response.voice}` : "Playing current voice settings.",
        ttlMs: 2200,
      });
    } catch (error) {
      setPreviewingVoice(false);
      pushNotif({
        kind: "error",
        title: "Preview Failed",
        message: String(error),
        ttlMs: 4200,
      });
    }
  };

  const handleSaveProfile = () => {
    if (!profileName.trim()) return;
    s.saveProfile(profileName.trim());
    setProfileName("");
    setSaveError(null);
    pushNotif({ kind: "success", title: "Profile", message: "Profile prepared for save.", ttlMs: 2000 });
  };

  const handleDeleteProfile = (profileId: string) => {
    s.deleteProfile(profileId);
    setSaveError(null);
    pushNotif({ kind: "warning", title: "Profile Removed", message: "Save settings to persist deletion.", ttlMs: 2500 });
  };

  const applyProfile = (profileId: string) => {
    s.applyProfile(profileId);
    setAllowedTopicsText(topicsToText(useSettingsStore.getState().allowedTopics));
    setGestureBindingsDraft(gestureBindingsToText(useSettingsStore.getState().gestureBindings));
    setGestureBindingsError(null);
    setSaveError(null);
  };

  const handleResetSession = async () => {
    await logoutRobotSession();
    pushNotif({
      kind: "info",
      title: "Session Reset",
      message: "Current device authorization was cleared.",
      ttlMs: 2600,
    });
  };

  useEffect(() => {
    setAllowedTopicsText(topicsToText(s.allowedTopics));
  }, [s.allowedTopics]);

  useEffect(() => {
    if (status !== "success") return;
    lastSavedSnapshotRef.current = JSON.stringify(pickSettingsSnapshot(useSettingsStore.getState()));
    setAllowedTopicsText(topicsToText(useSettingsStore.getState().allowedTopics));
    setGestureBindingsDraft(gestureBindingsToText(useSettingsStore.getState().gestureBindings));
    setGestureBindingsError(null);
    setSaveError(null);
    setSavedAtMs(loadedAtMs || 0);
  }, [loadedAtMs, status]);

  useEffect(() => {
    if (s.ttsProvider !== "edge" && s.ttsProvider !== "chatterbox") return;
    if (ttsVoices.length > 0) return;
    void loadTtsVoices({ silent: true });
  }, [s.chatterboxBaseUrl, s.ttsProvider, ttsVoices.length]);

  useEffect(() => {
    if (!isChatterboxCloneMode) return;
    if (referenceFiles.length > 0) return;
    void loadChatterboxReferenceFiles({ silent: true });
  }, [isChatterboxCloneMode, referenceFiles.length, s.chatterboxBaseUrl]);

  useEffect(() => {
    return () => {
      previewAudioRef.current?.pause();
      previewAudioRef.current = null;
    };
  }, []);

  if (loading && loadedAtMs === 0 && status !== "success") {
    return <SettingsInitialSkeleton />;
  }

  const SectionTitle = ({ icon: Icon, title }: { icon: LucideIcon; title: string }) => (
    <div className="mb-5 flex items-center gap-3 sm:mb-8 sm:gap-4">
      <Icon className="h-4 w-4 text-[var(--ts-muted)] sm:h-5 sm:w-5" strokeWidth={1.5} />
      <h2 className="text-base font-semibold uppercase leading-tight tracking-[0.12em] text-[var(--ts-text)] sm:text-xl sm:tracking-[0.2em]">
        {title}
      </h2>
    </div>
  );

  return (
    <div className="mx-auto max-w-4xl animate-[ts-fade-in_0.5s_ease-out] pt-0 pb-28 sm:pt-4 sm:pb-16">
      <div className="ts-surface-panel sticky top-[calc(env(safe-area-inset-top)+0.75rem)] z-20 mb-8 flex flex-col gap-4 rounded-[1.5rem] p-4 sm:mb-16 sm:flex-row sm:items-center sm:justify-between sm:rounded-[1.75rem] sm:p-6">
        <div>
          <div className="mb-1 text-sm font-semibold tracking-[0.3em] uppercase text-[var(--ts-text)]">
            Configuration State
          </div>
          <div className="text-xs tracking-widest uppercase text-[var(--ts-muted)]">
            {statusText({ loading, saving, saveError, gestureBindingsError, hasPendingChanges, savedAtMs, status })}
          </div>
          <div className="mt-2 text-[11px] uppercase tracking-[0.16em] text-[var(--ts-muted)] sm:text-xs sm:tracking-[0.2em]">
            {hostLabel} · {hostRuntimeLabel} · {hostUrl}
          </div>
        </div>
        <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
          <button
            onClick={() => {
              void (async () => {
                await refreshHostRuntime(true);
              })();
            }}
            disabled={loading || saving}
            className="ts-btn ts-btn-ghost w-full rounded-full px-6 py-3 text-xs uppercase tracking-[0.2em] sm:w-auto"
          >
            Refresh Host State
          </button>
          <button
            onClick={() => {
              void (async () => {
                const result = await load({ force: true });
                if (result.ok) {
                  pushNotif({
                    kind: "info",
                    title: "Reloaded",
                    message: "Settings were refreshed from the host.",
                    ttlMs: 2500,
                  });
                  return;
                }
                pushNotif({
                  kind: "error",
                  title: "Reload Failed",
                  message: result.error || "Could not refresh host settings.",
                  ttlMs: 3500,
                });
              })();
            }}
            disabled={loading || saving}
            className="ts-btn ts-btn-ghost w-full rounded-full px-6 py-3 text-xs uppercase tracking-[0.2em] sm:w-auto"
          >
            Reload Host Copy
          </button>
          <button
            onClick={() => {
              void handleResetSession();
            }}
            className="ts-btn ts-btn-ghost w-full rounded-full px-6 py-3 text-xs uppercase tracking-[0.2em] sm:w-auto"
          >
            <span className="inline-flex items-center gap-2">
              <LogOut className="h-4 w-4" strokeWidth={1.8} />
              Reset Session
            </span>
          </button>
          <button
            onClick={() => {
              void syncToRobot();
            }}
            disabled={loading || saving || !hasPendingChanges}
            className="ts-btn ts-btn-primary w-full rounded-full px-6 py-3 text-xs uppercase tracking-[0.2em] sm:w-auto"
          >
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      </div>

      <div className="space-y-8 sm:space-y-24">
        <section>
          <SectionTitle icon={Cpu} title="Intelligence Modules (LLM & VLM)" />
          <div className="space-y-8 sm:space-y-12">
            <div className="space-y-4">
              <div className="flex flex-col gap-2">
                <label className={labelClass}>LLM Provider</label>
                <select
                  title="LLM Provider"
                  value={s.provider || "ollama"}
                  onChange={(e) => updateSetting({ provider: e.target.value as any })}
                  className="ts-select focus:outline-none"
                >
                  <option value="ollama">Ollama (Local/Cloud)</option>
                  <option value="openrouter">OpenRouter (Key Rotation)</option>
                </select>
              </div>

              {(s.provider === "ollama" || !s.provider) && (
                <>
                  <div className="flex flex-col gap-2">
                    <label className={labelClass}>Ollama LLM Endpoint</label>
                    <div className="flex flex-col gap-3 sm:flex-row sm:gap-4">
                      <input
                        value={s.ollamaBaseUrl}
                        onChange={(e) => updateSetting({ ollamaBaseUrl: e.target.value })}
                        className="ts-input flex-1 focus:outline-none"
                        placeholder="http://127.0.0.1:11434"
                      />
                      <button
                        onClick={() => loadModels("ollama")}
                        disabled={ollamaLoading}
                        title="Probe Ollama Node"
                        className={probeButtonClass}
                      >
                        Probe
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <label className={labelClass}>Active LLM Model</label>
                    {ollamaModels.length > 0 ? (
                      <select
                        title="Ollama Model"
                        value={s.ollamaModel}
                        onChange={(e) => updateSetting({ ollamaModel: e.target.value })}
                        className="ts-select focus:outline-none"
                      >
                        {ollamaModels.map((model) => (
                          <option key={model} value={model}>
                            {model}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        title="Ollama Model"
                        placeholder="gemma3:4b"
                        value={s.ollamaModel}
                        onChange={(e) => updateSetting({ ollamaModel: e.target.value })}
                        className="ts-input focus:outline-none"
                      />
                    )}
                  </div>
                </>
              )}

              {s.provider === "openrouter" && (
                <div className="flex flex-col gap-2">
                  <label className={labelClass}>Active OpenRouter Model</label>
                  <input
                    title="OpenRouter Model"
                    placeholder="moonshotai/kimi-k2.6:free"
                    value={s.hfModel || ""}
                    onChange={(e) => updateSetting({ hfModel: e.target.value })}
                    className="ts-input focus:outline-none"
                  />
                  <div className={helperClass}>
                    Specify any model supported by OpenRouter (e.g. moonshotai/kimi-k2.6:free). Make sure to configure the keys on the API Keys page.
                  </div>
                </div>
              )}
              <div className="flex flex-col gap-2">
                <label className={labelClass}>LLM Compute Device</label>
                <select
                  title="LLM Compute Device"
                  value={s.llmDevice}
                  onChange={(e) => updateSetting({ llmDevice: e.target.value as SettingsState["llmDevice"] })}
                  className="ts-select focus:outline-none"
                >
                  <option value="cpu">CPU</option>
                  <option value="gpu">GPU</option>
                </select>
                <div className={helperClass}>Main language models should stay on CPU for the host workflow.</div>
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelClass}>Allowed Topics</label>
                <textarea
                  value={allowedTopicsText}
                  onChange={(e) => {
                    const value = e.target.value;
                    setAllowedTopicsText(value);
                    updateSetting({ allowedTopics: parseTopicsText(value) });
                  }}
                  rows={3}
                  className="ts-input min-h-[5.75rem] resize-y leading-6 focus:outline-none sm:min-h-[7rem]"
                  placeholder="vision, navigation, safety"
                />
                <div className={helperClass}>Separate topics with commas or new lines.</div>
              </div>
            </div>

            <div className="space-y-4 border-t border-[color:var(--ts-border)] pt-5 sm:pt-6">
              <div className="flex flex-col gap-2">
                <label className={labelClass}>Vision (VLM) Endpoint</label>
                <div className="flex flex-col gap-3 sm:flex-row sm:gap-4">
                  <input
                    value={s.vlmBaseUrl}
                    onChange={(e) => updateSetting({ vlmBaseUrl: e.target.value })}
                    className="ts-input flex-1 focus:outline-none"
                    placeholder="http://127.0.0.1:11434"
                  />
                  <button
                    onClick={() => loadModels("vlm")}
                    disabled={ollamaLoading}
                    title="Probe Vision Node"
                    className={probeButtonClass}
                  >
                    Probe
                  </button>
                </div>
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelClass}>Active Vision Model</label>
                {vlmModels.length > 0 ? (
                  <select
                    title="Vision Model"
                    value={s.vlmModel}
                    onChange={(e) => updateSetting({ vlmModel: e.target.value })}
                    className="ts-select focus:outline-none"
                  >
                    {vlmModels.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    title="Vision Model"
                    placeholder="moondream"
                    value={s.vlmModel}
                    onChange={(e) => updateSetting({ vlmModel: e.target.value })}
                    className="ts-input focus:outline-none"
                  />
                )}
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelClass}>Vision Compute Device</label>
                <select
                  title="Vision Compute Device"
                  value={s.vlmDevice}
                  onChange={(e) => updateSetting({ vlmDevice: e.target.value as SettingsState["vlmDevice"] })}
                  className="ts-select focus:outline-none"
                >
                  <option value="gpu">GPU</option>
                  <option value="cpu">CPU</option>
                </select>
                <div className={helperClass}>Vision inference should stay on GPU for faster scene analysis.</div>
              </div>

              <div className="ts-surface-card rounded-[1.5rem] p-4">
                <div className="mb-4 flex items-center justify-between gap-4">
                  <span className="text-sm tracking-widest uppercase text-[var(--ts-text)]">VLM Online (Cloud)</span>
                  <button
                    title="Toggle VLM Online"
                    onClick={() => updateSetting({ vlmOnline: !s.vlmOnline })}
                    className={`relative flex h-8 w-14 items-center rounded-full px-1 transition-colors ${
                      s.vlmOnline ? "bg-[var(--ts-accent)]" : "bg-[color:var(--ts-border)]"
                    }`}
                  >
                    <div
                      className={`h-6 w-6 rounded-full transition-transform ${
                        s.vlmOnline ? "translate-x-6 bg-white" : "translate-x-0 bg-slate-500"
                      }`}
                    />
                  </button>
                </div>
                {s.vlmOnline && (
                  <div className="space-y-4 animate-[ts-fade-in_0.3s_ease-out]">
                    <div className="flex flex-col gap-2">
                      <label className={labelClass}>VLM Cloud URL</label>
                      <input
                        value={s.vlmCloudUrl}
                        onChange={(e) => updateSetting({ vlmCloudUrl: e.target.value })}
                        className="ts-input focus:outline-none"
                        placeholder="https://your-ollama-cloud-endpoint.com"
                      />
                    </div>
                    <div className="flex flex-col gap-2">
                      <label className={labelClass}>VLM Cloud Model</label>
                      <input
                        value={s.vlmCloudModel}
                        onChange={(e) => updateSetting({ vlmCloudModel: e.target.value })}
                        className="ts-input focus:outline-none"
                        placeholder="llama3-vision:11b"
                      />
                    </div>
                  </div>
                )}
                <div className={helperClass}>When enabled, the robot will prefer the cloud model for vision analysis to reduce local load.</div>
              </div>
            </div>
          </div>
        </section>

        <section>
          <SectionTitle icon={MonitorSpeaker} title="Voice & Speech Systems" />
          <div className="space-y-6 sm:space-y-8">
            <div className="grid grid-cols-1 gap-5 md:grid-cols-2 md:gap-8">
              <div className="flex flex-col gap-2">
                <label className={labelClass}>Robot Base Language</label>
                <input
                  title="Robot Language"
                  placeholder="e.g. ar-EG"
                  value={s.robotLanguage}
                  onChange={(e) => updateSetting({ robotLanguage: e.target.value })}
                  className="ts-input focus:outline-none"
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelClass}>TTS Provider</label>
                <select
                  title="TTS Provider"
                  value={s.ttsProvider}
                  onChange={(e) => updateSetting({ ttsProvider: e.target.value as SettingsState["ttsProvider"] })}
                  className="ts-select focus:outline-none"
                >
                  <option value="gemini">Gemini Live</option>
                  <option value="chatterbox">Chatterbox Local (Offline)</option>
                  <option value="edge">Egyptian Neural (Edge)</option>
                  <option value="pyttsx3">System SAPI (pyttsx3)</option>
                  <option value="gtts">Google (gTTS)</option>
                  <option value="coqui">Coqui VITS</option>
                </select>
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelClass}>Voice Gender</label>
                <select
                  title="Voice Gender"
                  value={s.ttsVoiceGender}
                  onChange={(e) => updateSetting({ ttsVoiceGender: e.target.value as SettingsState["ttsVoiceGender"] })}
                  className="ts-select focus:outline-none"
                >
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                </select>
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelClass}>STT Language (Mic)</label>
                <input
                  title="STT Language"
                  placeholder="e.g. ar-EG"
                  value={s.sttLang}
                  onChange={(e) => updateSetting({ sttLang: e.target.value })}
                  className="ts-input focus:outline-none"
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelClass}>TTS Output Language</label>
                <input
                  title="TTS Output Language"
                  placeholder="e.g. ar-EG"
                  value={s.ttsLang}
                  onChange={(e) => updateSetting({ ttsLang: e.target.value })}
                  className="ts-input focus:outline-none"
                />
              </div>

              <div className="ts-surface-card rounded-[1.5rem] p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm tracking-widest uppercase text-[var(--ts-text)]">STT Online (Google)</span>
                    <span className={helperClass}>Better accuracy for Egyptian Arabic.</span>
                  </div>
                  <button
                    title="Toggle STT Online"
                    onClick={() => updateSetting({ sttOnline: !s.sttOnline })}
                    className={`relative flex h-8 w-14 items-center rounded-full px-1 transition-colors ${
                      s.sttOnline ? "bg-[var(--ts-accent)]" : "bg-[color:var(--ts-border)]"
                    }`}
                  >
                    <div
                      className={`h-6 w-6 rounded-full transition-transform ${
                        s.sttOnline ? "translate-x-6 bg-white" : "translate-x-0 bg-slate-500"
                      }`}
                    />
                  </button>
                </div>
              </div>

              <div className="ts-surface-card rounded-[1.5rem] p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm tracking-widest uppercase text-[var(--ts-text)]">TTS Online (Edge)</span>
                    <span className={helperClass}>High quality Egyptian voices.</span>
                  </div>
                  <button
                    title="Toggle TTS Online"
                    onClick={() => updateSetting({ ttsOnline: !s.ttsOnline })}
                    className={`relative flex h-8 w-14 items-center rounded-full px-1 transition-colors ${
                      s.ttsOnline ? "bg-[var(--ts-accent)]" : "bg-[color:var(--ts-border)]"
                    }`}
                  >
                    <div
                      className={`h-6 w-6 rounded-full transition-transform ${
                        s.ttsOnline ? "translate-x-6 bg-white" : "translate-x-0 bg-slate-500"
                      }`}
                    />
                  </button>
                </div>
              </div>
              {s.ttsProvider !== "chatterbox" || s.chatterboxVoiceMode === "predefined" ? (
                <div className="flex flex-col gap-2">
                  <label className={labelClass}>Voice URI / Voice Id</label>
                  <input
                    title="Voice URI"
                    placeholder={
                      s.ttsProvider === "edge"
                        ? "leave blank for auto by gender"
                        : s.ttsProvider === "chatterbox"
                          ? "e.g. Layla.wav"
                          : "system voice id or URI"
                    }
                    value={s.ttsVoiceURI}
                    onChange={(e) => updateSetting({ ttsVoiceURI: e.target.value })}
                    className="ts-input focus:outline-none"
                  />
                </div>
              ) : null}
              {s.ttsProvider === "chatterbox" ? (
                <>
                  <div className="flex flex-col gap-2">
                    <label className={labelClass}>Chatterbox Server URL</label>
                    <input
                      title="Chatterbox Server URL"
                      placeholder="http://127.0.0.1:8004"
                      value={s.chatterboxBaseUrl}
                      onChange={(e) => updateSetting({ chatterboxBaseUrl: e.target.value })}
                      className="ts-input focus:outline-none"
                    />
                    <div className={helperClass}>Keep it local for fully offline speech generation.</div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <label className={labelClass}>Chatterbox Install Directory</label>
                    <input
                      title="Chatterbox Install Directory"
                      placeholder="folder that contains server.py and venv"
                      value={s.chatterboxInstallDir}
                      onChange={(e) => updateSetting({ chatterboxInstallDir: e.target.value })}
                      className="ts-input focus:outline-none"
                    />
                    <div className={helperClass}>Used by the one-click launcher to auto-start the local Chatterbox server.</div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <label className={labelClass}>Chatterbox Voice Mode</label>
                    <select
                      title="Chatterbox Voice Mode"
                      value={s.chatterboxVoiceMode}
                      onChange={(e) =>
                        updateSetting({
                          chatterboxVoiceMode: e.target.value as SettingsState["chatterboxVoiceMode"],
                        })
                      }
                      className="ts-select focus:outline-none"
                    >
                      <option value="predefined">Voice Preset</option>
                      <option value="clone">Clone from Reference</option>
                    </select>
                    <div className={helperClass}>Clone mode gives the strongest Egyptian voice when you upload a local sample.</div>
                  </div>
                </>
              ) : null}
              {s.ttsProvider === "edge" || (isChatterboxProvider && s.chatterboxVoiceMode === "predefined") ? (
                <div className="flex flex-col gap-2">
                  <label className={labelClass}>{s.ttsProvider === "edge" ? "Edge Voice Preset" : "Chatterbox Voice Preset"}</label>
                  <select
                    title={s.ttsProvider === "edge" ? "Edge Voice Preset" : "Chatterbox Voice Preset"}
                    value={s.ttsVoiceURI}
                    onChange={(e) => updateSetting({ ttsVoiceURI: e.target.value })}
                    className="ts-select focus:outline-none"
                  >
                    <option value="">
                      {s.ttsProvider === "edge"
                        ? `Auto by gender (${s.ttsVoiceGender === "male" ? "Shakir" : "Salma"})`
                        : `Auto by gender (${s.ttsVoiceGender === "male" ? "Michael.wav" : "Layla.wav"})`}
                    </option>
                    {visibleTtsVoices.map((voice) => (
                      <option key={voice.ShortName} value={voice.ShortName}>
                        {voice.FriendlyName || voice.ShortName}
                        {voice.Gender ? ` · ${voice.Gender}` : ""}
                      </option>
                    ))}
                  </select>
                  <div className={ttsVoicesError ? "text-[11px] leading-5 text-red-500 sm:text-xs" : helperClass}>
                    {ttsVoicesError ||
                      (s.ttsProvider === "edge"
                        ? `Showing ${visibleTtsVoices.length} voice options for ${ttsLanguage}. Leave it on auto if you only want بنت / ولد.`
                        : `Showing ${visibleTtsVoices.length} local Chatterbox voices. Leave it on auto to map by gender.`)}
                  </div>
                </div>
              ) : null}
              {isChatterboxCloneMode ? (
                <div className="flex flex-col gap-3 md:col-span-2">
                  <div className="flex flex-col gap-2">
                    <label className={labelClass}>Reference Voice File</label>
                    <select
                      title="Reference Voice File"
                      value={s.chatterboxReferenceAudio}
                      onChange={(e) => updateSetting({ chatterboxReferenceAudio: e.target.value })}
                      className="ts-select focus:outline-none"
                    >
                      <option value="">Use preset fallback until a reference is selected</option>
                      {referenceFiles.map((fileName) => (
                        <option key={fileName} value={fileName}>
                          {fileName}
                        </option>
                      ))}
                    </select>
                    <div className={referenceFilesError ? "text-[11px] leading-5 text-red-500 sm:text-xs" : helperClass}>
                      {referenceFilesError ||
                        (referenceFiles.length > 0
                          ? "Choose your uploaded Egyptian sample. If no file is selected, Chatterbox falls back to the preset voice."
                          : "No reference audio uploaded yet. Upload a short clean Egyptian sample in wav or mp3.")}
                    </div>
                  </div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <button
                      onClick={() => {
                        void loadChatterboxReferenceFiles();
                      }}
                      disabled={referenceFilesLoading || uploadingReferenceAudio}
                      className="ts-btn ts-btn-ghost w-full rounded-full px-5 py-3 text-xs uppercase tracking-[0.18em] sm:w-auto"
                    >
                      {referenceFilesLoading ? "Loading References..." : "Refresh References"}
                    </button>
                    <button
                      onClick={() => {
                        referenceAudioInputRef.current?.click();
                      }}
                      disabled={uploadingReferenceAudio || previewingVoice}
                      className="ts-btn ts-btn-ghost w-full rounded-full px-5 py-3 text-xs uppercase tracking-[0.18em] sm:w-auto"
                    >
                      {uploadingReferenceAudio ? "Uploading..." : "Upload Reference Audio"}
                    </button>
                    <input
                      ref={referenceAudioInputRef}
                      type="file"
                      accept=".wav,.mp3,audio/wav,audio/mpeg,audio/*"
                      className="hidden"
                      onChange={(e) => {
                        void uploadReferenceAudio(e.target.files);
                      }}
                    />
                  </div>
                </div>
              ) : null}
              <div className="flex flex-col gap-2 md:col-span-2">
                <label className={labelClass}>TTS Cache Directory</label>
                <input
                  title="TTS Cache Directory"
                  placeholder="./data/tts_cache"
                  value={s.ttsCacheDir}
                  onChange={(e) => updateSetting({ ttsCacheDir: e.target.value })}
                  className="ts-input focus:outline-none"
                />
              </div>
            </div>

            <div className="ts-surface-panel rounded-[1.5rem] p-4 sm:rounded-[1.75rem] sm:p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <label className={labelClass}>Voice Preview</label>
                  <div className="mt-2 text-sm text-[var(--ts-text)]">
                    {previewSpeechText(ttsLanguage)}
                  </div>
                  <div className={`mt-2 ${helperClass}`}>
                    Test the current speech settings before saving them to the host.
                  </div>
                </div>
                <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
                  {s.ttsProvider === "edge" || (isChatterboxProvider && s.chatterboxVoiceMode === "predefined") ? (
                    <button
                      onClick={() => {
                        void loadTtsVoices();
                      }}
                      disabled={ttsVoicesLoading || previewingVoice}
                      className="ts-btn ts-btn-ghost w-full rounded-full px-5 py-3 text-xs uppercase tracking-[0.18em] sm:w-auto"
                    >
                      {ttsVoicesLoading ? "Loading Voices..." : s.ttsProvider === "chatterbox" ? "Refresh Local Voices" : "Refresh Voices"}
                    </button>
                  ) : null}
                  <button
                    onClick={() => {
                      void previewCurrentVoice();
                    }}
                    disabled={previewingVoice || uploadingReferenceAudio}
                    className="ts-btn ts-btn-primary w-full rounded-full px-5 py-3 text-xs uppercase tracking-[0.18em] sm:w-auto"
                  >
                    {previewingVoice ? "Playing..." : "Preview Voice"}
                  </button>
                </div>
              </div>
            </div>

            <div className="ts-surface-panel rounded-[1.5rem] p-4 sm:rounded-[1.75rem] sm:p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <label className={labelClass}>Speech Rate</label>
                  <div className="mt-2 text-3xl font-light tracking-tight text-[var(--ts-text)]">
                    {s.ttsRate.toFixed(2)}
                    <span className="ml-2 text-base text-[var(--ts-muted)]">x</span>
                  </div>
                </div>
                <input
                  title="Speech Rate"
                  type="number"
                  min="0.6"
                  max="1.5"
                  step="0.05"
                  value={s.ttsRate}
                  onChange={(e) => updateSetting({ ttsRate: clampTtsRate(Number(e.target.value) || 1) })}
                  className="ts-input w-full text-center focus:outline-none sm:w-28"
                />
              </div>
              <input
                title="Speech Rate Slider"
                type="range"
                min="0.6"
                max="1.5"
                step="0.05"
                value={s.ttsRate}
                onChange={(e) => updateSetting({ ttsRate: clampTtsRate(Number(e.target.value)) })}
                className="ts-slider mt-5"
              />
              <div className={`mt-3 ${helperClass}`}>Recommended range for the Egyptian neural voice is 0.60 to 1.50.</div>
            </div>
          </div>
        </section>

        <section>
          <SectionTitle icon={Camera} title="Camera & Peripherals" />
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 md:gap-8">
            <div className="flex flex-col gap-2">
              <label className={labelClass}>Camera Resolution</label>
              <select
                title="Camera Resolution"
                value={s.cameraResolution}
                onChange={(e) => updateSetting({ cameraResolution: e.target.value })}
                className="ts-select focus:outline-none"
              >
                <option value="320x240">320x240 (Fast)</option>
                <option value="640x480">640x480 (Standard)</option>
                <option value="1280x720">1280x720 (HD)</option>
              </select>
            </div>
            <div className="flex flex-col gap-2">
              <label className={labelClass}>Max FPS Capture</label>
              <input
                title="Camera FPS"
                placeholder="15"
                type="number"
                min="1"
                max="60"
                value={s.cameraFps}
                onChange={(e) => updateSetting({ cameraFps: Number(e.target.value) })}
                className="ts-input focus:outline-none"
              />
            </div>
          </div>

          <div className="ts-surface-card mt-8 rounded-[1.5rem] p-4">
            <div className="mb-4 flex items-center justify-between gap-4">
              <span className="text-sm tracking-widest uppercase text-[var(--ts-text)]">Gesture Detection Engine</span>
              <button
                title="Toggle Gestures"
                onClick={() => updateSetting({ gestureDetectionEnabled: !s.gestureDetectionEnabled })}
                className={`relative flex h-8 w-14 items-center rounded-full px-1 transition-colors ${
                  s.gestureDetectionEnabled ? "bg-[var(--ts-accent)]" : "bg-[color:var(--ts-border)]"
                }`}
              >
                <div
                  className={`h-6 w-6 rounded-full transition-transform ${
                    s.gestureDetectionEnabled ? "translate-x-6 bg-white" : "translate-x-0 bg-slate-500"
                  }`}
                />
              </button>
            </div>
            <div className="flex flex-col gap-2">
              <label className={labelClass}>Gesture Bindings (JSON)</label>
              <textarea
                value={gestureBindingsDraft}
                onChange={(e) => {
                  const value = e.target.value;
                  setGestureBindingsDraft(value);
                  const parsed = parseGestureBindingsText(value);
                  if (!parsed.ok) {
                    setGestureBindingsError(parsed.error);
                    setSaveError(null);
                    return;
                  }
                  setGestureBindingsError(null);
                  updateSetting({ gestureBindings: parsed.value });
                }}
                rows={7}
                className="ts-input min-h-[8.5rem] resize-y font-mono text-sm leading-6 focus:outline-none sm:min-h-[10rem]"
                placeholder={'{\n  "swipe_left": "turn_left",\n  "thumbs_up": "wake_up_ai"\n}'}
              />
              <div className={gestureBindingsError ? "text-[11px] leading-5 text-red-500 sm:text-xs" : helperClass}>
                {gestureBindingsError || "Map gesture labels to robot actions using JSON."}
              </div>
            </div>
          </div>
        </section>

        <section>
          <SectionTitle icon={Paintbrush} title="App Preferences" />
          <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <label className={labelClass}>App Theme</label>
              <select
                title="App Theme"
                value={s.themePreference}
                onChange={(e) => updateSetting({ themePreference: e.target.value as SettingsState["themePreference"] })}
                className="ts-select focus:outline-none"
              >
                <option value="dark">Night Manual</option>
                <option value="light">Day Manual</option>
                <option value="auto">Auto By Host Time</option>
              </select>
            </div>
            <div className="ts-surface-card mt-6 flex h-full items-center justify-between rounded-[1.5rem] p-4">
              <span className="text-sm tracking-widest uppercase text-[var(--ts-muted)]">LLM Cache</span>
              <button
                title="Toggle LLM Cache"
                onClick={() => updateSetting({ llmCacheEnabled: !s.llmCacheEnabled })}
                className={`relative flex h-8 w-14 items-center rounded-full px-1 transition-colors ${
                  s.llmCacheEnabled ? "bg-[var(--ts-accent)]" : "bg-[color:var(--ts-border)]"
                }`}
              >
                <div
                  className={`h-6 w-6 rounded-full transition-transform ${
                    s.llmCacheEnabled ? "translate-x-6 bg-white" : "translate-x-0 bg-slate-500"
                  }`}
                />
              </button>
            </div>
          </div>
        </section>

        <section>
          <SectionTitle icon={Save} title="Operating Profiles" />
          <div className="ts-surface-panel grid grid-cols-1 gap-6 rounded-[1.75rem] p-4 sm:gap-8 sm:p-6 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <label className={labelClass}>Active Profile</label>
              <select
                title="Active Profile"
                value={s.activeProfileId || ""}
                onChange={(e) => applyProfile(e.target.value)}
                className="ts-select focus:outline-none"
              >
                <option value="">— Factory Default —</option>
                {s.profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-2">
              <label className={labelClass}>Save Current State</label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  title="Profile Name"
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                  className="ts-input flex-1 focus:outline-none"
                  placeholder="Profile name..."
                />
                <button onClick={handleSaveProfile} className="ts-btn ts-btn-ghost px-6 text-xs uppercase tracking-widest">
                  Commit
                </button>
              </div>
            </div>
            <div className="md:col-span-2">
              <label className={labelClass}>Stored Profiles</label>
              <div className="mt-3 space-y-3">
                {s.profiles.length === 0 ? (
                  <div className="ts-surface-card rounded-[1.25rem] px-4 py-3 text-sm text-[var(--ts-muted)]">
                    No saved profiles yet.
                  </div>
                ) : (
                  s.profiles.map((profile) => (
                    <div
                      key={profile.id}
                      className="ts-surface-card flex flex-col gap-3 rounded-[1.25rem] px-4 py-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div>
                        <div className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--ts-text)]">
                          {profile.name}
                        </div>
                        <div className="mt-1 text-[11px] uppercase tracking-[0.14em] text-[var(--ts-muted)]">
                          Created {new Date(profile.createdAtMs).toLocaleString()}
                        </div>
                      </div>
                      <div className="flex gap-2 sm:min-w-[13rem]">
                        <button
                          onClick={() => applyProfile(profile.id)}
                          className="ts-btn ts-btn-ghost flex-1 px-4 py-2 text-[11px] uppercase tracking-[0.16em]"
                        >
                          Apply
                        </button>
                        <button
                          onClick={() => handleDeleteProfile(profile.id)}
                          className="ts-btn ts-btn-danger px-4 py-2 text-[11px] uppercase tracking-[0.16em]"
                          title="Delete profile"
                        >
                          <Trash2 className="h-4 w-4" strokeWidth={1.8} />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </section>
      </div>

      <div className="fixed inset-x-3 bottom-[calc(env(safe-area-inset-bottom)+0.85rem)] z-30 sm:hidden">
        <div className="ts-surface-panel flex items-center gap-3 rounded-[1.35rem] px-3 py-3">
          <div className="min-w-0 flex-1">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--ts-muted)]">
              {gestureBindingsError ? "Gesture JSON needs fix" : hasPendingChanges ? "Pending sync" : "Host state"}
            </div>
            <div className="truncate text-sm font-semibold text-[var(--ts-text)]">
              {gestureBindingsError
                ? gestureBindingsError
                : hasPendingChanges
                  ? "Changes ready to save"
                  : statusText({ loading, saving, saveError, gestureBindingsError, hasPendingChanges, savedAtMs, status })}
            </div>
          </div>
          <button
            onClick={() => {
              void syncToRobot();
            }}
            disabled={loading || saving || !hasPendingChanges}
            className="ts-btn ts-btn-primary min-w-[7rem] rounded-full px-4 py-3 text-[11px] uppercase tracking-[0.18em]"
          >
            {mobileSaveLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Settings() {
  return (
    <AppShell title="CONFIGURATION">
      <SettingsContent />
    </AppShell>
  );
}
