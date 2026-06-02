import React, { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useChestActivity } from "../hooks/useChestActivity";
import { EmotionAvatar } from "../components/chest/EmotionAvatar";
import { AnalysisVisualizer } from "../components/chest/AnalysisVisualizer";
import { LiveBrowserPanel } from "../components/chest/LiveBrowserPanel";
import { MaintenanceTray } from "../components/chest/MaintenanceTray";

export function ChestDisplay() {
  const { events, status } = useChestActivity();
  const location = useLocation();
  const timelineEndRef = useRef<HTMLDivElement | null>(null);

  // Floating chat states
  const [chatOpen, setChatOpen] = useState(false);
  const [chatText, setChatText] = useState("");
  const [sending, setSending] = useState(false);

  // Check for maintenance query param
  const query = new URLSearchParams(location.search);
  const showMaintenance = query.get("maintenance") === "1";

  const latestEvent = events[events.length - 1];
  const activePhase = latestEvent?.phase || "idle";

  // Auto-scroll timeline to bottom
  useEffect(() => {
    if (timelineEndRef.current) {
      timelineEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [events]);

  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatText.trim() || sending) return;
    setSending(true);
    try {
      const res = await fetch("/api/chest/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: chatText }),
      });
      if (res.ok) {
        setChatText("");
        setChatOpen(false);
      }
    } catch (err) {
      console.error("Failed to send chat:", err);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans select-none overflow-x-hidden">
      {/* HUD Header */}
      <header className="flex justify-between items-center px-6 py-4 bg-slate-900/40 border-b border-slate-800/80 backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="relative flex h-3 w-3">
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                status === "connected"
                  ? "bg-emerald-400"
                  : status === "connecting"
                  ? "bg-amber-400"
                  : "bg-rose-400"
              }`}
            />
            <span
              className={`relative inline-flex rounded-full h-3 w-3 ${
                status === "connected"
                  ? "bg-emerald-500"
                  : status === "connecting"
                  ? "bg-amber-500"
                  : "bg-rose-500"
              }`}
            />
          </div>
          <div>
            <h1 className="text-sm font-black tracking-widest text-slate-200 font-mono">ROBOT CHEST INTERFACE</h1>
            <span className="text-[10px] text-slate-500 font-semibold tracking-wider font-mono">
              STATUS: {status.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Date and Clock */}
        <div className="text-right">
          <span className="text-xs text-slate-400 font-mono font-medium">
            {new Date().toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" })}
          </span>
          <span className="text-[9px] text-slate-600 font-bold block tracking-wider uppercase font-mono">
            {new Date().toLocaleDateString("en-US", { month: "short", day: "numeric" })}
          </span>
        </div>
      </header>

      {/* Main Responsive Grid Layout */}
      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch max-w-7xl mx-auto w-full">
        {/* Left column: Avatar and logs timeline */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          {/* Avatar Panel */}
          <div className="flex-shrink-0">
            <EmotionAvatar phase={activePhase} />
          </div>

          {/* Timeline Feed Panel */}
          <div className="flex-1 flex flex-col bg-slate-900/60 backdrop-blur-md border border-slate-700/50 rounded-xl p-4 shadow-2xl overflow-hidden min-h-[300px]">
            <h3 className="text-slate-300 text-sm font-semibold mb-3 flex items-center gap-2">
              <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              سجل العمليات الأخير
            </h3>

            {/* Timeline Stream */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-2 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent max-h-[400px]">
              {events.length === 0 ? (
                <div className="h-full flex items-center justify-center text-slate-600 text-xs italic">
                  لا توجد سجلات بعد. في انتظار نشاط الروبوت...
                </div>
              ) : (
                events.map((e, idx) => (
                  <div
                    key={e.id || idx}
                    className={`p-2.5 rounded-lg border text-xs flex flex-col gap-1 transition-all ${
                      e.severity === "error"
                        ? "bg-rose-950/20 border-rose-900/50 text-rose-300"
                        : e.severity === "warning"
                        ? "bg-amber-950/20 border-amber-900/50 text-amber-300"
                        : e.phase === activePhase && idx === events.length - 1
                        ? "bg-indigo-950/30 border-indigo-500/50 text-indigo-200"
                        : "bg-slate-950/40 border-slate-800/80 text-slate-300"
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-mono text-[9px] text-slate-500">
                        {new Date(e.tsMs).toLocaleTimeString("en-US", {
                          hour12: false,
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </span>
                      <span
                        className={`text-[8px] uppercase tracking-wider px-1.5 py-0.5 rounded font-bold ${
                          e.source === "browser"
                            ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                            : e.source === "debate"
                            ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
                            : e.source === "tts"
                            ? "bg-pink-500/10 text-pink-400 border border-pink-500/20"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {e.source}
                      </span>
                    </div>

                    <div className="font-bold">{e.title}</div>
                    {e.detail && <div className="text-[11px] text-slate-500 break-words">{e.detail}</div>}
                  </div>
                ))
              )}
              <div ref={timelineEndRef} />
            </div>
          </div>
        </div>

        {/* Right column: Graph, Browser and Maintenance */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          {showMaintenance ? (
            <div className="flex-1">
              <MaintenanceTray />
            </div>
          ) : (
            <>
              {/* Decision Flow Pipeline */}
              <div className="h-auto">
                <AnalysisVisualizer events={events} />
              </div>

              {/* Browser Panel */}
              <div className="flex-1">
                <LiveBrowserPanel events={events} />
              </div>
            </>
          )}
        </div>
      </main>

      {/* Floating Chat Input Widget */}
      <div className="fixed bottom-6 right-6 z-[100] flex flex-col items-end gap-3 font-sans">
        {chatOpen && (
          <form
            onSubmit={handleSendChat}
            className="flex items-center gap-2 bg-slate-900/90 border border-slate-700/80 rounded-xl p-3 shadow-2xl backdrop-blur-xl w-80 md:w-96"
          >
            <input
              type="text"
              value={chatText}
              onChange={(e) => setChatText(e.target.value)}
              placeholder="اكتب سؤالك للروبوت هنا..."
              disabled={sending}
              className="flex-1 bg-slate-950/80 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500/80"
              autoFocus
            />
            <button
              type="submit"
              disabled={sending || !chatText.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-lg px-3 py-2 text-xs font-bold transition-all flex items-center justify-center min-w-[50px]"
            >
              {sending ? "..." : "إرسال"}
            </button>
          </form>
        )}
        <button
          onClick={() => setChatOpen(!chatOpen)}
          className={`flex items-center justify-center w-12 h-12 rounded-full shadow-2xl cursor-pointer transition-all duration-300 ${
            chatOpen 
              ? "bg-rose-600 hover:bg-rose-500 text-white rotate-90" 
              : "bg-indigo-600 hover:bg-indigo-500 text-white hover:scale-105"
          }`}
          title="إرسال نص للروبوت"
        >
          {chatOpen ? (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}

export default ChestDisplay;
