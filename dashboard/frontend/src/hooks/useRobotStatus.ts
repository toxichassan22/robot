import { useState, useEffect, useRef, useCallback } from "react";

export type RobotMode = "NAV" | "IDLE" | "EMERGENCY";
export type ThermalLevel = "NORMAL" | "WARM" | "HOT" | "CRITICAL";
export type AudioState = "SLEEP" | "WAKE_WORD" | "ACTIVE" | "PROCESSING";

export interface RobotState {
    mode: RobotMode;
    thermal_level: ThermalLevel;
    temp_c: number;
    vision_layer: number;
    audio_state: AudioState;
    speed_limit: number;
    last_heartbeat_ack_ms: number;
}

export interface StatusResponse {
    success: boolean;
    state: RobotState;
    heartbeat_healthy: boolean;
    timestamp_ms: number;
}

export type RobotStatusResult = {
    status: StatusResponse | null;
    error: boolean;
    isLoading: boolean;
};

export function useRobotStatus(): RobotStatusResult {
    const [status, setStatus] = useState<StatusResponse | null>(null);
    const [error, setError] = useState<boolean>(false);
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const inFlight = useRef(false);
    const errorCount = useRef(0);
    const mountedRef = useRef(true);

    const fetchStatus = useCallback(async () => {
        // Prevent overlapping requests
        if (inFlight.current) return;
        // Optimization: Pause polling when tab is hidden
        if (document.hidden) return;

        inFlight.current = true;
        try {
            const res = await fetch("/api/status", { cache: "no-store" });
            if (!res.ok) throw new Error("Failed to fetch status");
            const data = await res.json();

            if (data.success) {
                if (!mountedRef.current) return;
                setStatus(data);
                setError(false);
                errorCount.current = 0;
                setIsLoading(false);
            } else {
                // Ignore "State manager not initialized" as it just means we are in standalone/test mode
                if (data.error === "State manager not initialized") {
                    errorCount.current = 0; // Don't escalate to error state
                    if (!mountedRef.current) return;
                    setIsLoading(false);
                    return; // Fail silently
                }
                throw new Error("API returned failure");
            }
        } catch (err) {
            errorCount.current += 1;
            // Only show error state after 3 consecutive failures
            if (errorCount.current >= 3) {
                if (errorCount.current === 3 && err instanceof Error) console.error("Status poll failed:", err);
                if (!mountedRef.current) return;
                setError(true);
                setIsLoading(false);
            }
        } finally {
            inFlight.current = false;
        }
    }, []);

    useEffect(() => {
        mountedRef.current = true;
        let failureDelayMs = 0;
        let timer: ReturnType<typeof setTimeout> | null = null;

        const scheduleNext = (delayMs: number) => {
            if (!mountedRef.current) return;
            if (timer) clearTimeout(timer);
            timer = setTimeout(() => {
                void tick();
            }, delayMs);
        };

        const tick = async () => {
            const beforeErrorCount = errorCount.current;
            await fetchStatus();

            if (!mountedRef.current) return;
            if (document.hidden) {
                scheduleNext(Math.max(3000, failureDelayMs || 3000));
                return;
            }

            if (errorCount.current > beforeErrorCount) {
                failureDelayMs = failureDelayMs === 0 ? 1800 : Math.min(15000, failureDelayMs * 2);
            } else {
                failureDelayMs = 750;
            }

            scheduleNext(failureDelayMs);
        };

        void tick();

        // Add visibility change listener to resume polling immediately when returning to tab
        const handleVisibilityChange = () => {
            if (document.hidden) return;
            failureDelayMs = Math.min(failureDelayMs || 750, 750);
            scheduleNext(100);
        };
        document.addEventListener("visibilitychange", handleVisibilityChange);

        return () => {
            mountedRef.current = false;
            if (timer) clearTimeout(timer);
            document.removeEventListener("visibilitychange", handleVisibilityChange);
        };
    }, [fetchStatus]);

    return { status, error, isLoading };
}
