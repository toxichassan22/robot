import React from "react";
import { ChestActivityPhase } from "../chestTypes";

interface EmotionAvatarProps {
  phase: ChestActivityPhase;
}

export function EmotionAvatar({ phase }: EmotionAvatarProps) {
  // Map phase to visual theme
  const getTheme = (p: ChestActivityPhase) => {
    switch (p) {
      case "listening":
        return {
          color: "from-emerald-400 to-teal-500",
          shadow: "shadow-emerald-500/30",
          glow: "bg-emerald-500/20",
          label: "جاري الاستماع...",
          pulseClass: "animate-[ping_1.5s_infinite]",
        };
      case "thinking":
        return {
          color: "from-amber-400 to-orange-500",
          shadow: "shadow-amber-500/30",
          glow: "bg-amber-500/20",
          label: "يفكر...",
          pulseClass: "animate-[spin_3s_linear_infinite]",
        };
      case "searching":
      case "reading":
        return {
          color: "from-sky-400 to-blue-600",
          shadow: "shadow-sky-500/30",
          glow: "bg-sky-500/20",
          label: "يبحث في الإنترنت...",
          pulseClass: "animate-[pulse_1s_infinite]",
        };
      case "analyzing":
        return {
          color: "from-indigo-500 to-purple-600",
          shadow: "shadow-indigo-500/30",
          glow: "bg-indigo-500/20",
          label: "يحلل البيانات...",
          pulseClass: "animate-[spin_1.5s_linear_infinite]",
        };
      case "speaking":
        return {
          color: "from-pink-500 to-rose-500",
          shadow: "shadow-rose-500/30",
          glow: "bg-rose-500/20",
          label: "يتحدث الآن...",
          pulseClass: "animate-[bounce_0.8s_infinite]",
        };
      case "success":
        return {
          color: "from-green-400 to-emerald-600",
          shadow: "shadow-green-500/30",
          glow: "bg-green-500/20",
          label: "اكتمل بنجاح",
          pulseClass: "animate-[ping_2s_infinite]",
        };
      case "error":
        return {
          color: "from-red-500 to-rose-600",
          shadow: "shadow-red-500/30",
          glow: "bg-red-500/20",
          label: "خطأ في المعالجة",
          pulseClass: "animate-[pulse_0.5s_infinite] border-2 border-red-400",
        };
      case "idle":
      default:
        return {
          color: "from-slate-600 to-indigo-800",
          shadow: "shadow-slate-800/20",
          glow: "bg-slate-800/10",
          label: "خمول",
          pulseClass: "animate-[pulse_4s_infinite]",
        };
    }
  };

  const theme = getTheme(phase);

  return (
    <div className="flex flex-col items-center justify-center bg-slate-900/60 backdrop-blur-md border border-slate-700/50 rounded-xl p-6 shadow-2xl h-full">
      <div className="relative w-40 h-40 flex items-center justify-center mb-4">
        {/* Glow Outer Layer */}
        <div className={`absolute inset-0 rounded-full blur-2xl transition-all duration-1000 ${theme.glow}`} />

        {/* Pulsing ring */}
        <div className={`absolute w-full h-full rounded-full border border-dashed border-slate-700/50 ${theme.pulseClass}`} />

        {/* Inner Fluid Orb */}
        <div
          className={`w-28 h-28 rounded-full bg-gradient-to-tr ${theme.color} shadow-2xl ${theme.shadow} transition-all duration-1000 flex items-center justify-center overflow-hidden`}
        >
          {/* Futuristic Face Elements or Audio Waves */}
          {phase === "speaking" ? (
            <div className="flex gap-1 items-end h-10">
              <div className="w-1.5 bg-white/80 rounded animate-[bounce_0.6s_infinite] h-8" />
              <div className="w-1.5 bg-white/80 rounded animate-[bounce_0.6s_infinite_0.1s] h-10" />
              <div className="w-1.5 bg-white/80 rounded animate-[bounce_0.6s_infinite_0.2s] h-6" />
              <div className="w-1.5 bg-white/80 rounded animate-[bounce_0.6s_infinite_0.3s] h-9" />
              <div className="w-1.5 bg-white/80 rounded animate-[bounce_0.6s_infinite_0.4s] h-5" />
            </div>
          ) : phase === "listening" ? (
            <div className="w-12 h-12 rounded-full border-4 border-white/40 animate-ping" />
          ) : phase === "thinking" ? (
            <div className="w-10 h-10 border-4 border-t-white border-white/20 rounded-full animate-spin" />
          ) : (
            // Robot Eye HUD design
            <div className="flex items-center justify-center gap-4">
              <div className="w-4 h-4 rounded-full bg-white/90 animate-pulse shadow-[0_0_8px_#fff]" />
              <div className="w-4 h-4 rounded-full bg-white/90 animate-pulse shadow-[0_0_8px_#fff]" />
            </div>
          )}
        </div>
      </div>

      <div className="text-center">
        <span className="text-xs text-slate-500 font-medium tracking-wider uppercase">حالة الروبوت</span>
        <h2 className="text-slate-200 text-lg font-bold mt-0.5">{theme.label}</h2>
      </div>
    </div>
  );
}
