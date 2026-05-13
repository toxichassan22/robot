/**
 * Shared SSE stream parser for /api/llm/generate responses.
 *
 * Backend SSE contract:
 *   event: message  → { outputText: string, action: null, raw: object }
 *   event: done     → { outputText: string, action: { kind, payload }, raw: object }
 *   event: error    → { error: string }
 */

export interface SSEDoneResult {
    outputText: string;
    action: { kind: string; payload: Record<string, unknown> } | null;
    raw: unknown;
    meta?: Record<string, unknown> | null;
}

export interface SSEHandlers {
    /** Called for each incremental token from the model */
    onToken?: (token: string) => void;
    /** Called once when generation is complete */
    onDone?: (result: SSEDoneResult) => void;
    /** Called if the stream reports an error */
    onError?: (error: string) => void;
}

/**
 * Parse a single SSE text block (separated by \n\n) into event type + data.
 */
function parseEventBlock(block: string): { event: string; data: string } | null {
    const lines = block.split("\n").map((x) => x.replace(/\r$/, ""));
    let event = "message";
    const dataLines: string[] = [];

    for (const line of lines) {
        if (line.startsWith("event:")) {
            event = line.slice("event:".length).trim() || "message";
        }
        if (line.startsWith("data:")) {
            dataLines.push(line.slice("data:".length).trim());
        }
    }

    const data = dataLines.join("\n");
    if (!data) return null;
    return { event, data };
}

/**
 * Read an SSE stream from the backend and dispatch events to handlers.
 *
 * @param body     The ReadableStream from a fetch Response
 * @param handlers Callbacks for token, done, and error events
 * @returns        The full accumulated text from all message tokens
 */
export async function parseSSEStream(
    body: ReadableStream<Uint8Array>,
    handlers: SSEHandlers,
): Promise<string> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullText = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
            const evt = parseEventBlock(part);
            if (!evt) continue;

            let payload: Record<string, unknown> | null = null;
            try {
                payload = JSON.parse(evt.data) as Record<string, unknown>;
            } catch {
                // Non-JSON data, skip
                continue;
            }

            if (evt.event === "message" && payload) {
                const token = String(payload.outputText ?? "");
                if (token) {
                    fullText += token;
                    handlers.onToken?.(token);
                }
            } else if (evt.event === "done" && payload) {
                // Final event — extract complete result
                const outputText = typeof payload.outputText === "string" ? payload.outputText : fullText;
                const action =
                    payload.action && typeof payload.action === "object"
                        ? (payload.action as SSEDoneResult["action"])
                        : null;
                const meta =
                    payload.meta && typeof payload.meta === "object"
                        ? (payload.meta as Record<string, unknown>)
                        : null;

                if (payload.success === false) {
                    handlers.onError?.(String(payload.error || "Generation failed"));
                } else {
                    handlers.onDone?.({
                        outputText,
                        action,
                        raw: payload.raw,
                        meta,
                    });
                }
            } else if (evt.event === "error" && payload) {
                handlers.onError?.(String(payload.error || "Unknown error"));
            }
        }
    }

    return fullText;
}
