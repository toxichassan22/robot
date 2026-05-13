import { useMemo } from "react";
import { Copy, X } from "lucide-react";
import { Button } from "./Card";
import { useNotificationStore, type Notification, type NotificationState } from "../stores/notificationStore";

function tone(n: Notification): string {
  if (n.kind === "success") return "border-[#2ECC71]/30 bg-[#2ECC71]/10";
  if (n.kind === "warning") return "border-[#F39C12]/30 bg-[#F39C12]/10";
  if (n.kind === "error") return "border-[#E74C3C]/30 bg-[#E74C3C]/10";
  return "border-white/10 bg-white/5";
}

function titleTone(n: Notification): string {
  if (n.kind === "success") return "text-[#2ECC71]";
  if (n.kind === "warning") return "text-[#F39C12]";
  if (n.kind === "error") return "text-[#E74C3C]";
  return "text-[#EAF0FF]";
}

export function ToastHost() {
  const items = useNotificationStore((s: NotificationState) => s.items);
  const remove = useNotificationStore((s: NotificationState) => s.remove);

  const sorted = useMemo(() => items.slice(0, 10), [items]);

  if (!sorted.length) return null;
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[60] w-[min(92vw,420px)] space-y-2">
      {sorted.map((n) => (
        <div key={n.id} className={`pointer-events-auto rounded-2xl border p-3 shadow-lg ${tone(n)}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className={`text-sm font-semibold ${titleTone(n)}`}>{n.title}</div>
              {n.message ? <div className="mt-1 text-xs text-[#AAB6D3]">{n.message}</div> : null}
            </div>
            <div className="flex items-center gap-2">
              {n.details ? (
                <Button
                  onClick={() => {
                    navigator.clipboard.writeText(n.details || "").catch(() => undefined);
                  }}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              ) : null}
              <Button onClick={() => remove(n.id)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          {n.details ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-[#AAB6D3]">التفاصيل</summary>
              <pre className="mt-2 max-h-40 overflow-auto rounded-xl border border-white/10 bg-black/20 p-2 text-xs text-[#EAF0FF]">
                {n.details}
              </pre>
            </details>
          ) : null}
        </div>
      ))}
    </div>
  );
}

