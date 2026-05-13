import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Template = { id: string; name: string; text: string };

export type TemplatesState = {
  templates: Template[];
  add: (t: { name: string; text: string }) => void;
  remove: (id: string) => void;
  update: (id: string, patch: Partial<Omit<Template, "id">>) => void;
};

function id(): string {
  const a = Math.random().toString(16).slice(2);
  const b = Date.now().toString(16);
  return `${b}-${a}`;
}

const defaults: Template[] = [
  { id: "t-fan-on", name: "شغل المروحة", text: "شغل المروحة" },
  { id: "t-light-off", name: "اطفي النور", text: "اطفي النور" },
  { id: "t-sleep", name: "وضع النوم", text: "نام" },
];

export const useTemplatesStore = create<TemplatesState>()(
  persist(
    (set) => ({
      templates: defaults,
      add: (t) =>
        set((s) => ({
          templates: [{ id: id(), name: String(t.name || "").trim() || "بدون اسم", text: String(t.text || "").trim() }, ...s.templates].slice(
            0,
            50,
          ),
        })),
      remove: (templateId) => set((s) => ({ templates: s.templates.filter((x) => x.id !== templateId) })),
      update: (templateId, patch) =>
        set((s) => ({
          templates: s.templates.map((x) =>
            x.id !== templateId
              ? x
              : {
                  ...x,
                  name: patch.name != null ? String(patch.name).trim() : x.name,
                  text: patch.text != null ? String(patch.text).trim() : x.text,
                },
          ),
        })),
    }),
    { name: "local-robot-tester:templates", version: 1 },
  ),
);

