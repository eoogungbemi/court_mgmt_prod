"use client";

import { useEffect, useRef } from "react";

/**
 * Subscribes to real-time queue updates for a courtroom via WebSocket.
 * Calls `onUpdate` whenever the server signals a queue change.
 * Reconnects automatically on disconnect.
 * Falls back silently if WebSocket is unavailable (polling continues as backup).
 */
export function useQueueSocket(roomId: number, onUpdate: () => void): void {
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let pingTimer: ReturnType<typeof setInterval> | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let destroyed = false;

    function connect() {
      if (destroyed) return;
      try {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const base =
          process.env.NEXT_PUBLIC_WS_BASE ?? `${proto}://${window.location.host}`;
        ws = new WebSocket(`${base}/api/ws/courtroom/${roomId}`);
      } catch {
        return;
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data as string);
          if (msg.type === "queue_update") onUpdateRef.current();
        } catch {}
      };

      ws.onopen = () => {
        pingTimer = setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
        }, 30_000);
      };

      ws.onclose = () => {
        if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
        if (!destroyed) reconnectTimer = setTimeout(connect, 3_000);
      };

      ws.onerror = () => {
        ws?.close();
      };
    }

    connect();

    return () => {
      destroyed = true;
      if (pingTimer)     clearInterval(pingTimer);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [roomId]);
}
