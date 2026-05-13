import { useEffect, useMemo, useRef, useState } from "react";

type SpeechRecognitionType = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((ev: unknown) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionType;

function normalizeSpeech(text: string): string {
  return text.trim().toLowerCase().split(/\s+/g).filter(Boolean).join(" ");
}

function containsWakeWord(text: string, wakeWord: string): boolean {
  const normalizedWakeWord = normalizeSpeech(wakeWord);
  if (!normalizedWakeWord) return true;
  return normalizeSpeech(text).includes(normalizedWakeWord);
}

function removeWakeWord(text: string, wakeWord: string): string {
  const normalizedWakeWord = normalizeSpeech(wakeWord);
  if (!normalizedWakeWord) return text.trim();
  return normalizeSpeech(text).replace(normalizedWakeWord, "").trim();
}

function getCtor(): SpeechRecognitionConstructor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

type SpeechRecognitionOpts = { lang?: string; wakeWordEnabled?: boolean; wakeWord?: string; sleepTimeoutMs?: number };

export function useSpeechRecognition(opts?: SpeechRecognitionOpts) {
  const [supported] = useState(() => Boolean(getCtor()));
  const [listening, setListening] = useState(false);
  const [interimText, setInterimText] = useState("");
  const [finalText, setFinalText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<SpeechRecognitionType | null>(null);
  const shouldListenRef = useRef(false);
  const restartTimerRef = useRef<number | null>(null);
  const restartRecognitionRef = useRef<((delayMs?: number) => void) | null>(null);

  const lang = opts?.lang || "ar-EG";
  const wakeWordEnabled = Boolean(opts?.wakeWordEnabled);
  const wakeWord = String(opts?.wakeWord || "").trim();
  const sleepTimeoutMs = Math.max(1000, Number(opts?.sleepTimeoutMs || 20_000));
  const [wakeAwake, setWakeAwake] = useState(false);
  const lastActiveMsRef = useRef(0);
  const wakeAwakeRef = useRef(wakeAwake);
  const wakeConfigRef = useRef({ enabled: wakeWordEnabled, word: wakeWord });

  useEffect(() => {
    wakeAwakeRef.current = wakeAwake;
  }, [wakeAwake]);

  useEffect(() => {
    wakeConfigRef.current = { enabled: wakeWordEnabled, word: wakeWord };
  }, [wakeWord, wakeWordEnabled]);

  useEffect(() => {
    if (!supported) return;
    const Ctor = getCtor();
    if (!Ctor) return;
    const rec: SpeechRecognitionType = new Ctor();
    const clearRestartTimer = () => {
      if (restartTimerRef.current != null) {
        window.clearTimeout(restartTimerRef.current);
        restartTimerRef.current = null;
      }
    };
    const scheduleRestart = (delayMs = 220) => {
      clearRestartTimer();
      if (!shouldListenRef.current) return;
      restartTimerRef.current = window.setTimeout(() => {
        restartTimerRef.current = null;
        if (!shouldListenRef.current || !recRef.current) return;
        try {
          recRef.current.lang = lang;
          recRef.current.start();
          setListening(true);
        } catch {
          scheduleRestart(700);
        }
      }, delayMs);
    };
    restartRecognitionRef.current = scheduleRestart;
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = lang;
    rec.onresult = (ev) => {
      const e = ev as {
        resultIndex?: number;
        results?: ArrayLike<{ isFinal: boolean; 0?: { transcript?: unknown } }>;
      };
      const results = e.results;
      if (!results || typeof e.resultIndex !== "number") return;
      let interim = "";
      let final = "";
      for (let i = e.resultIndex; i < results.length; i++) {
        const r = results[i];
        const txt = String(r?.[0]?.transcript || "");
        if (r.isFinal) final += txt;
        else interim += txt;
      }
      if (interim) setInterimText(interim.trim());
      if (final) {
        const chunk = final.trim();
        if (!chunk) return;
        const { enabled, word } = wakeConfigRef.current;
        if (!enabled) {
          setFinalText((p) => (p ? (p + " " + chunk).trim() : chunk));
          setInterimText("");
          return;
        }

        const now = Date.now();
        if (wakeAwakeRef.current) {
          lastActiveMsRef.current = now;
          setFinalText((p) => (p ? (p + " " + chunk).trim() : chunk));
          setInterimText("");
          return;
        }

        if (containsWakeWord(chunk, word)) {
          lastActiveMsRef.current = now;
          wakeAwakeRef.current = true;
          setWakeAwake(true);
          const cleaned = removeWakeWord(chunk, word);
          if (cleaned) setFinalText((p) => (p ? (p + " " + cleaned).trim() : cleaned));
          setInterimText("");
        } else {
          setInterimText(chunk);
        }
      }
    };
    rec.onerror = (ev) => {
      const e = ev as { error?: unknown; message?: unknown };
      const code = String(e?.error || e?.message || "speech_error");
      const retryable = code === "aborted" || code === "no-speech" || code === "network";
      if (!retryable) {
        setError(code);
      }
      setListening(false);
      if (retryable && shouldListenRef.current) {
        scheduleRestart(code === "no-speech" ? 120 : 400);
      }
    };
    rec.onend = () => {
      setListening(false);
      if (shouldListenRef.current) {
        scheduleRestart(180);
      }
    };
    recRef.current = rec;
    return () => {
      shouldListenRef.current = false;
      restartRecognitionRef.current = null;
      clearRestartTimer();
      try {
        rec.onresult = null;
        rec.onerror = null;
        rec.onend = null;
        rec.stop();
      } catch (error) {
        void error;
      }
    };
  }, [supported, lang]);

  useEffect(() => {
    if (!wakeWordEnabled) {
      setWakeAwake(false);
      return;
    }
    const t = setInterval(() => {
      if (!wakeAwake) return;
      const last = lastActiveMsRef.current;
      if (!last) return;
      if (Date.now() - last >= sleepTimeoutMs) setWakeAwake(false);
    }, 500);
    return () => clearInterval(t);
  }, [sleepTimeoutMs, wakeAwake, wakeWordEnabled]);

  const actions = useMemo(() => {
    return {
      start: () => {
        if (!recRef.current) return;
        shouldListenRef.current = true;
        if (restartTimerRef.current != null) {
          window.clearTimeout(restartTimerRef.current);
          restartTimerRef.current = null;
        }
        setError(null);
        setListening(true);
        if (wakeWordEnabled) {
          wakeAwakeRef.current = false;
          setWakeAwake(false);
          lastActiveMsRef.current = 0;
        }
        recRef.current.lang = lang;
        try {
          recRef.current.start();
        } catch {
          restartRecognitionRef.current?.(300);
        }
      },
      stop: () => {
        if (!recRef.current) return;
        shouldListenRef.current = false;
        if (restartTimerRef.current != null) {
          window.clearTimeout(restartTimerRef.current);
          restartTimerRef.current = null;
        }
        try {
          recRef.current.stop();
        } finally {
          setListening(false);
        }
      },
      reset: () => {
        setFinalText("");
        setInterimText("");
        setError(null);
        shouldListenRef.current = false;
        if (restartTimerRef.current != null) {
          window.clearTimeout(restartTimerRef.current);
          restartTimerRef.current = null;
        }
        if (wakeWordEnabled) {
          wakeAwakeRef.current = false;
          setWakeAwake(false);
          lastActiveMsRef.current = 0;
        }
      },
      setFinalText: (t: string) => setFinalText(t),
    };
  }, [lang, wakeWordEnabled]);

  const text = (finalText + (interimText ? " " + interimText : "")).trim();
  const wakeStatus = !wakeWordEnabled ? null : !listening ? "Sleeping" : wakeAwake ? "Active" : "Listening";

  return { supported, listening, text, finalText, interimText, error, wakeStatus, ...actions };
}
