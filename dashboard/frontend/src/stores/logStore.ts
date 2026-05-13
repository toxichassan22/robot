import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ActionCommand, Provider } from "../utils/api";
import type { ExtractedCommand } from "../utils/commandExtractor";

export type LogEntry = {
  id: string;
  ts: number;
  provider: Provider;
  model: string;
  heardText: string;
  localCommands: ExtractedCommand[];
  llmOutputText: string;
  llmAction: ActionCommand | null;
  error: string | null;
  durationMs?: number | null;
  tokens?: number | null;
};

export type LogState = {
  entries: LogEntry[];
  add: (e: Omit<LogEntry, "id">) => void;
  clear: () => void;
};

function id(): string {
  const a = Math.random().toString(16).slice(2);
  const b = Date.now().toString(16);
  return `${b}-${a}`;
}

export const useLogStore = create<LogState>()(
  persist(
    (set) => ({
      entries: [],
      add: (e) => set((s) => ({ entries: [{ ...e, id: id() }, ...s.entries].slice(0, 100) })),
      clear: () => set({ entries: [] }),
    }),
    { name: "local-robot-tester:logs", version: 1 },
  ),
);
