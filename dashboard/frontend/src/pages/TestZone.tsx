import { useState, useRef, useEffect, useCallback } from "react";
import { AppShell } from "../components/AppShell";
import {
  Camera, MessageSquare, Mic, StopCircle, CornerDownRight
} from "lucide-react";
import { useHostRuntime } from "../hooks/useHostRuntime";
import { useSettingsStore, type SettingsState } from "../stores/settingsStore";
import { getJson, getRobotAuthHeaders, requestRobotAuth } from "../utils/api";
import { parseSSEStream } from "../utils/sseParser";
import { useNotificationStore, type NotificationState } from "../stores/notificationStore";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { normalizeArabic } from "../utils/normalizeArabic";

type ModelListResponse = { success: boolean; models: string[] };
type AnalyzeResponse = { success: boolean; description: string; error?: string };

export function TestZoneContent() {
  const [activeTab, setActiveTab] = useState<"vision" | "voice">("vision");

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-3 pt-0 sm:gap-8 sm:pt-4 animate-[ts-fade-in_0.5s_ease-out]">
        
        {/* Minimal Tab Switcher */}
        <div className="shrink-0 border-b border-[color:var(--ts-border)] px-0 pb-2 sm:px-4 sm:pb-4">
          <div className="flex items-center justify-center gap-1.5 sm:gap-12">
            {(["vision", "voice"] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`relative flex-1 px-1 pb-2.5 text-[11px] font-semibold uppercase tracking-[0.16em] transition-colors sm:flex-none sm:px-2 sm:pb-4 sm:text-sm sm:tracking-[0.3em]
                  ${activeTab === tab ? "text-[var(--ts-text)]" : "text-[var(--ts-muted)] hover:text-[var(--ts-text)]"}`}
              >
                <div className="flex items-center justify-center gap-2 sm:gap-3">
                  {tab === "vision" ? <Camera className="w-4 h-4" /> : <MessageSquare className="w-4 h-4" />}
                  {tab === "vision" ? "Optical Vision" : "Core Comms"}
                </div>
                {activeTab === tab && (
                  <div className="absolute bottom-[-1px] left-0 h-[2px] w-full bg-[var(--ts-accent)] animate-[ts-fade-in_0.3s_ease-out]" />
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 min-h-0">
          {activeTab === "vision" ? <VisionTest /> : <VoiceTest />}
        </div>
    </div>
  );
}

export default function TestZone() {
  return (
    <AppShell title="DIAGNOSTICS & TESTING">
      <TestZoneContent />
    </AppShell>
  );
}

/* ════════════════ VISION ════════════════ */

function VisionTest() {
  const notify = useNotificationStore((s: NotificationState) => s.push);
  const { health } = useHostRuntime();
  const [models, setModels] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const vlmBaseUrl = useSettingsStore((s: SettingsState) => s.vlmBaseUrl);
  const vlmUnavailable = health?.services?.vlm && health.services.vlm.ready === false;

  const loadModels = useCallback(async () => {
    try {
      const r = await getJson<ModelListResponse>(`/api/vision/vlm-models?baseUrl=${encodeURIComponent(vlmBaseUrl)}`);
      if (r.success) { setModels(r.models); if (r.models.length && !selected) setSelected(r.models[0]); }
    } catch (error) {
      if (!vlmUnavailable) {
        notify({ kind: "error", title: "Vision Probe Failed", message: String(error), ttlMs: 4000 });
      }
    }
  }, [notify, selected, vlmBaseUrl, vlmUnavailable]);

  useEffect(() => { void loadModels(); }, [loadModels]);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setPreviewUrl(URL.createObjectURL(f));
    setResult(null);
  };

  const analyze = async () => {
    if (vlmUnavailable) {
      notify({ kind: "error", title: "Vision Offline", message: "Vision service is not ready on host", ttlMs: 3500 });
      return;
    }
    if (!fileRef.current?.files?.[0] || !selected) return;
    setAnalyzing(true); setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", fileRef.current.files[0]);
      fd.append("model", selected);
      fd.append("prompt", "Describe this image in detail.");
      let r = await fetch("/api/vision/analyze", { method: "POST", headers: { ...getRobotAuthHeaders() }, body: fd, credentials: "include" });
      if (r.status === 401) { const ok = await requestRobotAuth("unauthorized"); if (ok) r = await fetch("/api/vision/analyze", { method: "POST", headers: { ...getRobotAuthHeaders() }, body: fd, credentials: "include" }); }
      const data = await r.json() as AnalyzeResponse;
      if (data.success) setResult(data.description);
      else throw new Error(data.error || "Analysis failed");
    } catch (e) { notify({ kind: "error", title: "Error", message: String(e), ttlMs: 5000 }); }
    finally { setAnalyzing(false); }
  };

  return (
    <div className="flex h-full flex-col gap-5 sm:gap-12 md:flex-row">
      {/* Left: Input */}
      <div className="flex w-full flex-col gap-6 sm:gap-8 md:w-5/12">
        <div>
          <label className="mb-3 block text-xs font-semibold tracking-[0.2em] uppercase text-[var(--ts-muted)]">Model Selection</label>
          <select title="Select Target Model" value={selected} onChange={e => setSelected(e.target.value)} className="ts-select focus:outline-none">
            <option value="" disabled>— Select Target —</option>
            {models.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        <div className="ts-surface-card group relative flex min-h-[190px] flex-1 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-[1.5rem] border border-dashed border-[color:var(--ts-border-strong)] bg-[color:var(--ts-surface-bg)] transition-colors hover:border-[var(--ts-accent)] sm:min-h-[300px] sm:rounded-[1.75rem]">
          <input title="Image Upload" ref={fileRef} type="file" accept="image/*" onChange={handleFile}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" />
          {previewUrl ? (
            <img src={previewUrl} className="absolute inset-0 w-full h-full object-contain filter grayscale hover:grayscale-0 transition-all duration-700" alt="Preview" />
          ) : (
            <div className="text-center font-mono pointer-events-none">
              <Camera className="mx-auto mb-4 h-9 w-9 text-[var(--ts-muted)] transition-colors stroke-[1.35] group-hover:text-[var(--ts-text)]" />
              <div className="text-xs font-semibold tracking-widest uppercase text-[var(--ts-text)]">Drop Visual Feed</div>
            </div>
          )}
        </div>

        <button disabled={!previewUrl || !selected || analyzing} onClick={analyze}
          className="ts-btn ts-btn-ghost h-12 border-[color:var(--ts-border-strong)] bg-[color:var(--ts-surface-bg)] text-[var(--ts-text)] hover:bg-[color:var(--ts-surface-bg-strong)] uppercase tracking-[0.18em] font-semibold disabled:opacity-30 sm:h-14 sm:tracking-[0.2em]"
        >
          {analyzing ? "Processing Frame..." : "Execute Scan"}
        </button>
        {vlmUnavailable ? (
          <div className="text-xs uppercase tracking-[0.16em] text-amber-500">
            Vision service unavailable on host.
          </div>
        ) : null}
      </div>

      {/* Right: Output */}
      <div className="flex w-full flex-col md:w-7/12">
        <label className="mb-3 block text-xs font-semibold tracking-[0.2em] uppercase text-[var(--ts-muted)]">Analysis Log</label>
        <div className="ts-surface-panel min-h-[190px] flex-1 overflow-auto rounded-[1.5rem] p-4 font-mono text-sm leading-relaxed text-[var(--ts-text)] sm:min-h-[300px] sm:rounded-[1.75rem] sm:p-6 sm:text-base">
          {result ? (
            <p className="whitespace-pre-wrap">{result}</p>
          ) : (
            <div className="flex h-full items-center justify-center text-[var(--ts-muted)]">
              <span className="text-xs font-semibold tracking-[0.4em] uppercase">Awaiting Feed</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ════════════════ VOICE / CHAT ════════════════ */

function VoiceTest() {
  const { health } = useHostRuntime();
  const [messages, setMessages] = useState<{ role: "user" | "robot"; text: string; ts: number }[]>([]);
  const [input, setInput] = useState("");
  const [lang, setLang] = useState<"en" | "ar">("en");
  const [processing, setProcessing] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const stt = useSpeechRecognition({ lang: lang === "ar" ? "ar-EG" : "en-US", wakeWordEnabled: false });
  const llmUnavailable = health?.services?.llm && health.services.llm.ready === false;

  useEffect(() => { if (stt.text) setInput(lang === "ar" ? normalizeArabic(stt.text) : stt.text); }, [stt.text, lang]);

  const toggleListening = () => { if (stt.listening) stt.stop(); else stt.start(); };

  const sendMessage = async () => {
    if (llmUnavailable) {
      setMessages(prev => [...prev, { role: "robot", text: "Host LLM service is unavailable right now.", ts: Date.now() }]);
      return;
    }
    if (!input.trim()) return;
    const userMsg = lang === "ar" ? normalizeArabic(input) : input;
    const sanitized = userMsg.replace(/[<>{}]/g, "");
    const detectedLang = /[\u0600-\u06FF]/.test(sanitized) ? "ar" : "en";
    if (stt.listening) stt.stop();
    setMessages(prev => [...prev, { role: "user", text: sanitized, ts: Date.now() }]);
    setInput(""); stt.reset(); setProcessing(true);
    const effectiveLang = lang === "ar" ? "ar" : detectedLang;

    try {
      const body = {
        provider: "ollama", model: "", inputText: sanitized, stream: true,
        systemPrompt: effectiveLang === "ar"
          ? `أنت روبوت ذكي. رد بالعامية المصرية وبشكل طبيعي ومختصر.`
          : 'You are an intelligent robot. Answer concisely in natural English.'
      };
      let r = await fetch("/api/llm/generate", { method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...getRobotAuthHeaders() }, body: JSON.stringify(body), credentials: "include" });
      if (r.status === 401) { const ok = await requestRobotAuth("unauthorized"); if (ok) r = await fetch("/api/llm/generate", { method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...getRobotAuthHeaders() }, body: JSON.stringify(body), credentials: "include" }); }
      if (!r.ok) { const t = await r.text().catch(() => ""); throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`); }
      if (!r.body) throw new Error("No stream from server.");

      let textToSpeak = "";
      const fullText = await parseSSEStream(r.body, {
        onToken: () => {},
        onDone: (result) => {
          const action = result.action as { kind?: string; payload?: { text?: string } } | null;
          if (action?.kind === "say" && action.payload?.text) textToSpeak = action.payload.text;
        },
        onError: (error) => { throw new Error(error); },
      });

      if (!textToSpeak) { try { const parsed = JSON.parse(fullText); if (parsed.payload?.text) textToSpeak = parsed.payload.text; else textToSpeak = fullText; } catch { textToSpeak = fullText; } }
      setMessages(prev => [...prev, { role: "robot", text: textToSpeak, ts: Date.now() }]);

      // TTS Playback logic omitted here for brevity (identical to previous)
    } catch (e) { setMessages(prev => [...prev, { role: "robot", text: `Error: ${String(e)}`, ts: Date.now() }]); }
    finally { setProcessing(false); }
  };

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  return (
    <div className="flex h-full flex-col gap-8 sm:gap-12 md:flex-row">
      {/* Settings / Voice Output */}
      <div className="flex w-full flex-col gap-8 sm:gap-10 md:w-4/12">
        <div>
          <label className="mb-3 block text-xs font-semibold tracking-[0.2em] uppercase text-[var(--ts-muted)]">Transmission Lang</label>
          <div className="ts-surface-card flex rounded-[1.25rem] p-1">
            <button onClick={() => setLang("ar")} className={`flex-1 rounded-[0.95rem] py-3 text-sm font-semibold tracking-widest uppercase transition-colors ${lang === "ar" ? "bg-[var(--ts-accent)] text-white" : "text-[var(--ts-muted)] hover:text-[var(--ts-text)]"}`}>AR</button>
            <button onClick={() => setLang("en")} className={`flex-1 rounded-[0.95rem] py-3 text-sm font-semibold tracking-widest uppercase transition-colors ${lang === "en" ? "bg-[var(--ts-accent)] text-white" : "text-[var(--ts-muted)] hover:text-[var(--ts-text)]"}`}>EN</button>
          </div>
        </div>

        <div className="ts-surface-card flex items-center justify-between rounded-[1.5rem] p-6">
          <div>
            <div className="mb-1 text-xs font-semibold tracking-widest uppercase text-[var(--ts-text)]">Mic Input</div>
            <div className={`text-[10px] uppercase font-mono tracking-widest ${stt.supported ? "text-green-500" : "text-red-500"}`}>
              {stt.supported ? (stt.listening ? "RECORDING..." : "STANDBY") : "OFFLINE"}
            </div>
          </div>
          <Mic className={`h-8 w-8 stroke-[1.2] ${stt.listening ? "text-red-500 animate-pulse" : "text-[var(--ts-muted)]"}`} />
        </div>
      </div>

      {/* Terminal View */}
      <div className="relative flex w-full flex-col md:w-8/12">
        <label className="mb-3 hidden text-xs font-semibold tracking-[0.2em] uppercase text-[var(--ts-muted)] md:block">Active COMMS</label>
        
        <div className="ts-surface-panel flex-1 space-y-4 overflow-auto rounded-[1.75rem] p-4 sm:space-y-6 sm:p-6">
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center text-[var(--ts-muted)]">
              <span className="text-xs font-semibold tracking-[0.4em] uppercase">No Record</span>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex max-w-[85%] ${m.role === "user" ? "ml-auto" : "mr-auto"}`}>
              <div className={`rounded-[1.35rem] px-6 py-4 text-sm md:text-base ${m.role === "user" ? "border border-[color:var(--ts-border-strong)] bg-[color:var(--ts-surface-bg)] text-[var(--ts-text)]" : "ts-surface-card text-[var(--ts-text)]"}`}>
                <div className={`mb-2 text-[9px] font-mono tracking-widest uppercase ${m.role === "user" ? "text-[var(--ts-muted)]" : "text-blue-500"}`}>
                  {m.role === "user" ? "Operator" : "System"}
                </div>
                {m.text}
              </div>
            </div>
          ))}
          {processing && (
            <div className="ts-surface-card flex w-64 max-w-[85%] rounded-[1.35rem] px-6 py-4">
              <div className="flex gap-2">
                 <div className="h-1.5 w-1.5 animate-pulse bg-[var(--ts-muted)] delay-150" />
                 <div className="h-1.5 w-1.5 animate-pulse bg-[var(--ts-muted)] delay-300" />
                 <div className="h-1.5 w-1.5 animate-pulse bg-[var(--ts-muted)] delay-500" />
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input Bar */}
        <div className="mt-6 flex gap-3 sm:mt-8 sm:gap-4">
          <button onClick={toggleListening} disabled={processing || !stt.supported}
            className={`flex h-12 w-12 flex-none items-center justify-center rounded-[1rem] border transition-colors sm:h-14 sm:w-14
              ${stt.listening ? "border-red-500 text-red-500 bg-red-500/10" : "border-[color:var(--ts-border-strong)] bg-[color:var(--ts-surface-bg)] text-[var(--ts-muted)] hover:text-[var(--ts-text)]"}`}
          >
            {stt.listening ? <StopCircle className="h-5 w-5 stroke-1" /> : <Mic className="h-5 w-5 stroke-1" />}
          </button>
          
          <input
            value={input}
            onKeyDown={e => e.key === "Enter" && void sendMessage()}
            placeholder={lang === "ar" ? "أمر النظام..." : "Command System..."}
            className="ts-input flex-1 rounded-[1rem] px-4 text-sm font-medium sm:text-base" 
            dir={lang === "ar" ? "rtl" : "ltr"}
            onChange={e => { const v = lang === "ar" ? normalizeArabic(e.target.value) : e.target.value; setInput(v); }}
          />

          <button title="Send Command" onClick={() => void sendMessage()} disabled={!input.trim() || processing}
            className="flex h-12 w-12 flex-none items-center justify-center rounded-[1rem] border border-[color:var(--ts-border-strong)] bg-[color:var(--ts-surface-bg)] text-[var(--ts-text)] transition-all hover:bg-[color:var(--ts-surface-bg-strong)] disabled:opacity-30 sm:h-14 sm:w-14"
          >
            <CornerDownRight className="h-5 w-5 stroke-1" />
          </button>
        </div>
        {llmUnavailable ? (
          <div className="mt-3 text-xs uppercase tracking-[0.16em] text-amber-500">
            LLM service unavailable on host.
          </div>
        ) : null}
      </div>
    </div>
  );
}
