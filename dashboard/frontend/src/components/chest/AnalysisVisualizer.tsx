import React from "react";
import { ChestActivityEvent } from "../chestTypes";

interface AnalysisVisualizerProps {
  events: ChestActivityEvent[];
}

export function AnalysisVisualizer({ events }: AnalysisVisualizerProps) {
  const latestEvent = events[events.length - 1];
  const activePhase = latestEvent?.phase || "idle";

  // Define static workflow stages for visual RAG/thinking pipelines
  const stages = [
    {
      id: "input",
      label: "دخل المستخدم",
      desc: "ASR / Audio Input",
      phases: ["listening"],
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      ),
    },
    {
      id: "gatekeeper",
      label: "البوابة الذكية",
      desc: "Gatekeeper Awake Check",
      phases: ["thinking"],
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      ),
    },
    {
      id: "debate",
      label: "محرك المناظرة RAG",
      desc: "Web Search & Debate",
      phases: ["searching", "reading"],
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
        </svg>
      ),
    },
    {
      id: "planner",
      label: "مخطط الأفعال",
      desc: "Action LLM Planner",
      phases: ["analyzing"],
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      ),
    },
    {
      id: "actions",
      label: "تنفيذ الأوامر",
      desc: "TTS & Motors Execution",
      phases: ["acting", "speaking"],
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
    },
  ];

  return (
    <div className="flex flex-col bg-slate-900/60 backdrop-blur-md border border-slate-700/50 rounded-xl p-5 shadow-2xl h-full justify-between">
      <div>
        <h3 className="text-slate-300 text-sm font-semibold mb-1 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
          مخطط تدفق المعالجة
        </h3>
        <p className="text-slate-500 text-xs mb-5">تتبع مسار اتخاذ القرار داخل عقل الروبوت في الوقت الحقيقي.</p>
      </div>

      {/* Decision Flow Pipeline */}
      <div className="flex flex-col md:flex-row items-center gap-4 justify-between w-full py-4 relative">
        {stages.map((stage, idx) => {
          const isCurrent = stage.phases.includes(activePhase);
          const isPassed = stages.slice(0, idx).some((s) => s.phases.includes(activePhase));
          
          return (
            <React.Fragment key={stage.id}>
              {/* Connector line for large screens */}
              {idx > 0 && (
                <div className="hidden md:block flex-1 h-[2px] min-w-[20px] transition-colors duration-500 bg-slate-700/50">
                  <div
                    className={`h-full bg-indigo-500 transition-all duration-700 ${
                      isCurrent || isPassed ? "w-full" : "w-0"
                    }`}
                  />
                </div>
              )}

              {/* Node Card */}
              <div
                className={`flex flex-col items-center text-center p-3 rounded-xl border transition-all duration-300 w-full md:w-[150px] relative z-10 ${
                  isCurrent
                    ? "bg-indigo-600/20 border-indigo-500 shadow-lg shadow-indigo-500/20 scale-105"
                    : isPassed
                    ? "bg-emerald-950/20 border-emerald-800/80"
                    : "bg-slate-950/40 border-slate-800/80"
                }`}
              >
                {/* Node Icon */}
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all duration-300 mb-2 ${
                    isCurrent
                      ? "bg-indigo-500 text-white shadow-md shadow-indigo-500/50"
                      : isPassed
                      ? "bg-emerald-800/30 text-emerald-400"
                      : "bg-slate-900 text-slate-500"
                  }`}
                >
                  {stage.icon}
                </div>

                <div className="text-[11px] font-bold text-slate-200">{stage.label}</div>
                <div className="text-[9px] text-slate-500 font-mono mt-0.5">{stage.desc}</div>
              </div>
            </React.Fragment>
          );
        })}
      </div>

      {/* Details Box */}
      <div className="mt-4 p-3 bg-slate-950/80 border border-slate-800 rounded-lg">
        <div className="flex justify-between items-center text-[10px] text-slate-500 uppercase tracking-wider font-mono">
          <span>الحالة الحالية</span>
          <span className="font-bold text-indigo-400">{activePhase}</span>
        </div>
        <div className="text-xs text-slate-300 font-medium mt-1.5 line-clamp-2">
          {latestEvent ? `${latestEvent.title} ${latestEvent.detail ? `(${latestEvent.detail})` : ""}` : "الروبوت جاهز وفي حالة خمول."}
        </div>
      </div>
    </div>
  );
}
