import { useEffect, useRef } from "react";

type ShortcutHandler = (ev: KeyboardEvent) => void;

export type KeyboardShortcuts = {
  onSpace?: ShortcutHandler;
  onEnter?: ShortcutHandler;
  onCtrlK?: ShortcutHandler;
  onCtrlComma?: ShortcutHandler;
  onEscape?: ShortcutHandler;
};

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = (el.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  const editable = el.getAttribute?.("contenteditable");
  return editable === "" || editable === "true";
}

export function useKeyboardShortcuts(shortcuts: KeyboardShortcuts) {
  const shortcutsRef = useRef(shortcuts);

  useEffect(() => {
    shortcutsRef.current = shortcuts;
  }, [shortcuts]);

  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      const s = shortcutsRef.current;
      const key = ev.key;
      const ctrlOrMeta = ev.ctrlKey || ev.metaKey;
      const editable = isEditableTarget(ev.target);

      if (key === "Escape") {
        s.onEscape?.(ev);
        return;
      }

      if (ctrlOrMeta && (key === "k" || key === "K")) {
        ev.preventDefault();
        s.onCtrlK?.(ev);
        return;
      }

      if (ctrlOrMeta && key === ",") {
        ev.preventDefault();
        s.onCtrlComma?.(ev);
        return;
      }

      if (key === " " && !ctrlOrMeta && !ev.altKey) {
        if (!editable) {
          ev.preventDefault();
          s.onSpace?.(ev);
        }
        return;
      }

      if (key === "Enter" && !ctrlOrMeta && !ev.altKey && !ev.shiftKey) {
        if (editable) {
          ev.preventDefault();
        }
        s.onEnter?.(ev);
        return;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}

