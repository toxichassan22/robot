import { Suspense } from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../App";

function renderAt(route: string) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  return {
    container,
    root,
    render: async () => {
      await act(async () => {
        root.render(
          <MemoryRouter initialEntries={[route]}>
            <Suspense fallback={<div>loading</div>}>
              <AppRoutes />
            </Suspense>
          </MemoryRouter>,
        );
        await Promise.resolve();
        await Promise.resolve();
      });
    },
  };
}

describe("ChestDisplay Route", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  beforeEach(() => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: jest.fn().mockImplementation((query: string) => ({
        matches: query.includes("pointer: coarse"),
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      })),
    });

    // Mock EventSource
    class MockEventSource {
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      close = jest.fn();
      addEventListener = jest.fn();
      constructor(public url: string) {
        setTimeout(() => {
          if (this.onopen) this.onopen();
        }, 0);
      }
    }
    global.EventSource = MockEventSource as any;

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok" }),
    }) as unknown as typeof fetch;
  });

  afterEach(() => {
    if (root) {
      act(() => {
        root?.unmount();
      });
    }
    if (container) {
      container.remove();
    }
    root = null;
    container = null;
    jest.restoreAllMocks();
  });

  test("renders chest display page on /chest route", async () => {
    const mounted = renderAt("/chest");
    container = mounted.container;
    root = mounted.root;
    await mounted.render();

    expect(container.textContent).toContain("ROBOT CHEST INTERFACE");
    expect(container.textContent).toContain("حالة الروبوت");
  });

  test("renders maintenance screen when ?maintenance=1 is queried", async () => {
    const mounted = renderAt("/chest?maintenance=1");
    container = mounted.container;
    root = mounted.root;
    await mounted.render();

    expect(container.textContent).toContain("لوحة الصيانة المغلقة");
    expect(container.textContent).toContain("رمز PIN للروبوت");
  });
});
