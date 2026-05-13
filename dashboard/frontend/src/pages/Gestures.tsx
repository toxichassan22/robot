import { useEffect, useMemo, useState } from "react";
import { AppShell } from "../components/AppShell";
import { Button, Card } from "../components/Card";
import { useSettingsStore, type SettingsState } from "../stores/settingsStore";
import { Hand, RefreshCcw, Save } from "lucide-react";
import { cn } from "../lib/utils";

type GestureKey = "rock" | "paper" | "scissors" | "pointing" | "waving" | "thumbs_up" | "thumbs_down";
type GestureConfig = { enabled: boolean; binding: string };

const DEFAULT: Record<GestureKey, GestureConfig> = {
  rock: { enabled: true, binding: "rps" },
  paper: { enabled: true, binding: "rps" },
  scissors: { enabled: true, binding: "rps" },
  pointing: { enabled: true, binding: "follow" },
  waving: { enabled: true, binding: "greet" },
  thumbs_up: { enabled: true, binding: "positive_feedback" },
  thumbs_down: { enabled: true, binding: "negative_feedback" },
};

function normalizeBindings(v: unknown): Record<string, string> {
  if (!v || typeof v !== "object" || Array.isArray(v)) return {};
  const out: Record<string, string> = {};
  for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
    const key = String(k || "").trim().toLowerCase();
    const s = typeof val === "string" ? val.trim() : "";
    if (key && s) out[key] = s;
  }
  return out;
}

function bindingsToCfg(bindings: Record<string, string>): Record<GestureKey, GestureConfig> {
  const out: Record<GestureKey, GestureConfig> = { ...DEFAULT };
  for (const k of Object.keys(DEFAULT) as GestureKey[]) {
    const raw = bindings[k];
    if (typeof raw === "string" && raw.trim()) {
      out[k] = { enabled: true, binding: raw.trim() };
    } else {
      out[k] = { enabled: false, binding: DEFAULT[k].binding };
    }
  }
  return out;
}

function cfgToBindings(cfg: Record<GestureKey, GestureConfig>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of Object.keys(DEFAULT) as GestureKey[]) {
    const v = cfg[k];
    if (!v || typeof v !== "object") continue;
    if (!v.enabled) continue;
    const binding = String(v.binding || "").trim();
    if (!binding) continue;
    out[k] = binding;
  }
  return out;
}

export default function Gestures() {
  const gestureBindings = useSettingsStore((st: SettingsState) => st.gestureBindings);
  const setSettings = useSettingsStore((st: SettingsState) => st.set);
  const [cfg, setCfg] = useState<Record<GestureKey, GestureConfig>>(() => bindingsToCfg(normalizeBindings(gestureBindings)));
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    const storeBindings = normalizeBindings(useSettingsStore.getState().gestureBindings);
    const next = cfgToBindings(cfg);
    const storeStr = JSON.stringify(storeBindings);
    const nextStr = JSON.stringify(next);
    setHasChanges(storeStr !== nextStr);
  }, [cfg]);


  // Sync from store if store changes externally (and we haven't touched it yet? or just force sync?)
  // For now let's keep it simple: initial load is handled by useState initializer.
  // If we want two-way sync it gets complex with dirty states.
  // We'll stick to: Store -> State (on mount) and State -> Store (on save/effect).

  const saveChanges = () => {
    const next = cfgToBindings(cfg);
    setSettings({ gestureBindings: next });
    setHasChanges(false);
  };

  const items = useMemo(() => Object.entries(cfg) as [GestureKey, GestureConfig][], [cfg]);

  return (
    <AppShell title="إيماءات اليد">
      <div className="mx-auto max-w-4xl space-y-6">
        <Card
          title="ربط الإيماءات بالأوامر"
          right={
            hasChanges && (
              <Button onClick={saveChanges} variant="primary" className="animate-fade-in">
                <Save className="h-4 w-4" /> حفظ التغييرات
              </Button>
            )
          }
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {items.map(([k, v]) => (
              <div key={k} className={cn("group rounded-xl border p-4 transition-all duration-300", v.enabled ? "bg-white/5 border-white/10" : "bg-black/20 border-transparent opacity-60")}>
                <div className="flex items-start gap-4">
                  <div className={cn("mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-colors", v.enabled ? "border-primary/20 bg-primary/10 text-primary shadow-[0_0_10px_rgba(59,130,246,0.3)]" : "border-white/5 bg-white/5 text-muted-foreground")}>
                    <Hand className="h-5 w-5" />
                  </div>

                  <div className="flex-1 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="font-semibold capitalize text-white tracking-wide">{k.replace("_", " ")}</div>
                      <label className="relative inline-flex cursor-pointer items-center">
                        <input
                          type="checkbox"
                          className="peer sr-only"
                          title={`Toggle ${k.replace("_", " ")}`}
                          checked={v.enabled}
                          onChange={(e) => {
                            setCfg((s) => ({ ...s, [k]: { ...s[k], enabled: e.target.checked } }));
                          }}
                        />
                        <div className="h-5 w-9 rounded-full bg-white/10 after:absolute after:left-[2px] after:top-[2px] after:h-4 after:w-4 after:rounded-full after:bg-white after:transition-all after:content-[''] peer-checked:bg-primary peer-checked:after:translate-x-full peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary/50"></div>
                      </label>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Action / Command</label>
                      <input
                        value={v.binding}
                        onChange={(e) => setCfg((s) => ({ ...s, [k]: { ...s[k], binding: e.target.value } }))}
                        disabled={!v.enabled}
                        className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50 disabled:cursor-not-allowed disabled:placeholder-transparent transition-all"
                        placeholder={v.enabled ? "e.g. greet" : "Disabled"}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 flex justify-end pt-4 border-t border-white/5">
            <Button
              variant="secondary"
              onClick={() => {
                setCfg(DEFAULT);
              }}
              className="text-muted-foreground hover:text-white"
            >
              <RefreshCcw className="h-4 w-4 ml-2" /> استعادة الافتراضي
            </Button>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
