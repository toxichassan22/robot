import { useEffect, useMemo, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { Badge, Button, Card } from "../components/Card";
import { AdvancedMode } from "../components/AdvancedMode";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { useTts } from "../hooks/useTts";
import { useSettingsStore } from "../stores/settingsStore";
import { useLogStore, type LogState } from "../stores/logStore";
import { useNotificationStore, type NotificationState } from "../stores/notificationStore";
import { useTemplatesStore, type TemplatesState } from "../stores/templatesStore";
import { extractCommandsFromText, type ExtractedCommand } from "../utils/commandExtractor";
import { getJson, getRobotAuthHeaders, requestRobotAuth, validateModelName, validateOllamaBaseUrl, type ActionCommand } from "../utils/api";
import { parseSSEStream } from "../utils/sseParser";
import { Copy, Loader2, Mic, MicOff, Send, Volume2, VolumeX, XCircle, Cloud, Terminal, CheckCircle2, AlertCircle, Image as ImageIcon } from "lucide-react";
import { cn } from "../lib/utils";

type HealthResponse = { ok: boolean; message?: string };

export default function Home() {
  const settings = useSettingsStore();
  const addLog = useLogStore((s: LogState) => s.add);
  const notify = useNotificationStore((s: NotificationState) => s.push);
  const templates = useTemplatesStore((s: TemplatesState) => s.templates);
  const addTemplate = useTemplatesStore((s: TemplatesState) => s.add);
  const removeTemplate = useTemplatesStore((s: TemplatesState) => s.remove);
  const navigate = useNavigate();

  const [wakeWordEnabled, setWakeWordEnabled] = useState(false);
  const [wakeWord, setWakeWord] = useState("aria");
  const stt = useSpeechRecognition({ lang: settings.sttLang, wakeWordEnabled, wakeWord, sleepTimeoutMs: 20_000 });
  const tts = useTts();

  const [busy, setBusy] = useState(false);
  const [llmText, setLlmText] = useState("");
  const [llmAction, setLlmAction] = useState<ActionCommand | null>(null);
  const [health, setHealth] = useState<{ ollama?: HealthResponse }>({});
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"local" | "cloud">("local");
  const [cloudModelName, setCloudModelName] = useState("");
  const [pullBusy, setPullBusy] = useState(false);
  const [pullMsg, setPullMsg] = useState<string | null>(null);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [newTemplateName, setNewTemplateName] = useState("");
  const [newTemplateText, setNewTemplateText] = useState("");
  const [advancedEnabled, setAdvancedEnabled] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [llmMeta, setLlmMeta] = useState<Record<string, unknown> | null>(null);
  const [llmRaw, setLlmRaw] = useState<unknown>(null);
  const [feedbackInteractionId, setFeedbackInteractionId] = useState("");
  const [feedbackRating, setFeedbackRating] = useState<number | null>(null);
  const [feedbackCorrection, setFeedbackCorrection] = useState("");
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);

  const [pullProgress, setPullProgress] = useState<{ status: string; completed?: number; total?: number } | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const generateAbortRef = useRef<AbortController | null>(null);

  const localCommands = useMemo(() => extractCommandsFromText(stt.text), [stt.text]);
  const selectedProvider = "ollama";
  const selectedModel = settings.ollamaModel;
  const isLocal = settings.ollamaBaseUrl.includes("127.0.0.1") || settings.ollamaBaseUrl.includes("localhost");

  const [visionBusy, setVisionBusy] = useState(false);
  const [visionText, setVisionText] = useState("");
  const [visionImage, setVisionImage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const analyzeImage = async (file: File) => {
    setVisionBusy(true);
    setVisionText("");
    const formData = new FormData();
    formData.append("file", file);
    formData.append("prompt", "Describe this image in detail.");

    try {
      const r = await fetch("/api/vision/analyze", {
        method: "POST",
        headers: { ...getRobotAuthHeaders() },
        body: formData,
        credentials: "include",
      });
      const data = await r.json();
      if (data.success) {
        setVisionText(data.description);
      } else {
        setVisionText(`Error: ${data.error}`);
      }
    } catch (e) {
      setVisionText(`Error: ${e}`);
    } finally {
      setVisionBusy(false);
    }
  };

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (visionImage) URL.revokeObjectURL(visionImage);
      setVisionImage(URL.createObjectURL(file));
      void analyzeImage(file);
    }
  };

  const canSend = Boolean(stt.text.trim()) && Boolean(selectedModel.trim()) && !busy;

  useEffect(() => {
    return () => {
      const controller = abortControllerRef.current;
      if (controller) controller.abort();
      abortControllerRef.current = null;
      const gen = generateAbortRef.current;
      if (gen) gen.abort();
      generateAbortRef.current = null;
    };
  }, []);

  const cancelAll = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setPullBusy(false);
      setPullMsg("تم الإلغاء.");
      setPullProgress(null);
    }
    if (generateAbortRef.current) {
      generateAbortRef.current.abort();
      generateAbortRef.current = null;
    }
    if (stt.listening) stt.stop();
    tts.stop();
  };

  const checkHealth = async () => {
    try {
      const baseUrl = validateOllamaBaseUrl(settings.ollamaBaseUrl, "عنوان Ollama");
      const o = await getJson<HealthResponse>(`/api/health/ollama?baseUrl=${encodeURIComponent(baseUrl)}`);
      setHealth({ ollama: o });
    } catch (e) {
      setHealth({ ollama: { ok: false, message: String(e) } });
    }
  };

  const loadOllamaModels = async () => {
    try {
      const baseUrl = validateOllamaBaseUrl(settings.ollamaBaseUrl, "عنوان Ollama");
      const r = await getJson<{ success: boolean; models: string[] }>(
        `/api/llm/ollama-models?baseUrl=${encodeURIComponent(baseUrl)}`,
      );
      const models = r.success ? r.models : [];
      setOllamaModels(models);
      if (models.length && !models.includes(settings.ollamaModel)) {
        settings.set({ ollamaModel: models[0] });
      }
    } catch {
      setOllamaModels([]);
    }
  };

  const cancelPull = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setPullBusy(false);
      setPullMsg("تم إلغاء التحميل.");
      setPullProgress(null);
    }
  };

  const pullAndRun = async () => {
    let name: string;
    let baseUrl: string;
    try {
      name = validateModelName(cloudModelName, "اسم الموديل");
      baseUrl = validateOllamaBaseUrl(settings.ollamaBaseUrl, "عنوان Ollama");
    } catch (e) {
      setPullMsg(String(e));
      return;
    }
    setPullBusy(true);
    setPullMsg(null);
    setPullProgress(null);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch("/api/llm/ollama-pull", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getRobotAuthHeaders() },
        body: JSON.stringify({ name, ollamaBaseUrl: baseUrl }),
        signal: controller.signal,
        credentials: "include",
      });

      if (!response.ok) {
        console.error("ollama-pull HTTP error", { status: response.status, statusText: response.statusText });
        setPullMsg(`HTTP Error: ${response.status}`);
        return;
      }

      if (!response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n");
        buffer = parts.pop() ?? "";

        for (const rawLine of parts) {
          const line = rawLine.trim();
          if (!line) continue;

          if (!line.startsWith("{") && !line.startsWith("[")) {
            continue;
          }

          let data: unknown;
          try {
            data = JSON.parse(line);
          } catch (e) {
            console.error("ollama-pull JSON parse error", { error: String(e), line: line.slice(0, 200) });
            setPullMsg("تعذر تفسير استجابة التحميل من السيرفر.");
            throw e;
          }

          if (!data || typeof data !== "object" || Array.isArray(data)) {
            continue;
          }

          const obj = data as Record<string, unknown>;

          if (obj.error != null) {
            const msg = String(obj.error);
            console.error("ollama-pull server error", { error: msg });
            setPullMsg(msg);
            throw new Error(msg);
          }

          if (obj.status != null) {
            setPullProgress({
              status: String(obj.status),
              completed: typeof obj.completed === "number" ? obj.completed : undefined,
              total: typeof obj.total === "number" ? obj.total : undefined,
            });
          }
        }
      }

      const tail = buffer.trim();
      if (tail) {
        if (tail.startsWith("{") || tail.startsWith("[")) {
          try {
            const data: unknown = JSON.parse(tail);
            if (data && typeof data === "object" && !Array.isArray(data)) {
              const obj = data as Record<string, unknown>;
              if (obj.error != null) {
                const msg = String(obj.error);
                console.error("ollama-pull server error (tail)", { error: msg });
                setPullMsg(msg);
                throw new Error(msg);
              }
              if (obj.status != null) {
                setPullProgress({
                  status: String(obj.status),
                  completed: typeof obj.completed === "number" ? obj.completed : undefined,
                  total: typeof obj.total === "number" ? obj.total : undefined,
                });
              }
            }
          } catch (e) {
            console.error("ollama-pull JSON parse error (tail)", { error: String(e), line: tail.slice(0, 200) });
          }
        }
      }

      setPullMsg("تم التحميل بنجاح!");
      setPullProgress(null);
      await loadOllamaModels();
      settings.set({ ollamaModel: name });
      setActiveTab("local");
    } catch (e) {
      if (controller.signal.aborted) return;
      console.error("ollama-pull failed", e);
      setPullMsg(String(e));
    } finally {
      if (abortControllerRef.current === controller) abortControllerRef.current = null;
      if (!controller.signal.aborted) setPullBusy(false);
    }
  };

  const sendToModel = async () => {
    const inputText = stt.text.trim();
    const startedAtMs = Date.now();
    const interactionId = `${startedAtMs.toString(16)}-${Math.random().toString(16).slice(2)}`;
    setFeedbackInteractionId(interactionId);
    setFeedbackRating(null);
    setFeedbackCorrection("");
    setFeedbackBusy(false);
    setFeedbackSent(false);
    let model: string;
    let baseUrl: string;
    try {
      model = validateModelName(selectedModel, "اسم الموديل");
      baseUrl = validateOllamaBaseUrl(settings.ollamaBaseUrl, "عنوان Ollama");
    } catch (e) {
      const msg = String(e);
      notify({ kind: "error", title: "مدخلات غير صالحة", message: msg, details: msg, ttlMs: 6000 });
      addLog({
        ts: Date.now(),
        provider: selectedProvider,
        model: selectedModel,
        heardText: inputText,
        localCommands,
        llmOutputText: "",
        llmAction: null,
        error: msg,
        durationMs: Date.now() - startedAtMs,
      });
      return;
    }

    setBusy(true);
    setLlmText("");
    setLlmAction(null);
    setLlmMeta(null);
    setLlmRaw(null);

    try {
      const body = {
        provider: selectedProvider,
        model,
        inputText,
        ollamaBaseUrl: baseUrl,
        stream: true,
        systemPrompt: advancedEnabled && systemPrompt.trim() ? systemPrompt.trim() : undefined,
        cacheEnabled: settings.llmCacheEnabled,
      };
      if (generateAbortRef.current) {
        generateAbortRef.current.abort();
        generateAbortRef.current = null;
      }
      const controller = new AbortController();
      generateAbortRef.current = controller;

      let r = await fetch("/api/llm/generate?stream=1", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...getRobotAuthHeaders() },
        body: JSON.stringify(body),
        signal: controller.signal,
        credentials: "include",
      });
      if (r.status === 401) {
        const ok = await requestRobotAuth("unauthorized");
        if (ok) {
          r = await fetch("/api/llm/generate?stream=1", {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...getRobotAuthHeaders() },
            body: JSON.stringify(body),
            signal: controller.signal,
            credentials: "include",
          });
        }
      }

      if (!r.ok) {
        const t = await r.text().catch(() => "");
        throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
      }
      if (!r.body) throw new Error("لا يوجد stream من السيرفر.");

      let output = "";
      let action: ActionCommand | null = null;
      let raw: unknown = null;
      let meta: Record<string, unknown> | null = null;

      output = await parseSSEStream(r.body, {
        onToken: (token) => {
          setLlmText((p) => p + token);
        },
        onDone: (result) => {
          output = result.outputText || output;
          action = (result.action as ActionCommand | null) || null;
          raw = result.raw;
          meta = result.meta ?? null;
        },
        onError: (error) => {
          throw new Error(error);
        },
      });

      setLlmText(output);
      setLlmAction(action);
      setLlmMeta(meta);
      setLlmRaw(raw);
      addLog({
        ts: Date.now(),
        provider: selectedProvider,
        model,
        heardText: inputText,
        localCommands,
        llmOutputText: output,
        llmAction: action,
        error: null,
        durationMs: Date.now() - startedAtMs,
      });
      void raw;
    } catch (e) {
      if (generateAbortRef.current?.signal.aborted) return;
      const msg = String(e);
      notify({ kind: "error", title: "فشل إرسال للموديل", message: msg, details: msg, ttlMs: 0 });
      addLog({
        ts: Date.now(),
        provider: selectedProvider,
        model,
        heardText: inputText,
        localCommands,
        llmOutputText: "",
        llmAction: null,
        error: msg,
        durationMs: Date.now() - startedAtMs,
      });
    } finally {
      generateAbortRef.current = null;
      setBusy(false);
    }
  };

  useKeyboardShortcuts({
    onSpace: () => {
      if (!stt.supported) return;
      if (stt.listening) stt.stop();
      else stt.start();
    },
    onEnter: () => {
      if (!canSend) return;
      void sendToModel();
    },
    onCtrlK: () => {
      setCommandPaletteOpen(true);
    },
    onCtrlComma: () => {
      navigate("/settings");
    },
    onEscape: () => {
      cancelAll();
      setCommandPaletteOpen(false);
    },
  });

  const speak = async () => {
    const payloadText =
      llmAction && llmAction.kind === "say" && llmAction.payload && typeof llmAction.payload === "object"
        ? (llmAction.payload as { text?: unknown }).text
        : "";
    const text = (llmAction?.kind === "say" ? String(payloadText || "") : llmText) || "";
    if (!text.trim()) return;

    try {
      const endpoint = settings.ttsProvider === "coqui" ? "/api/tts/coqui" : "/api/tts/speak";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getRobotAuthHeaders() },
        body: JSON.stringify({
          text,
          lang: settings.ttsLang || settings.robotLanguage || "ar",
        }),
      });
      const data = await res.json();
      if (data.success && data.audio) {
        const audioFormat = data.format || "mp3";
        const src = `data:audio/${audioFormat};base64,${data.audio}`;
        const audio = new Audio(src);
        audio.play().catch(e => console.error("Audio block playback failed:", e));
      } else {
        console.error("TTS Failed:", data.error);
      }
    } catch (e) {
      console.error("TTS Network Error:", e);
    }
  };

  const submitFeedback = async (rating: number) => {
    if (feedbackBusy) return;
    if (!feedbackInteractionId) return;
    setFeedbackBusy(true);
    try {
      const r = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          interactionId: feedbackInteractionId,
          rating,
          correction: feedbackCorrection,
          context: {
            inputText: stt.text,
            llmAction,
            llmText,
            output: displayOutput,
          },
        }),
      });
      const data: unknown = await r.json().catch(() => null);
      if (!data || typeof data !== "object" || Array.isArray(data) || (data as { success?: unknown }).success !== true) {
        throw new Error("فشل حفظ الـfeedback");
      }
      setFeedbackRating(rating);
      setFeedbackSent(true);
      notify({ kind: "success", title: "Feedback", message: "تم الحفظ.", ttlMs: 2500 });
    } catch (e) {
      notify({ kind: "error", title: "Feedback", message: String(e), details: String(e), ttlMs: 6000 });
    } finally {
      setFeedbackBusy(false);
    }
  };

  const displayOutput = useMemo(() => {
    if (llmAction && llmAction.kind === "say") {
      const payloadText = llmAction.payload && typeof llmAction.payload === "object"
        ? (llmAction.payload as { text?: unknown }).text
        : "";
      return String(payloadText || "");
    }
    if (llmAction) {
      return "—";
    }
    return llmText;
  }, [llmAction, llmText]);

  return (
    <AppShell title="لوحة الاختبار">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-12">
        {commandPaletteOpen ? (
          <div
            className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in"
            onMouseDown={() => setCommandPaletteOpen(false)}
          >
            <div className="ts-surface-panel w-full max-w-lg rounded-2xl p-6 shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between gap-3 mb-6">
                <div className="font-heading text-lg font-semibold text-white">الأوامر السريعة</div>
                <Button onClick={() => setCommandPaletteOpen(false)} variant="ghost" className="h-8 w-8 p-0">
                  <XCircle className="h-4 w-4" />
                </Button>
              </div>
              <div className="space-y-4">
                <div className="space-y-2 text-sm text-muted-foreground bg-white/5 p-4 rounded-xl border border-white/5">
                  <div className="flex justify-between"><span>تشغيل/إيقاف الاستماع</span> <kbd className="font-mono bg-white/10 px-1.5 rounded">Space</kbd></div>
                  <div className="flex justify-between"><span>إرسال للموديل</span> <kbd className="font-mono bg-white/10 px-1.5 rounded">Enter</kbd></div>
                  <div className="flex justify-between"><span>فتح الإعدادات</span> <kbd className="font-mono bg-white/10 px-1.5 rounded">Ctrl+,</kbd></div>
                  <div className="flex justify-between"><span>إلغاء العمليات</span> <kbd className="font-mono bg-white/10 px-1.5 rounded">Esc</kbd></div>
                </div>
                <div className="space-y-3">
                  <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Templates</div>
                  {templates.length ? (
                    <div className="flex flex-wrap gap-2">
                      {templates.slice(0, 12).map((t) => (
                        <Button
                          key={t.id}
                          variant="secondary"
                          onClick={() => {
                            stt.setFinalText(t.text);
                            setCommandPaletteOpen(false);
                          }}
                          className="text-xs"
                        >
                          {t.name}
                        </Button>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-xs text-muted-foreground border border-dashed border-white/10 rounded-xl">لا توجد Templates بعد</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : null}

        <div className="md:col-span-7 space-y-6">
          <Card
            title="الاستماع للمايك"
            right={
              <div className="flex gap-2">
                {stt.wakeStatus ? <Badge tone={stt.wakeStatus === "Active" ? "ok" : stt.wakeStatus === "Listening" ? "warn" : "neutral"}>{stt.wakeStatus}</Badge> : null}
                {stt.listening ? <Badge tone="ok">Listening</Badge> : <Badge>Stopped</Badge>}
              </div>
            }
          >
            <div className="flex flex-wrap items-center gap-3 mb-6">
              <Button
                variant={stt.listening ? "danger" : "primary"}
                disabled={!stt.supported}
                onClick={() => (stt.listening ? stt.stop() : stt.start())}
                className="w-32"
              >
                {stt.listening ? (
                  <>
                    <MicOff className="h-4 w-4" /> إيقاف
                  </>
                ) : (
                  <>
                    <Mic className="h-4 w-4" /> تشغيل
                  </>
                )}
              </Button>
              <Button onClick={stt.reset} variant="secondary">
                مسح
              </Button>
              <Button onClick={checkHealth} variant="secondary">فحص الاتصال</Button>
              <Button onClick={() => setCommandPaletteOpen(true)} variant="ghost" className="ml-auto text-xs font-mono text-muted-foreground">Ctrl+K</Button>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 p-4 bg-white/5 rounded-xl border border-white/5 mb-4">
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-white mb-2 cursor-pointer">
                  <input type="checkbox" checked={wakeWordEnabled} onChange={(e) => setWakeWordEnabled(e.target.checked)} className="rounded border-white/20 bg-white/10 text-primary focus:ring-primary" />
                  تفعيل Wake Word
                </label>
                <div className="relative">
                  <input
                    value={wakeWord}
                    onChange={(e) => setWakeWord(e.target.value)}
                    disabled={!wakeWordEnabled}
                    className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 disabled:opacity-50 placeholder:text-muted-foreground/50 transition-all"
                    placeholder="مثال: aria"
                  />
                  <div className="absolute right-3 top-2.5 text-[10px] text-muted-foreground uppercase pointer-events-none">Wake Word</div>
                </div>
              </div>

              <div className="flex flex-col justify-end">
                <StatusLine label="Ollama Service" ok={health.ollama?.ok} msg={health.ollama?.message} />
              </div>
            </div>

            {!stt.supported ? (
              <div className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-400">
                <AlertCircle className="h-4 w-4 shrink-0" />
                المتصفح لا يدعم SpeechRecognition. استخدم إدخال نص يدوي أو جرّب Chrome.
              </div>
            ) : null}
            {stt.error ? (
              <div className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                <AlertCircle className="h-4 w-4 shrink-0" />
                خطأ STT: {stt.error}
              </div>
            ) : null}
          </Card>

          <Card title="المحادثة">
            <div className="relative mb-4">
              <textarea
                className="h-40 w-full resize-none rounded-xl border border-white/10 bg-black/20 p-4 text-sm text-white outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 placeholder:text-muted-foreground/50 transition-all leading-relaxed"
                value={stt.text}
                onChange={(e) => stt.setFinalText(e.target.value)}
                placeholder="ابدأ الاستماع أو اكتب هنا لاختبار…"
              />
              <div className="absolute bottom-3 left-3 flex gap-2">
                <Button
                  disabled={!stt.text.trim()}
                  onClick={() => {
                    navigator.clipboard.writeText(stt.text).catch(() => undefined);
                  }}
                  variant="ghost"
                  className="h-6 px-2 text-xs bg-black/40 hover:bg-black/60 backdrop-blur-sm"
                >
                  <Copy className="h-3 w-3 mr-1" /> نسخ
                </Button>
              </div>
            </div>

            <div className="flex justify-end mb-8">
              <Button
                variant="primary"
                disabled={!canSend}
                onClick={sendToModel}
                className="w-full md:w-auto px-8 py-3 text-base shadow-lg shadow-primary/20"
              >
                {busy ? <Loader2 className="h-5 w-5 animate-spin mr-2" /> : <Send className="h-5 w-5 mr-2" />}
                إرسال للموديل
              </Button>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Terminal className="h-4 w-4 text-primary" />
                  رد الموديل (LLM)
                </h3>
                <div className="flex gap-2">
                  <Button variant="ghost" disabled={(!llmText.trim() && !llmAction) || busy} onClick={speak} className="h-8 px-3 text-xs">
                    <Volume2 className="h-4 w-4 mr-1.5" /> قراءة
                  </Button>
                  <Button variant="ghost" disabled={!tts.speaking} onClick={tts.stop} className="h-8 px-3 text-xs text-red-400 hover:text-red-300">
                    <VolumeX className="h-4 w-4 mr-1.5" /> إيقاف
                  </Button>
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-black/20 p-4 min-h-[120px]">
                {llmAction ? (
                  <div className="mb-4 rounded-lg bg-primary/5 border border-primary/20 p-3">
                    <div className="text-[10px] font-semibold text-primary uppercase tracking-wider mb-2">Action Detected</div>
                    <pre className="overflow-auto text-xs font-mono text-blue-200 custom-scrollbar">{JSON.stringify(llmAction, null, 2)}</pre>
                  </div>
                ) : null}

                <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
                  {displayOutput || (busy ? <span className="animate-pulse text-muted-foreground">جاري الكتابة...</span> : <span className="text-muted-foreground/40 italic">بانتظار الرد...</span>)}
                </div>
              </div>

              <div className="rounded-xl border border-white/5 bg-white/5 p-4 flex flex-col md:flex-row md:items-center gap-4 justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-semibold text-muted-foreground">هل كان الرد مفيداً؟</span>
                  <div className="flex gap-1">
                    <Button
                      variant={feedbackRating === 1 ? "primary" : "ghost"}
                      disabled={busy || feedbackBusy || !displayOutput.trim()}
                      onClick={() => void submitFeedback(1)}
                      className="h-8 w-8 p-0 rounded-full"
                    >
                      👍
                    </Button>
                    <Button
                      variant={feedbackRating === 0 ? "danger" : "ghost"}
                      disabled={busy || feedbackBusy || !displayOutput.trim()}
                      onClick={() => void submitFeedback(0)}
                      className="h-8 w-8 p-0 rounded-full"
                    >
                      👎
                    </Button>
                  </div>
                </div>

                <div className="flex-1 flex gap-2">
                  <input
                    value={feedbackCorrection}
                    onChange={(e) => setFeedbackCorrection(e.target.value)}
                    className="flex-1 rounded-lg border border-white/10 bg-black/20 px-3 py-1.5 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 placeholder:text-muted-foreground/50 transition-all"
                    placeholder="اقتراح تصحيح (اختياري)..."
                  />
                  {feedbackSent && <div className="flex items-center text-xs text-emerald-400 animate-fade-in"><CheckCircle2 className="h-4 w-4 mr-1" /> تم الإرسال</div>}
                </div>
              </div>
            </div>
          </Card>

          <Card title="اختبار الرؤية (Vision Test)">
            <div className="space-y-4">
              <div
                className="border-2 border-dashed border-white/10 rounded-xl bg-white/5 p-8 flex flex-col items-center justify-center cursor-pointer hover:bg-white/10 transition-colors"
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleImageSelect}
                  className="hidden"
                  accept="image/*"
                  title="Upload Image"
                  aria-label="Upload Image"
                />

                {visionImage ? (
                  <div className="relative w-full aspect-video rounded-lg overflow-hidden">
                    <img src={visionImage} alt="Uploaded" className="object-cover w-full h-full" />
                    {visionBusy && (
                      <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="h-12 w-12 rounded-full bg-primary/20 flex items-center justify-center mb-3">
                      <ImageIcon className="h-6 w-6 text-primary" />
                    </div>
                    <p className="text-sm text-white font-medium">اضغط لرفع صورة</p>
                    <p className="text-xs text-muted-foreground mt-1">PNG, JPG, JPEG supported</p>
                  </>
                )}
              </div>

              {visionText && (
                <div className="rounded-xl border border-white/10 bg-black/20 p-4">
                  <div className="text-[10px] font-semibold text-primary uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Terminal className="h-3 w-3" /> Vision Analysis
                  </div>
                  <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
                    {visionText}
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="md:col-span-5 space-y-6">
          <div className="sticky top-6 space-y-6">
            {/* Model Selector Card */}
            <Card title="إعدادات الموديل">
              <div className="p-1 mb-4 flex rounded-lg bg-black/20 border border-white/5">
                <button
                  className={cn("flex-1 rounded-md py-1.5 text-xs font-medium transition-all", activeTab === "local" ? "bg-primary text-white shadow-md" : "text-muted-foreground hover:text-white hover:bg-white/5")}
                  onClick={() => setActiveTab("local")}
                >
                  الموديلات المحلية
                </button>
                <button
                  className={cn("flex-1 rounded-md py-1.5 text-xs font-medium transition-all", activeTab === "cloud" ? "bg-primary text-white shadow-md" : "text-muted-foreground hover:text-white hover:bg-white/5")}
                  onClick={() => setActiveTab("cloud")}
                >
                  تحميل موديل جديد
                </button>
              </div>

              {activeTab === "local" ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex justify-between items-center text-xs text-muted-foreground">
                      <span>الموديل الحالي</span>
                      <Button onClick={loadOllamaModels} variant="ghost" className="h-6 px-2 text-[10px]">تحديث القائمة</Button>
                    </div>
                    {ollamaModels.length ? (
                      <div className="relative">
                        <select
                          value={settings.ollamaModel}
                          onChange={(e) => settings.set({ ollamaModel: e.target.value })}
                          className="w-full appearance-none rounded-xl border border-white/10 bg-black/20 px-4 py-2.5 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50"
                          title="اختر الموديل"
                          aria-label="اختر الموديل"
                        >
                          {ollamaModels.map((m) => (
                            <option key={m} value={m} className="bg-slate-900">
                              {m}
                            </option>
                          ))}
                        </select>
                        <Terminal className="absolute left-3 top-3 h-4 w-4 text-muted-foreground pointer-events-none" />
                      </div>
                    ) : (
                      <div className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-4 text-center">
                        <p className="text-sm text-amber-400 mb-2">لا توجد موديلات محملة</p>
                        <Button onClick={() => setActiveTab("cloud")} variant="secondary" className="text-xs">تحميل موديل</Button>
                      </div>
                    )}
                  </div>

                  <div className="rounded-xl border border-white/10 bg-white/5 p-3 flex items-center justify-between">
                    <div className="text-xs text-muted-foreground">Provider</div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white tracking-wide uppercase">{selectedProvider}</span>
                      <Badge tone={isLocal ? "ok" : "warn"}>{isLocal ? "LOCAL" : "REMOTE"}</Badge>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-xs text-muted-foreground">اسم الموديل (مثل mistral, llama3)</label>
                    <input
                      value={cloudModelName}
                      onChange={(e) => setCloudModelName(e.target.value)}
                      placeholder="e.g. mistral:latest"
                      className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 placeholder:text-muted-foreground/50 transition-all font-mono"
                    />
                  </div>

                  <div className="flex gap-2">
                    <Button
                      variant="primary"
                      disabled={!cloudModelName.trim() || pullBusy}
                      onClick={pullAndRun}
                      className="flex-1"
                    >
                      {pullBusy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Cloud className="h-4 w-4 mr-2" />}
                      {pullBusy ? "جاري التحميل..." : "تحميل وتشغيل"}
                    </Button>
                    {pullBusy && (
                      <Button variant="danger" onClick={cancelPull}>
                        <XCircle className="h-4 w-4" />
                      </Button>
                    )}
                  </div>

                  {pullProgress && (
                    <div className="space-y-2 rounded-xl bg-black/30 p-3 border border-white/5">
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>{pullProgress.status}</span>
                        {pullProgress.total && pullProgress.completed && (
                          <span className="text-white font-mono">{Math.round((pullProgress.completed / pullProgress.total) * 100)}%</span>
                        )}
                      </div>
                      {pullProgress.total && pullProgress.completed && (
                        <progress
                          className="h-1.5 w-full appearance-none rounded-full overflow-hidden bg-white/10 [&::-webkit-progress-bar]:bg-white/10 [&::-webkit-progress-value]:bg-primary [&::-webkit-progress-value]:transition-all [&::-webkit-progress-value]:duration-300 [&::-webkit-progress-value]:shadow-[0_0_10px_rgba(59,130,246,0.5)] [&::-moz-progress-bar]:bg-primary [&::-moz-progress-bar]:transition-all [&::-moz-progress-bar]:duration-300 [&::-moz-progress-bar]:shadow-[0_0_10px_rgba(59,130,246,0.5)]"
                          value={pullProgress.completed}
                          max={pullProgress.total}
                        />
                      )}
                    </div>
                  )}

                  {pullMsg && (
                    <div className={cn("text-xs p-3 rounded-lg border", pullMsg.includes("Error") ? "bg-red-500/10 border-red-500/20 text-red-400" : "bg-emerald-500/10 border-emerald-500/20 text-emerald-400")}>
                      {pullMsg}
                    </div>
                  )}
                </div>
              )}
            </Card>

            <AdvancedMode
              enabled={advancedEnabled}
              onToggle={() => setAdvancedEnabled((p) => !p)}
              systemPrompt={systemPrompt}
              onSystemPromptChange={setSystemPrompt}
              meta={llmMeta}
              raw={llmRaw}
            />

            <Card title="أوامر سريعة (Templates)">
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  {templates.map((t) => (
                    <div key={t.id} className="group relative">
                      <button
                        type="button"
                        className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium hover:bg-white/10 hover:border-white/20 transition-all"
                        onClick={() => stt.setFinalText(t.text)}
                      >
                        {t.name}
                      </button>
                      <button
                        onClick={() => removeTemplate(t.id)}
                        className="absolute -top-1 -right-1 hidden group-hover:flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-white shadow-sm"
                        title="حذف"
                        aria-label="حذف"
                      >
                        <XCircle className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                  {templates.length === 0 && <span className="text-xs text-muted-foreground italic">لا توجد أوامر محفوظة</span>}
                </div>

                <div className="space-y-3 pt-3 border-t border-white/5">
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      value={newTemplateName}
                      onChange={(e) => setNewTemplateName(e.target.value)}
                      className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs outline-none focus:border-primary/50 transition-all"
                      placeholder="الأسم (مثال: ترحيب)"
                    />
                    <input
                      value={newTemplateText}
                      onChange={(e) => setNewTemplateText(e.target.value)}
                      className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs outline-none focus:border-primary/50 transition-all"
                      placeholder="النص (مثال: أهلاً بك)"
                    />
                  </div>
                  <Button
                    variant="secondary"
                    disabled={!newTemplateName.trim() || !newTemplateText.trim()}
                    onClick={() => {
                      addTemplate({ name: newTemplateName, text: newTemplateText });
                      setNewTemplateName("");
                      setNewTemplateText("");
                      notify({ kind: "success", title: "Templates", message: "تمت الإضافة.", ttlMs: 3000 });
                    }}
                    className="w-full text-xs h-8"
                  >
                    إضافة للقائمة
                  </Button>
                </div>
              </div>
            </Card>

            <Card title="الأوامر المحلية">
              {localCommands.length ? (
                <div className="space-y-2">
                  {localCommands.map((c: ExtractedCommand, idx: number) => (
                    <div key={idx} className="rounded-lg border border-white/5 bg-white/5 p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                        <div className="text-xs font-medium text-white">{c.label}</div>
                      </div>
                      <pre className="overflow-auto text-[10px] font-mono text-muted-foreground bg-black/20 p-2 rounded">{JSON.stringify({ kind: c.kind, payload: c.payload }, null, 2)}</pre>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-white/10 rounded-xl">
                  لم يتم استخراج أوامر
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function StatusLine(props: { label: string; ok?: boolean; msg?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 p-2">
      <div className="text-xs font-medium text-muted-foreground">{props.label}</div>
      <div className="flex items-center gap-2">
        {props.ok === undefined ? <Badge tone="neutral">Unknown</Badge> : props.ok ? <Badge tone="ok">Connected</Badge> : <Badge tone="error">Error</Badge>}
        {/* Tooltip or expanded message could go here if needed, keeping it minimal for now */}
      </div>
    </div>
  );
}
