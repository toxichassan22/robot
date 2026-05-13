import { useMemo, useRef, useState } from "react";
import { AppShell } from "../components/AppShell";
import { Badge, Button, Card } from "../components/Card";
import { useLogStore, type LogEntry, type LogState } from "../stores/logStore";
import { Copy, Download, Trash2, ScrollText } from "lucide-react";
import { cn } from "../lib/utils";

export default function Logs() {
  const entries = useLogStore((s: LogState) => s.entries);
  const clear = useLogStore((s: LogState) => s.clear);
  const [selectedId, setSelectedId] = useState<string | null>(entries[0]?.id || null);
  const [compareA, setCompareA] = useState<string | null>(null);
  const [compareB, setCompareB] = useState<string | null>(null);
  const [providerFilter, setProviderFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "success" | "error">("all");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [virtualScrollTop, setVirtualScrollTop] = useState(0);
  const listRef = useRef<HTMLDivElement | null>(null);

  const selected = useMemo(() => entries.find((e) => e.id === selectedId) || null, [entries, selectedId]);
  const providerOptions = useMemo(() => {
    const set = new Set<string>();
    for (const e of entries) set.add(e.provider);
    return ["all", ...Array.from(set)];
  }, [entries]);

  const filtered = useMemo(() => {
    const startMs = startDate ? new Date(`${startDate}T00:00:00`).getTime() : null;
    const endMs = endDate ? new Date(`${endDate}T23:59:59.999`).getTime() : null;
    return entries.filter((e) => {
      if (providerFilter !== "all" && e.provider !== providerFilter) return false;
      if (statusFilter === "success" && e.error) return false;
      if (statusFilter === "error" && !e.error) return false;
      if (startMs != null && e.ts < startMs) return false;
      if (endMs != null && e.ts > endMs) return false;
      return true;
    });
  }, [endDate, entries, providerFilter, startDate, statusFilter]);

  const stats = useMemo(() => {
    const total = filtered.length;
    const success = filtered.filter((e) => !e.error).length;
    const error = total - success;
    const durations = filtered.map((e) => (typeof e.durationMs === "number" ? e.durationMs : null)).filter((x): x is number => x != null);
    const avgDurationMs = durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null;
    const successRate = total ? Math.round((success / total) * 100) : 0;
    return { total, success, error, successRate, avgDurationMs };
  }, [filtered]);

  const selectedA = useMemo(() => (compareA ? entries.find((e) => e.id === compareA) || null : null), [compareA, entries]);
  const selectedB = useMemo(() => (compareB ? entries.find((e) => e.id === compareB) || null : null), [compareB, entries]);

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `robot-tester-logs-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const rowHeight = 84;
  const viewportHeight = 70 * 16;
  const totalHeight = filtered.length * rowHeight;
  const startIndex = Math.max(0, Math.floor(virtualScrollTop / rowHeight) - 5);
  const endIndex = Math.min(filtered.length, startIndex + Math.ceil(viewportHeight / rowHeight) + 10);
  const visible = filtered.slice(startIndex, endIndex);

  return (
    <AppShell title="السجل والتشخيص">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-12">
        <div className="md:col-span-6 space-y-6">
          <Card
            title="سجل الجلسات"
            right={
              <div className="flex items-center gap-2">
                <Button onClick={exportJson} disabled={!entries.length} variant="ghost" className="h-8 w-8 p-0">
                  <Download className="h-4 w-4" />
                </Button>
                <Button variant="danger" onClick={clear} disabled={!entries.length} className="h-8 w-8 p-0 flex items-center justify-center rounded-lg">
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            }
          >
            {entries.length ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <FilterGroup label="من">
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      title="Start date filter"
                      placeholder="yyyy-mm-dd"
                      className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                    />
                  </FilterGroup>
                  <FilterGroup label="إلى">
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      title="End date filter"
                      placeholder="yyyy-mm-dd"
                      className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                    />
                  </FilterGroup>
                  <FilterGroup label="Provider">
                    <select
                      value={providerFilter}
                      onChange={(e) => setProviderFilter(e.target.value)}
                      title="Provider filter"
                      className="w-full bg-transparent text-sm outline-none"
                    >
                      {providerOptions.map((p) => (
                        <option key={p} value={p} className="bg-slate-900 text-white">
                          {p === "all" ? "الكل" : p.toUpperCase()}
                        </option>
                      ))}
                    </select>
                  </FilterGroup>
                  <FilterGroup label="الحالة">
                    <select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value as "all" | "success" | "error")}
                      title="Status filter"
                      className="w-full bg-transparent text-sm outline-none"
                    >
                      <option value="all" className="bg-slate-900">الكل</option>
                      <option value="success" className="bg-slate-900">نجاح</option>
                      <option value="error" className="bg-slate-900">خطأ</option>
                    </select>
                  </FilterGroup>
                </div>

                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <Info label="عدد الجلسات" value={String(stats.total)} />
                  <Info label="نجاح" value={`${stats.success} (${stats.successRate}%)`} />
                  <Info label="فشل" value={String(stats.error)} highlight={stats.error > 0} />
                  <Info label="متوسط الوقت" value={stats.avgDurationMs != null ? `${stats.avgDurationMs}ms` : "—"} />
                </div>

                <div
                  ref={listRef}
                  className="max-h-[600px] overflow-auto pr-2 custom-scrollbar"
                  onScroll={(e) => setVirtualScrollTop((e.target as HTMLDivElement).scrollTop)}
                >
                  <div className="relative" style={{ height: totalHeight }}>
                    <div className="absolute left-0 right-0" style={{ top: startIndex * rowHeight }}>
                      <div className="space-y-2">
                        {visible.map((e) => (
                          <button
                            key={e.id}
                            type="button"
                            onClick={() => setSelectedId(e.id)}
                            className={cn(
                              "w-full rounded-xl border p-4 text-left transition-all duration-200",
                              selectedId === e.id
                                ? "bg-primary/10 border-primary/30 ring-1 ring-primary/30"
                                : "bg-white/5 border-white/5 hover:bg-white/10 hover:border-white/10"
                            )}
                          >
                            <div className="flex items-center justify-between gap-3 mb-2">
                              <div className="text-sm font-semibold text-white">{new Date(e.ts).toLocaleString()}</div>
                              <div className="flex flex-wrap items-center gap-2 justify-end">
                                <Badge>{e.provider.toUpperCase()}</Badge>
                                {e.error ? <Badge tone="error">خطأ</Badge> : <Badge tone="ok">نجاح</Badge>}
                              </div>
                            </div>
                            <div className="flex items-center justify-between gap-2">
                              <div className="line-clamp-1 text-xs text-muted-foreground max-w-[70%]">{e.heardText || "—"}</div>
                              {typeof e.durationMs === "number" ? <span className="text-[10px] text-muted-foreground/60">{e.durationMs}ms</span> : null}
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-8 text-muted-foreground border border-dashed border-white/10 rounded-xl">
                <ScrollText className="h-8 w-8 mb-2 opacity-50" />
                <div className="text-sm">لا يوجد سجل بعد</div>
              </div>
            )}
          </Card>
        </div>

        <div className="md:col-span-6">
          <div className="flex flex-col gap-6 sticky top-6">
            <Card title="تفاصيل الجلسة">
              {selected ? <EntryDetails entry={selected} /> : <EmptyDetails />}
            </Card>

            <Card title="مقارنة جلستين">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <FilterGroup label="الجلسة A">
                  <select
                    value={compareA || ""}
                    onChange={(e) => setCompareA(e.target.value || null)}
                    title="Select session A for comparison"
                    className="w-full bg-transparent text-sm outline-none"
                  >
                    <option value="" className="bg-slate-900">—</option>
                    {filtered.slice(0, 200).map((e) => (
                      <option key={e.id} value={e.id} className="bg-slate-900">
                        {new Date(e.ts).toLocaleString()} • {e.error ? "خطأ" : "نجاح"}
                      </option>
                    ))}
                  </select>
                </FilterGroup>
                <FilterGroup label="الجلسة B">
                  <select
                    value={compareB || ""}
                    onChange={(e) => setCompareB(e.target.value || null)}
                    title="Select session B for comparison"
                    className="w-full bg-transparent text-sm outline-none"
                  >
                    <option value="" className="bg-slate-900">—</option>
                    {filtered.slice(0, 200).map((e) => (
                      <option key={e.id} value={e.id} className="bg-slate-900">
                        {new Date(e.ts).toLocaleString()} • {e.error ? "خطأ" : "نجاح"}
                      </option>
                    ))}
                  </select>
                </FilterGroup>
              </div>

              {selectedA && selectedB ? (
                <div className="mt-4 grid grid-cols-1 gap-4">
                  <CompareBlock title="A: Output" text={selectedA.llmOutputText || "—"} />
                  <CompareBlock title="B: Output" text={selectedB.llmOutputText || "—"} />
                  <div className="grid grid-cols-2 gap-4">
                    <CompareBlock title="A: Action" json={selectedA.llmAction} />
                    <CompareBlock title="B: Action" json={selectedB.llmAction} />
                  </div>
                </div>
              ) : (
                <div className="mt-4 flex items-center justify-center p-6 text-sm text-muted-foreground border border-dashed border-white/10 rounded-xl">
                  اختر جلستين للمقارنة
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function FilterGroup({ label, children }: { label: string, children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/5 bg-white/5 px-3 py-2 transition-colors focus-within:border-primary/50 focus-within:bg-white/10">
      <div className="mb-0.5 text-[10px] text-muted-foreground uppercase tracking-wider">{label}</div>
      {children}
    </div>
  )
}

function EmptyDetails() {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-muted-foreground border border-dashed border-white/10 rounded-xl">
      <div className="text-sm">اختر جلسة لعرض التفاصيل</div>
    </div>
  );
}

function EntryDetails(props: { entry: LogEntry }) {
  const e = props.entry;
  const copy = (txt: string) => navigator.clipboard.writeText(txt).catch(() => undefined);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Info label="Provider" value={e.provider.toUpperCase()} />
        <Info label="Model" value={e.model} />
        <Info label="Duration" value={typeof e.durationMs === "number" ? `${e.durationMs}ms` : "—"} />
        <Info label="Status" value={e.error ? "Error" : "Success"} highlight={!!e.error} />
      </div>

      {e.error ? (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-400">
          <h4 className="font-semibold mb-1">Error Occurred</h4>
          {e.error}
        </div>
      ) : null}

      <Block title="النص المسموع" onCopy={() => copy(e.heardText)}>
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{e.heardText || "—"}</div>
      </Block>

      <Block title="رد الموديل" onCopy={() => copy(e.llmOutputText)}>
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{e.llmOutputText || "—"}</div>
      </Block>

      <div className="grid grid-cols-1 gap-4">
        <Block title="الأوامر (محلية)" onCopy={() => copy(JSON.stringify(e.localCommands, null, 2))}>
          <JsonPreview value={e.localCommands} />
        </Block>

        <Block title="Action" onCopy={() => copy(JSON.stringify(e.llmAction, null, 2))}>
          <JsonPreview value={e.llmAction} />
        </Block>
      </div>
    </div>
  );
}

function Info(props: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={cn("rounded-xl border border-white/5 bg-white/5 p-3", props.highlight ? "border-red-500/20 bg-red-500/5" : "")}>
      <div className="text-[10px] text-muted-foreground uppercase tracking-wider">{props.label}</div>
      <div className={cn("mt-1 text-sm font-semibold", props.highlight ? "text-red-400" : "text-white")}>{props.value || "—"}</div>
    </div>
  );
}

function Block(props: { title: string; onCopy: () => void; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/5 bg-black/20 p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{props.title}</div>
        <Button onClick={props.onCopy} variant="ghost" className="h-6 px-2 text-xs">
          <Copy className="h-3 w-3 mr-1" /> نسخ
        </Button>
      </div>
      <div className="">{props.children}</div>
    </div>
  );
}

function CompareBlock(props: { title: string; text?: string; json?: unknown }) {
  const copy = () => {
    const payload = props.json !== undefined ? JSON.stringify(props.json, null, 2) : props.text || "";
    navigator.clipboard.writeText(payload).catch(() => undefined);
  };
  return (
    <div className="rounded-xl border border-white/5 bg-black/20 p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{props.title}</div>
        <Button onClick={copy} variant="ghost" className="h-6 px-2 text-xs">
          <Copy className="h-3 w-3 mr-1" /> نسخ
        </Button>
      </div>
      <div className="">
        {props.json !== undefined ? (
          <JsonPreview value={props.json} />
        ) : (
          <div className="max-h-56 overflow-auto whitespace-pre-wrap text-sm leading-relaxed text-slate-300 custom-scrollbar">{props.text || "—"}</div>
        )}
      </div>
    </div>
  );
}

function escapeHtml(s: string): string {
  return s.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function highlightJsonString(json: string): string {
  const escaped = escapeHtml(json);
  return escaped
    .replace(/(&quot;)([^&]*?)(&quot;)(\s*:)?/g, (_m, q1, inner, q2, colon) => {
      const cls = colon ? "text-blue-400" : "text-emerald-400";
      const suffix = colon ? `<span class="text-slate-500">:</span>` : "";
      return `<span class="${cls}">${q1}${inner}${q2}</span>${suffix}`;
    })
    .replace(/\b(true|false|null)\b/g, `<span class="text-amber-400">$1</span>`)
    .replace(/\b(-?\d+(?:\.\d+)?)\b/g, `<span class="text-purple-400">$1</span>`);
}

function JsonPreview(props: { value: unknown }) {
  const json = useMemo(() => JSON.stringify(props.value, null, 2), [props.value]);
  const html = useMemo(() => highlightJsonString(json), [json]);
  return (
    <pre
      className="overflow-auto text-xs font-mono bg-black/40 p-3 rounded-lg custom-scrollbar border border-white/5"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
