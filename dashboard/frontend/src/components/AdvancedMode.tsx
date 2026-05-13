import { Card } from "./Card";
import { Activity, Cpu, Database, Terminal } from "lucide-react";

export function AdvancedMode(props: {
  enabled: boolean;
  onToggle: () => void;
  systemPrompt: string;
  onSystemPromptChange: (v: string) => void;
  meta: Record<string, unknown> | null;
  raw: unknown;
}) {
  return (
    <Card
      title="وضع الاختبار المتقدم"
      right={
        <label className="relative inline-flex cursor-pointer items-center">
          <input type="checkbox" className="peer sr-only" checked={props.enabled} onChange={props.onToggle} />
          <div className="h-6 w-11 rounded-full bg-white/10 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary/50 after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-white after:transition-all after:content-[''] peer-checked:bg-primary peer-checked:after:translate-x-full"></div>
          <span className="mr-2 text-xs font-medium text-white">{props.enabled ? "مفعل" : "غير مفعل"}</span>
        </label>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Info icon={<Activity className="h-4 w-4 text-emerald-400" />} label="Response Time" value={props.meta && typeof props.meta.durationMs === "number" ? `${props.meta.durationMs}ms` : "—"} />
          <Info icon={<Cpu className="h-4 w-4 text-blue-400" />} label="Tokens" value={props.meta && typeof props.meta.tokens === "number" ? String(props.meta.tokens) : "—"} />
          <Info icon={<Database className="h-4 w-4 text-amber-400" />} label="Memory" value="N/A" />
        </div>

        <div>
          <div className="flex items-center gap-2 mb-2">
            <Terminal className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs font-medium text-white">System Prompt</span>
          </div>
          <textarea
            disabled={!props.enabled}
            value={props.systemPrompt}
            onChange={(e) => props.onSystemPromptChange(e.target.value)}
            className="min-h-24 w-full resize-none rounded-xl border border-white/10 bg-black/20 p-3 text-sm outline-none focus:border-primary/50 disabled:opacity-50 font-mono transition-all"
            placeholder="اكتب System Prompt مخصص..."
          />
        </div>

        {props.enabled && (
          <div className="animate-fade-in">
            <div className="flex items-center gap-2 mb-2">
              <Terminal className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-medium text-white">Raw JSON Response</span>
            </div>
            <pre className="max-h-64 overflow-auto rounded-xl border border-white/10 bg-black/30 p-3 text-[10px] font-mono text-blue-200 custom-scrollbar">
              {props.raw ? JSON.stringify(props.raw, null, 2) : "—"}
            </pre>
          </div>
        )}
      </div>
    </Card>
  );
}

function Info(props: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/5 bg-white/5 p-3 flex items-center justify-between">
      <div className="flex items-center gap-2">
        {props.icon}
        <div className="text-xs text-muted-foreground">{props.label}</div>
      </div>
      <div className="text-sm font-bold font-mono text-white">{props.value}</div>
    </div>
  );
}
