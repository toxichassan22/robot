import { useEffect } from "react";

export function useUnsavedChangesGuard(active: boolean, message: string) {
  useEffect(() => {
    if (!active) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = message;
      return message;
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [active, message]);

  useEffect(() => {
    if (!active) return;

    const handleDocumentClick = (event: MouseEvent) => {
      const target = event.target instanceof HTMLElement ? event.target.closest("a[href]") : null;
      if (!target) return;

      const href = target.getAttribute("href");
      if (!href || href.startsWith("#")) return;

      const nextUrl = new URL(href, window.location.href);
      const currentUrl = new URL(window.location.href);
      if (nextUrl.pathname === currentUrl.pathname && nextUrl.search === currentUrl.search) return;

      if (!window.confirm(message)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };

    document.addEventListener("click", handleDocumentClick, true);
    return () => {
      document.removeEventListener("click", handleDocumentClick, true);
    };
  }, [active, message]);
}
