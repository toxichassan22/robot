import { useCallback, useEffect, useMemo, useRef, useState } from "react";

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

type VoiceLoadError = "no_voices" | "load_failed";
type VoiceOption = { voiceURI: string; name: string; lang: string; label: string; localService: boolean | undefined; default: boolean | undefined };

function readCachedVoiceOptions(): VoiceOption[] {
  try {
    const raw = sessionStorage.getItem("local-robot-tester:tts:voices");
    if (!raw) return [];
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data)) return [];
    return data
      .map((x) => {
        if (!x || typeof x !== "object") return null;
        const o = x as Record<string, unknown>;
        const voiceURI = typeof o.voiceURI === "string" ? o.voiceURI : "";
        const name = typeof o.name === "string" ? o.name : "";
        const lang = typeof o.lang === "string" ? o.lang : "";
        const label = typeof o.label === "string" ? o.label : "";
        const localService = typeof o.localService === "boolean" ? o.localService : undefined;
        const d = typeof o.default === "boolean" ? o.default : undefined;
        if (!voiceURI || !label) return null;
        return { voiceURI, name, lang, label, localService, default: d } satisfies VoiceOption;
      })
      .filter((x): x is VoiceOption => Boolean(x))
      .slice(0, 500);
  } catch {
    return [];
  }
}

function writeCachedVoiceOptions(options: VoiceOption[]) {
  try {
    sessionStorage.setItem("local-robot-tester:tts:voices", JSON.stringify(options.slice(0, 500)));
  } catch {
    return;
  }
}

function getVoicesSafe(): SpeechSynthesisVoice[] {
  try {
    return window.speechSynthesis.getVoices();
  } catch {
    return [];
  }
}

export function pickBestVoice(args: {
  voices: SpeechSynthesisVoice[];
  voiceURI?: string;
  lang?: string;
  gender?: "male" | "female";
}): SpeechSynthesisVoice | null {
  const voices = args.voices;
  if (!voices.length) return null;

  if (args.voiceURI) {
    const exact = voices.find((x) => x.voiceURI === args.voiceURI);
    if (exact) return exact;
  }

  const lang = (args.lang || "").trim();
  const shortLang = lang ? lang.split("-")[0] : "";

  const langCandidatesRaw = lang
    ? voices.filter((v) => v.lang === lang || (shortLang ? v.lang.startsWith(shortLang) : false))
    : voices;

  const langCandidates = [...langCandidatesRaw].sort((a, b) => {
    const al = a.localService ? 1 : 0;
    const bl = b.localService ? 1 : 0;
    if (al !== bl) return bl - al;
    const ad = a.default ? 1 : 0;
    const bd = b.default ? 1 : 0;
    if (ad !== bd) return bd - ad;
    return `${a.name} ${a.voiceURI}`.localeCompare(`${b.name} ${b.voiceURI}`);
  });

  if (args.gender) {
    const prefers =
      args.gender === "female"
        ? ["female", "woman", "girl", "zira", "susan", "sara", "amy", "emma", "olivia", "linda", "eva", "hanne"]
        : ["male", "man", "boy", "david", "mark", "john", "daniel", "alex", "george", "jorge"];

    const byName = langCandidates.find((v) => prefers.some((k) => `${v.name} ${v.voiceURI}`.toLowerCase().includes(k)));
    if (byName) return byName;
  }

  const defaultVoice = langCandidates.find((v) => v.default);
  if (defaultVoice) return defaultVoice;

  return langCandidates[0] || voices[0] || null;
}

