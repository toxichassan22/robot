import { useEffect, useState, useRef } from "react";
import { ChestActivityEvent } from "../components/chestTypes";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export function useChestActivity() {
  const [events, setEvents] = useState<ChestActivityEvent[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let reconnectTimeout: number;

    function connect() {
      setStatus("connecting");
      const url = `${window.location.protocol}//${window.location.host}/api/chest/events`;
      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onopen = () => {
        setStatus("connected");
      };

      es.onerror = () => {
        setStatus("disconnected");
        es.close();
        // Auto-reconnect after 3 seconds
        reconnectTimeout = window.setTimeout(() => {
          connect();
        }, 3000);
      };

      es.addEventListener("snapshot", (e: MessageEvent) => {
        try {
          const snapshot = JSON.parse(e.data) as ChestActivityEvent[];
          setEvents(snapshot);
        } catch (err) {
          console.error("Error parsing chest snapshot event", err);
        }
      });

      es.addEventListener("activity", (e: MessageEvent) => {
        try {
          const newEvent = JSON.parse(e.data) as ChestActivityEvent;
          setEvents((prev) => {
            const next = [...prev, newEvent];
            if (next.length > 200) {
              next.shift();
            }
            return next;
          });
        } catch (err) {
          console.error("Error parsing chest activity event", err);
        }
      });

      // Heartbeat requires no action except confirming the connection is alive
      es.addEventListener("heartbeat", () => {
        // Keeps connection active
      });
    }

    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      clearTimeout(reconnectTimeout);
    };
  }, []);

  return { events, status };
}
