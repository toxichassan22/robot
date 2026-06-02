export type ChestActivityPhase = 
  | "idle"
  | "listening"
  | "thinking"
  | "searching"
  | "reading"
  | "analyzing"
  | "acting"
  | "speaking"
  | "success"
  | "error";

export type ChestActivitySource = 
  | "runtime"
  | "planner"
  | "debate"
  | "browser"
  | "vision"
  | "tts"
  | "safety";

export type ChestActivityEvent = {
  id: string;
  tsMs: number;
  phase: ChestActivityPhase;
  source: ChestActivitySource;
  title: string;
  detail?: string;
  progress?: number;
  severity?: "info" | "warning" | "error";
  emotion?: "idle" | "listening" | "thinking" | "searching" | "analyzing" | "speaking" | "success" | "error";
  artifacts?: {
    browserLive?: boolean;
    cameraStream?: string;
    imageUrl?: string;
  };
  analysis?: {
    nodes?: Array<{ id: string; label: string; kind: "input" | "tool" | "source" | "decision" | "result" }>;
    edges?: Array<{ from: string; to: string }>;
  };
  action?: {
    kind: string;
    payload: Record<string, any>;
  };
};
