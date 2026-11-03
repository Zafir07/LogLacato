import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { getToken } from "../services/api";

export type LiveMessage = { type: string; data?: any; event?: string; topic?: string };
type Listener = (m: LiveMessage) => void;

interface LiveState {
  connected: boolean;
  subscribe: (fn: Listener) => () => void;
}

const Ctx = createContext<LiveState | null>(null);

/** Uma conexão WebSocket por aba, com reconexão automática (1 s, 2 s, 4 s… até 30 s). */
export function LiveProvider({ children, enabled }: { children: ReactNode; enabled: boolean }) {
  const [connected, setConnected] = useState(false);
  const listeners = useRef(new Set<Listener>());

  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let retry = 1000;
    let timer: number | undefined;
    let stopped = false;

    const open = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/api/v1/ws?token=${encodeURIComponent(getToken() ?? "")}`);
      ws.onopen = () => {
        setConnected(true);
        retry = 1000;
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as LiveMessage;
          listeners.current.forEach((fn) => fn(msg));
        } catch {
          /* mensagem malformada: ignora */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (stopped) return;
        timer = window.setTimeout(open, retry);
        retry = Math.min(retry * 2, 30000);
      };
    };
    open();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, [enabled]);

  const value: LiveState = {
    connected,
    subscribe: (fn) => {
      listeners.current.add(fn);
      return () => listeners.current.delete(fn);
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLive(fn?: Listener) {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLive fora do LiveProvider");
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!ref.current) return;
    return v.subscribe((m) => ref.current?.(m));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v.subscribe]);
  return v.connected;
}