export function useTts() {
  const [supported] = useState(() => "speechSynthesis" in window);
  const [speaking, setSpeaking] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [cachedVoiceOptions, setCachedVoiceOptions] = useState<VoiceOption[]>(() => readCachedVoiceOptions());
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [voicesError, setVoicesError] = useState<VoiceLoadError | null>(null);
  const [voicesLoadedOnce, setVoicesLoadedOnce] = useState(false);
  const loadSeqRef = useRef(0);

  useEffect(() => {
    if (!supported) return;
    const seq = ++loadSeqRef.current;

    const applyVoices = (v: SpeechSynthesisVoice[]) => {
      if (loadSeqRef.current !== seq) return;
      setVoices(v);
      setVoicesLoadedOnce(true);
      if (v.length) {
        setVoicesLoading(false);
        setVoicesError(null);
      }
    };

    const loadOnce = () => applyVoices(getVoicesSafe());

    const prev = window.speechSynthesis.onvoiceschanged;
    const handler = (ev: Event) => {
      loadOnce();
      if (typeof prev === "function") {
        try {
          prev.call(window.speechSynthesis, ev);
        } catch {
          return;
        }
      }
    };
    window.speechSynthesis.onvoiceschanged = handler;

    const loadWithRetry = async () => {
      setVoicesLoading(true);
      setVoicesError(null);

      const delaysMs = [0, 450, 1200];
      for (let i = 0; i < delaysMs.length; i++) {
        if (loadSeqRef.current !== seq) return;
        if (delaysMs[i]) await sleep(delaysMs[i]);
        if (loadSeqRef.current !== seq) return;
        const v = getVoicesSafe();
        if (v.length) {
          applyVoices(v);
          return;
        }
      }

      if (loadSeqRef.current !== seq) return;
      const final = getVoicesSafe();
      setVoices(final);
      setVoicesLoadedOnce(true);
      setVoicesLoading(false);
      setVoicesError(final.length ? null : "no_voices");
    };

    void loadWithRetry();
    return () => {
      if (window.speechSynthesis.onvoiceschanged === handler) window.speechSynthesis.onvoiceschanged = prev;
    };
  }, [supported]);

  const reloadVoices = useCallback(async () => {
    if (!supported) return;
    const seq = ++loadSeqRef.current;
    setVoicesLoading(true);
    setVoicesError(null);

    const delaysMs = [0, 600, 1500];
    for (let i = 0; i < delaysMs.length; i++) {
      if (loadSeqRef.current !== seq) return;
      if (delaysMs[i]) await sleep(delaysMs[i]);
      if (loadSeqRef.current !== seq) return;
      const v = getVoicesSafe();
      setVoices(v);
      setVoicesLoadedOnce(true);
      if (v.length) {
        setVoicesLoading(false);
        setVoicesError(null);
        return;
      }
    }

    if (loadSeqRef.current !== seq) return;
    setVoicesLoading(false);
    setVoicesError(getVoicesSafe().length ? null : "no_voices");
  }, [supported]);

  const speak = useCallback(
    (args: { text: string; voiceURI?: string; lang?: string; rate?: number; gender?: "male" | "female" }) => {
      if (!supported) return;
      const text = (args.text || "").trim();
      if (!text) return;
      window.speechSynthesis.cancel();

      const u = new SpeechSynthesisUtterance(text);
      if (args.lang) u.lang = args.lang;
      if (typeof args.rate === "number") u.rate = args.rate;

      const availableVoices = getVoicesSafe();

      const voice = pickBestVoice({
        voices: availableVoices,
        voiceURI: args.voiceURI,
        lang: args.lang,
        gender: args.gender,
      });
      if (voice) u.voice = voice;
      if (!voice && voicesLoadedOnce && !availableVoices.length) {
        setVoicesError("no_voices");
        return;
      }

      u.onstart = () => setSpeaking(true);
      u.onend = () => setSpeaking(false);
      u.onerror = () => setSpeaking(false);
      window.speechSynthesis.speak(u);
    },
    [supported, voicesLoadedOnce],
  );

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  useEffect(() => {
    if (!voices.length) return;
    const opts: VoiceOption[] = voices
      .map((v) => ({
        voiceURI: v.voiceURI,
        name: v.name,
        lang: v.lang,
        localService: v.localService,
        default: v.default,
        label: `${v.name} (${v.lang})${v.localService ? " • local" : ""}${v.default ? " • default" : ""}`,
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
    writeCachedVoiceOptions(opts);
    setCachedVoiceOptions(opts);
  }, [voices]);

  const voiceOptions = useMemo((): VoiceOption[] => {
    if (voices.length) {
      return voices
        .map((v) => ({
          voiceURI: v.voiceURI,
          name: v.name,
          lang: v.lang,
          localService: v.localService,
          default: v.default,
          label: `${v.name} (${v.lang})${v.localService ? " • local" : ""}${v.default ? " • default" : ""}`,
        }))
        .sort((a, b) => a.label.localeCompare(b.label));
    }
    return cachedVoiceOptions;
  }, [cachedVoiceOptions, voices]);

  const voicesAvailable = voiceOptions.length > 0;

  return {
    supported,
    speaking,
    voices: voiceOptions,
    voicesAvailable,
    voicesLoading,
    voicesLoadedOnce,
    voicesError,
    reloadVoices,
    speak,
    stop,
  };
}
