import { useState, useEffect } from "react";
import { ShieldCheck, ShieldAlert, Loader2, PauseCircle, Check, X } from "lucide-react";
import { cn } from "../lib/utils";
import { RobotMode } from "../hooks/useRobotStatus";
import { getRobotAuthHeaders } from "../utils/api";

interface ModeSelectorProps {
    isOpen: boolean;
    onClose: () => void;
    currentMode: RobotMode;
}

interface ModeOption {
    id: RobotMode;
    label: string;
    description: string;
    icon: React.ElementType;
}

const MODES: ModeOption[] = [
    {
        id: "NAV",
        label: "Navigation Mode",
        description: "Ready to Move - Full Autonomy",
        icon: ShieldCheck,
    },
    {
        id: "IDLE",
        label: "Idle Mode",
        description: "Safe to Approach - Motors Disabled",
        icon: PauseCircle,
    },
    {
        id: "EMERGENCY",
        label: "Emergency Stop",
        description: "IMMEDIATE HALT - System Lock",
        icon: ShieldAlert,
    },
];

export function ModeSelector({ isOpen, onClose, currentMode }: ModeSelectorProps) {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Handle ESC key
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape" && isOpen && !isLoading) {
                onClose();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [isOpen, onClose, isLoading]);

    if (!isOpen) return null;

    const handleModeChange = async (mode: RobotMode) => {
        if (mode === currentMode) return;

        setIsLoading(true);
        setError(null);

        try {
            const res = await fetch("/api/mode", {
                method: "POST",
                headers: { "Content-Type": "application/json", ...getRobotAuthHeaders() },
                body: JSON.stringify({ mode }),
            });

            if (!res.ok) {
                throw new Error("Failed to update mode");
            }

            const data = await res.json();
            if (data.success) {
                // Wait a brief moment for visual feedback potentially, or close immediately
                // The parent status polling will pick up the change
                onClose();
            } else {
                throw new Error(data.error || "Failed to update mode");
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error occurred");
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 animate-in fade-in duration-200">
            {/* Backdrop click handler area */}
            <div
                className="absolute inset-0"
                onClick={() => !isLoading && onClose()}
            />

            <div className="relative w-full max-w-2xl overflow-hidden rounded-xl border border-white/10 bg-[#0B1221] shadow-2xl animate-in zoom-in-95 duration-200">
                <div className="flex items-center justify-between border-b border-white/5 p-6">
                    <h2 className="text-xl font-semibold text-white">Select System Mode</h2>
                    <button
                        onClick={onClose}
                        disabled={isLoading}
                        className="rounded-full p-2 text-muted-foreground hover:bg-white/5 disabled:opacity-50"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="p-6">
                    {error && (
                        <div className="mb-6 rounded-lg bg-red-500/10 p-3 text-sm text-red-500 border border-red-500/20">
                            {error}
                        </div>
                    )}

                    <div className="grid gap-4 md:grid-cols-3">
                        {MODES.map((mode) => {
                            const isActive = currentMode === mode.id;
                            const Icon = mode.icon;
                            const isProcessing = isLoading && isActive; // Show loading on current if theoretically needed, but usually we just show overlay

                            // Dynamic styles based on mode type
                            let colorClass = "";
                            let borderClass = "";

                            if (mode.id === "NAV") {
                                colorClass = isActive ? "text-green-400 bg-green-500/10" : "text-green-400/70 hover:bg-green-500/5";
                                borderClass = isActive ? "border-green-500/50 ring-1 ring-green-500/50" : "border-white/5 hover:border-green-500/30";
                            } else if (mode.id === "IDLE") {
                                colorClass = isActive ? "text-red-400 bg-red-500/10" : "text-red-400/70 hover:bg-red-500/5";
                                borderClass = isActive ? "border-red-500/50 ring-1 ring-red-500/50" : "border-white/5 hover:border-red-500/30";
                            } else if (mode.id === "EMERGENCY") {
                                colorClass = isActive ? "text-red-500 bg-red-500/20" : "text-red-500/70 hover:bg-red-500/10";
                                borderClass = isActive ? "border-red-500 ring-1 ring-red-500" : "border-white/5 hover:border-red-500/30";
                            }

                            return (
                                <button
                                    key={mode.id}
                                    onClick={() => handleModeChange(mode.id)}
                                    disabled={isLoading}
                                    className={cn(
                                        "group relative flex flex-col items-center justify-center gap-4 rounded-xl border p-6 text-center transition-all",
                                        borderClass,
                                        isLoading && "opacity-50 cursor-not-allowed"
                                    )}
                                >
                                    <div className={cn("rounded-full p-4 transition-colors", colorClass)}>
                                        <Icon className="h-8 w-8" />
                                    </div>

                                    <div className="space-y-1.5">
                                        <div className="font-semibold text-white group-hover:text-white/90">
                                            {mode.label}
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            {mode.description}
                                        </div>
                                    </div>

                                    {isActive && (
                                        <div className="absolute right-3 top-3 rounded-full bg-white/10 p-1">
                                            {isProcessing ? (
                                                <Loader2 className="h-3 w-3 animate-spin text-white" />
                                            ) : (
                                                <Check className="h-3 w-3 text-white" />
                                            )}
                                        </div>
                                    )}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {isLoading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                        <Loader2 className="h-8 w-8 animate-spin text-white" />
                    </div>
                )}
            </div>
        </div>
    );
}
