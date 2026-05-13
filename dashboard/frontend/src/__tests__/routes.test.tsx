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

describe("AppRoutes", () => {
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

    global.fetch = jest.fn().mockRejectedValue(new Error("network")) as unknown as typeof fetch;
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

  test("renders landing page on root route", async () => {
    const mounted = renderAt("/");
    container = mounted.container;
    root = mounted.root;
    await mounted.render();

    expect(container.querySelector('[data-testid="landing-page"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="landing-scene-starfield"]')).not.toBeNull();
    expect(container.textContent).not.toContain("3D scene unavailable");
    expect(container.textContent).toContain("ابدأ");
    const cta = container.querySelector('a[href="/console"]');
    expect(cta).not.toBeNull();
  });

  test("renders operator dashboard on /console", async () => {
    const mounted = renderAt("/console");
    container = mounted.container;
    root = mounted.root;
    await mounted.render();

    expect(container.textContent).toContain("SYSTEMS & AI");
    expect(container.textContent).toContain("Intelligence Core");
    expect(container.textContent).toContain("Emergency Halt");
  });
});
