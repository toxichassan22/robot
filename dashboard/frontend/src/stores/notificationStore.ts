import { create } from "zustand";

export type NotificationKind = "success" | "error" | "warning" | "info";

export type Notification = {
  id: string;
  kind: NotificationKind;
  title: string;
  message?: string;
  details?: string;
  createdAtMs: number;
  ttlMs: number;
};

export type NotificationState = {
  items: Notification[];
  push: (n: Omit<Notification, "id" | "createdAtMs">) => string;
  remove: (id: string) => void;
  clear: () => void;
};

function id(): string {
  const a = Math.random().toString(16).slice(2);
  const b = Date.now().toString(16);
  return `${b}-${a}`;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  items: [],
  push: (n) => {
    const newId = id();
    const item: Notification = {
      id: newId,
      kind: n.kind,
      title: String(n.title || "").trim() || "تنبيه",
      message: n.message ? String(n.message) : undefined,
      details: n.details ? String(n.details) : undefined,
      createdAtMs: Date.now(),
      ttlMs: typeof n.ttlMs === "number" ? Math.max(0, Math.floor(n.ttlMs)) : 5000,
    };
    set((s) => ({ items: [item, ...s.items].slice(0, 10) }));
    if (item.ttlMs > 0) {
      setTimeout(() => {
        try {
          useNotificationStore.getState().remove(newId);
        } catch {
          return;
        }
      }, item.ttlMs);
    }
    return newId;
  },
  remove: (idToRemove) => set((s) => ({ items: s.items.filter((x) => x.id !== idToRemove) })),
  clear: () => set({ items: [] }),
}));

