import React from "react";
import { ChestActivityEvent } from "../chestTypes";

interface LiveBrowserPanelProps {
  events: ChestActivityEvent[];
}

export function LiveBrowserPanel({ events }: LiveBrowserPanelProps) {
  // Find latest browser event to get URL
  const browserEvents = events.filter((e) => e.source === "browser");
  const latestBrowserEvent = browserEvents[browserEvents.length - 1];
  
  const currentUrl = latestBrowserEvent?.detail || "https://www.google.com";
  const isActive = latestBrowserEvent?.phase === "searching" || latestBrowserEvent?.phase === "reading";

  return (
    <div className="flex flex-col bg-slate-900/60 backdrop-blur-md border border-slate-700/50 rounded-xl overflow-hidden shadow-2xl h-full">
      {/* Browser Bar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-slate-800/80 border-b border-slate-700/50">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-full bg-rose-500/80" />
          <div className="w-3 h-3 rounded-full bg-amber-500/80" />
          <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
        </div>
        
        {/* Navigation Buttons */}
        <div className="flex items-center gap-2 text-slate-400 text-xs">
          <button className="hover:text-slate-200">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button className="hover:text-slate-200">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        {/* Address Bar */}
        <div className="flex-1 flex items-center justify-between gap-2 px-3 py-1 bg-slate-950/80 border border-slate-800 rounded-lg text-slate-300 text-xs font-mono select-none overflow-hidden text-ellipsis whitespace-nowrap">
          <div className="flex items-center gap-2 overflow-hidden text-ellipsis">
            <span className="text-emerald-500 text-[10px] uppercase font-bold tracking-wider px-1 bg-emerald-500/10 rounded">HTTPS</span>
            <span className="text-slate-400 select-all overflow-hidden text-ellipsis">{currentUrl}</span>
          </div>
          {isActive && (
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-sky-505"></span>
              </span>
              <span className="text-[10px] text-sky-400 font-bold uppercase tracking-wider">LIVE</span>
            </div>
          )}
        </div>
      </div>

      {/* Browser Viewport Stream */}
      <div className="flex-1 relative bg-slate-950 flex items-center justify-center overflow-hidden min-h-[220px]">
        {/* Stream image */}
        <img
          src="/api/chest/browser/stream"
          alt="Visual Search Viewport"
          className="absolute inset-0 w-full h-full object-contain"
          onError={(e) => {
            // If the stream fails, show a fallback layout
            e.currentTarget.style.display = "none";
          }}
        />

        {/* Browser State Overlay */}
        {!isActive && browserEvents.length === 0 && (
          <div className="z-10 flex flex-col items-center gap-4 text-center px-6">
            <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-full text-slate-500 animate-pulse">
              <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
            </div>
            <div>
              <p className="text-slate-400 font-medium">متصفح البحث المرئي خامد</p>
              <p className="text-slate-600 text-xs mt-1">سيعرض هذا القسم المواقع التي يزورها الروبوت للتحقق من المعلومات.</p>
            </div>
          </div>
        )}

        {/* Running status HUD overlay */}
        {isActive && (
          <div className="absolute bottom-3 left-3 bg-slate-950/80 border border-slate-800 px-3 py-1.5 rounded-lg text-slate-300 text-xs flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-sky-500 animate-pulse" />
            <span className="font-mono">جاري تصفح: {latestBrowserEvent?.title || "البحث المرئي"}</span>
          </div>
        )}
      </div>
    </div>
  );
}
