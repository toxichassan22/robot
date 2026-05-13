import { useState, useEffect, useRef } from "react";
import { AlertTriangle, X, ShieldAlert } from "lucide-react";
import { cn } from "../lib/utils";

interface SafetyEvent {
    event: string;
    reason: string;
    original?: unknown;
    safe?: unknown;
    ts_ms: number;
}

interface Alert extends SafetyEvent {
    id: string; // Unique ID for React key
    isExiting?: boolean;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
    return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function SafetyAlertBanner() {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const lastSeenRef = useRef<number>(Date.now());
    const timeoutIdsRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

    // Cleanup timeouts on unmount
    useEffect(() => {
        const ids = timeoutIdsRef.current;
        return () => {
            ids.forEach(id => clearTimeout(id));
            ids.clear();
        };
    }, []);

    // Poll for safety events
    useEffect(() => {
        let mounted = true;
        let failureCount = 0;
        let timer: ReturnType<typeof setTimeout> | null = null;

        const scheduleNext = (delayMs: number) => {
            if (!mounted) return;
            if (timer) clearTimeout(timer);
            timer = setTimeout(() => {
                void poll();
            }, delayMs);
        };

        const poll = async () => {
            let nextDelayMs = failureCount === 0 ? 2000 : Math.min(30000, 3000 * 2 ** failureCount);
            try {
                if (document.hidden) {
                    nextDelayMs = failureCount === 0 ? 5000 : Math.min(30000, 5000 * 2 ** (failureCount - 1));
                    return;
                }

                const res = await fetch("/api/safety-events?limit=5");
                if (!res.ok) {
                    failureCount = Math.min(failureCount + 1, 4);
                    nextDelayMs = Math.min(30000, 3000 * 2 ** failureCount);
                    return;
                }

                const data = await res.json();
                if (data.success && Array.isArray(data.events)) {
                    failureCount = 0;
                    nextDelayMs = 2000;
                    // Filter for events strictly newer than what we last processed
                    const newEvents = data.events.filter((e: SafetyEvent) => e.ts_ms > lastSeenRef.current);

                    if (newEvents.length > 0) {
                        // Update timestamp marker to the latest event
                        lastSeenRef.current = Math.max(...newEvents.map((e: SafetyEvent) => e.ts_ms));

                        // Add unique IDs
                        const newAlerts: Alert[] = newEvents.map((e: SafetyEvent) => ({
                            ...e,
                            id: `${e.ts_ms}-${Math.random().toString(36).substr(2, 9)}`
                        }));

                        setAlerts(prev => [...prev, ...newAlerts]);

                        // Set up auto-dismiss timers
                        newAlerts.forEach((alert) => {
                            const id = setTimeout(() => {
                                dismissAlert(alert.id);
                                timeoutIdsRef.current.delete(id);
                            }, 5000); // Auto dismiss after 5 seconds
                            timeoutIdsRef.current.add(id);
                        });
                    }
                }
            } catch (error) {
                void error;
                failureCount = Math.min(failureCount + 1, 4);
                nextDelayMs = Math.min(30000, 3000 * 2 ** failureCount);
            } finally {
                scheduleNext(nextDelayMs);
            }
        };

        void poll();

        const handleVisibilityChange = () => {
            if (document.hidden) return;
            scheduleNext(100);
        };
        document.addEventListener("visibilitychange", handleVisibilityChange);

        return () => {
            mounted = false;
            if (timer) clearTimeout(timer);
            document.removeEventListener("visibilitychange", handleVisibilityChange);
        };
    }, []);

    const dismissAlert = (id: string) => {
        setAlerts(prev => prev.filter(a => a.id !== id));
    };

    // Helper to render JSON diff
    const renderDiff = (original: unknown, safe: unknown) => {
        if (!isPlainObject(original) || !isPlainObject(safe)) return null;
        const allKeys = Array.from(new Set([...Object.keys(original), ...Object.keys(safe)]));

        return (
            <div className="mt-2 text-xs font-mono bg-black/40 rounded p-2 overflow-x-auto border border-white/10">
                <div className="flex flex-col gap-1">
                    {allKeys.map(key => {
                        const originalVal = original[key];
                        const safeVal = safe[key];
                        const originalStr = JSON.stringify(originalVal);
                        const safeStr = JSON.stringify(safeVal);

                        if (originalVal === undefined && safeVal !== undefined) {
                            // Added
                            return (
                                <div key={key} className="text-green-400 bg-green-900/20 px-1 rounded flex gap-2">
                                    <span className="font-bold">+ {key}:</span>
                                    <span>{safeStr}</span>
                                </div>
                            );
                        } else if (originalVal !== undefined && safeVal === undefined) {
                            // Removed
                            return (
                                <div key={key} className="text-red-400 bg-red-900/20 px-1 rounded flex gap-2 line-through opacity-70">
                                    <span className="font-bold">- {key}:</span>
                                    <span>{originalStr}</span>
                                </div>
                            );
                        } else if (originalStr !== safeStr) {
                            // Changed
                            return (
                                <div key={key} className="text-yellow-400 bg-yellow-900/20 px-1 rounded flex flex-col sm:flex-row sm:gap-2">
                                    <span className="font-bold">~ {key}:</span>
                                    <div className="flex gap-2">
                                        <span className="text-red-400/70 line-through">{originalStr}</span>
                                        <span className="text-green-400">→ {safeStr}</span>
                                    </div>
                                </div>
                            );
                        }
                        return null;
                    })}
                    {allKeys.length === 0 && (
                        <div className="text-gray-400">No structured fields detected.</div>
                    )}
                </div>
            </div>
        );
    };

    if (alerts.length === 0) return null;

    return (
        <>
            <style>{`
                @keyframes slideDown {
                    from { transform: translateY(-100%); opacity: 0; }
                    to { transform: translateY(0); opacity: 1; }
                }
                @keyframes shrink {
                    from { width: 100%; }
                    to { width: 0%; }
                }
                .safety-alert-enter {
                    animation: slideDown 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
                }
            `}</style>
            <div className="flex flex-col gap-2 p-4 pointer-events-none fixed top-16 left-0 right-0 z-50 w-full max-w-4xl mx-auto">
                {alerts.map(alert => {
                    const isCritical = alert.event.toLowerCase().includes("emergency") || alert.event.toLowerCase().includes("block");

                    return (
                        <div
                            key={alert.id}
                            className={cn(
                                "safety-alert-enter pointer-events-auto relative flex flex-col gap-2 rounded-lg border p-4 shadow-xl overflow-hidden",
                                isCritical
                                    ? "border-red-500/50 bg-red-950/90 text-red-100"
                                    : "border-yellow-500/50 bg-yellow-950/90 text-yellow-100"
                            )}
                        >
                            <div className="flex items-start justify-between gap-3">
                                <div className="flex items-center gap-2">
                                    {isCritical ? (
                                        <ShieldAlert className="h-5 w-5 text-red-500 shrink-0" />
                                    ) : (
                                        <AlertTriangle className="h-5 w-5 text-yellow-500 shrink-0" />
                                    )}
                                    <span className="font-semibold text-sm sm:text-base">{alert.event}</span>
                                </div>
                                <button
                                    onClick={() => dismissAlert(alert.id)}
                                    className="rounded-full p-1 hover:bg-white/10 transition-colors shrink-0"
                                    aria-label="Dismiss"
                                >
                                    <X className="h-4 w-4" />
                                </button>
                            </div>

                            <p className="text-sm opacity-90 pl-0 sm:pl-7">{alert.reason}</p>

                            <div className="pl-0 sm:pl-7">
                                {renderDiff(alert.original, alert.safe)}
                            </div>

                            {/* Progress bar for auto-dismiss */}
                            <div
                                className={cn(
                                    "absolute bottom-0 left-0 h-1 transition-all ease-linear w-full",
                                    isCritical ? "bg-red-500/50" : "bg-yellow-500/50"
                                )}
                                style={{ animation: "shrink 5s linear forwards" }}
                            />
                        </div>
                    );
                })}
            </div>
        </>
    );
}
