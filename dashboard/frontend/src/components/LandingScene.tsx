import { useEffect, useRef, useState, type ComponentType, type CSSProperties } from "react";
import type { Theme } from "../hooks/useTheme";
import DayClouds from "./DayClouds";

type MeteorNode = {
  id: number;
  x: number;
  y: number;
  scale: number;
  opacity: number;
  delay: number;
  duration: number;
  rotate: number;
  travelX: number;
  travelY: number;
  tailWidth: number;
  glowWidth: number;
  coreSize: number;
};

type ParticlesRenderer = ComponentType<{
  id?: string;
  className?: string;
  options?: unknown;
}>;

function isCompactViewport(): boolean {
  return typeof window !== "undefined" && window.innerWidth < 640;
}

function shouldUseParticles(): boolean {
  return typeof navigator === "undefined" || !/jsdom/i.test(navigator.userAgent);
}

function createMeteors(count: number, compact: boolean): MeteorNode[] {
  const zones = compact
    ? [
      { xMin: 10, xMax: 38, yMin: 10, yMax: 17 },
      { xMin: 54, xMax: 76, yMin: 14, yMax: 22 },
    ]
    : [
      { xMin: 10, xMax: 28, yMin: 12, yMax: 20 },
      { xMin: 36, xMax: 56, yMin: 10, yMax: 18 },
      { xMin: 66, xMax: 82, yMin: 18, yMax: 28 },
    ];

  return Array.from({ length: count }, (_, id) => {
    const zone = zones[id % zones.length];
    return {
      id,
      x: zone.xMin + Math.random() * (zone.xMax - zone.xMin),
      y: zone.yMin + Math.random() * (zone.yMax - zone.yMin),
      scale: Math.random() * 0.18 + 0.84,
      opacity: Math.random() * 0.12 + 0.32,
      delay: Math.random() * 14,
      duration: Math.random() * 3.4 + (compact ? 9.2 : 10.5),
      rotate: -(Math.random() * 7 + 29),
      travelX: (compact ? 150 : 200) + Math.random() * (compact ? 40 : 54),
      travelY: (compact ? 24 : 30) + Math.random() * (compact ? 10 : 12),
      tailWidth: (compact ? 58 : 78) + Math.random() * (compact ? 18 : 28),
      glowWidth: Math.random() * (compact ? 6 : 8) + (compact ? 14 : 16),
      coreSize: Math.random() * 0.9 + 1.6,
    };
  });
}

function createParticleOptions(compact: boolean, theme: Theme) {
  const isDay = theme === "light";

  return {
    fullScreen: {
      enable: false,
    },
    background: {
      color: {
        value: "transparent",
      },
    },
    detectRetina: true,
    fpsLimit: 60,
    interactivity: {
      detectsOn: "window" as const,
      events: {
        onHover: {
          enable: true,
          mode: "bubble" as const,
        },
        resize: {
          enable: true,
          delay: 0.2,
        },
      },
      modes: {
        bubble: {
          distance: compact ? 72 : 96,
          duration: 1.8,
          opacity: 0.88,
          size: compact ? 3.2 : 4,
        },
      },
    },
    particles: {
      color: {
        value: isDay ? ["#0f5cff", "#2563eb", "#ffb300", "#f59e0b"] : ["#ffffff", "#f8fafc", "#dbeafe"],
      },
      links: {
        enable: false,
      },
      move: {
        direction: "none" as const,
        enable: true,
        outModes: {
          default: "out" as const,
        },
        random: true,
        speed: isDay ? (compact ? 0.16 : 0.2) : compact ? 0.12 : 0.18,
        straight: false,
      },
      number: {
        density: {
          enable: true,
          area: compact ? 900 : 1200,
        },
        value: isDay ? (compact ? 16 : 28) : compact ? 56 : 82,
      },
      opacity: {
        value: {
          min: isDay ? 0.72 : 0.16,
          max: isDay ? 0.92 : 0.82,
        },
        animation: {
          enable: true,
          speed: compact ? 0.35 : 0.42,
          sync: false,
        },
      },
      shape: {
        type: isDay ? ("star" as const) : ("circle" as const),
        options: isDay
          ? {
              star: {
                sides: {
                  min: 4,
                  max: 4,
                },
                inset: {
                  min: 2.4,
                  max: 2.8,
                },
              },
            }
          : undefined,
      },
      size: {
        value: {
          min: isDay ? 1.2 : 0.7,
          max: isDay ? (compact ? 3.2 : 4) : compact ? 2.6 : 3.3,
        },
        animation: {
          enable: true,
          speed: compact ? 1 : 1.2,
          sync: false,
        },
      },
      rotate: isDay
        ? {
            value: {
              min: 0,
              max: 360,
            },
            direction: "clockwise" as const,
            animation: {
              enable: true,
              speed: compact ? 6 : 8,
              sync: false,
            },
          }
        : {
            value: 0,
          },
    },
  };
}

let particlesRuntimePromise: Promise<ParticlesRenderer> | null = null;

function loadParticlesRuntimeOnce(): Promise<ParticlesRenderer> {
  if (!particlesRuntimePromise) {
    particlesRuntimePromise = Promise.all([
      import("@tsparticles/react"),
      import("@tsparticles/slim"),
      import("@tsparticles/shape-star"),
    ]).then(async ([particlesModule, slimModule, starShapeModule]) => {
      await particlesModule.initParticlesEngine(async (engine) => {
        await slimModule.loadSlim(engine);
        await starShapeModule.loadStarShape(engine);
      });

      return particlesModule.default as ParticlesRenderer;
    });
  }

  return particlesRuntimePromise;
}

export default function LandingScene({ theme = "dark" }: { theme?: Theme }) {
  const shouldRenderParticles = shouldUseParticles();
  const sceneRef = useRef<HTMLDivElement | null>(null);
  const [compact, setCompact] = useState(isCompactViewport);
  const [ParticlesCanvas, setParticlesCanvas] = useState<ParticlesRenderer | null>(null);
  const [meteors, setMeteors] = useState<MeteorNode[]>(() => createMeteors(compact ? 2 : 3, compact));
  const isDay = theme === "light";

  useEffect(() => {
    if (!shouldRenderParticles) {
      return;
    }

    let mounted = true;

    loadParticlesRuntimeOnce().then((ParticlesComponent) => {
      if (mounted) {
        setParticlesCanvas(() => ParticlesComponent);
      }
    });

    return () => {
      mounted = false;
    };
  }, [shouldRenderParticles]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    const setPointerGlow = (x: number | string, y: number | string) => {
      scene.style.setProperty("--ts-pointer-x", typeof x === "number" ? `${x}px` : x);
      scene.style.setProperty("--ts-pointer-y", typeof y === "number" ? `${y}px` : y);
    };

    const onPointerMove = (event: PointerEvent) => {
      setPointerGlow(event.clientX, event.clientY);
    };

    const resetPointerGlow = () => {
      setPointerGlow("50%", "38%");
    };

    resetPointerGlow();
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerleave", resetPointerGlow);

    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerleave", resetPointerGlow);
    };
  }, []);

  useEffect(() => {
    const syncViewportMode = () => {
      setCompact(isCompactViewport());
    };

    window.addEventListener("resize", syncViewportMode);

    return () => {
      window.removeEventListener("resize", syncViewportMode);
    };
  }, []);

  useEffect(() => {
    setMeteors(isDay ? [] : createMeteors(compact ? 2 : 3, compact));
  }, [compact, isDay]);

  return (
    <div
      ref={sceneRef}
      data-testid="landing-scene-starfield"
      className="relative h-full w-full overflow-hidden"
      style={
        {
          "--ts-pointer-x": "50%",
          "--ts-pointer-y": "38%",
          background:
            isDay
              ? "linear-gradient(180deg, #d9e6f4 0%, #c7d8ea 36%, #a9bfd7 100%)"
              : "radial-gradient(circle at 20% 55%, rgba(255,255,255,0.045), transparent 24%), radial-gradient(circle at 84% 22%, rgba(72,86,124,0.08), transparent 26%), linear-gradient(180deg, #02040a 0%, #010204 52%, #000000 100%)",
        } as CSSProperties
      }
    >
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            isDay
              ? "radial-gradient(circle 12rem at 12% 10%, rgba(255,214,102,0.14) 0%, rgba(255,236,190,0.05) 38%, transparent 66%), radial-gradient(circle 18rem at 82% 18%, rgba(96,165,250,0.08) 0%, rgba(96,165,250,0.04) 24%, transparent 54%)"
              : "radial-gradient(circle 50rem at var(--ts-pointer-x) var(--ts-pointer-y), rgba(255,255,255,0.16) 0%, rgba(255,255,255,0.08) 18%, rgba(255,255,255,0.035) 38%, rgba(255,255,255,0.012) 60%, transparent 86%)",
        }}
      />
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            isDay
              ? "radial-gradient(circle 14rem at var(--ts-pointer-x) var(--ts-pointer-y), rgba(15,23,42,0.05) 0%, rgba(15,23,42,0.02) 24%, rgba(15,23,42,0.008) 38%, transparent 58%)"
              : "radial-gradient(circle 7rem at var(--ts-pointer-x) var(--ts-pointer-y), rgba(255,255,255,0.34) 0%, rgba(255,255,255,0.14) 38%, rgba(255,255,255,0.04) 62%, transparent 76%)",
          filter: isDay ? "blur(9px)" : "blur(18px)",
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background: isDay
            ? "linear-gradient(180deg, rgba(255,255,255,0.015), rgba(255,255,255,0.008) 18%, rgba(15,23,42,0.05) 68%, rgba(15,23,42,0.18) 100%)"
            : "linear-gradient(180deg, rgba(255,255,255,0.04), transparent 22%, rgba(255,255,255,0.02) 65%, transparent)",
        }}
      />
      {isDay ? <DayClouds variant="landing" /> : null}
      {isDay ? (
        <>
          <div className="absolute left-[5%] top-[4%] z-[3] h-36 w-36">
            <div className="absolute left-1/2 top-1/2 h-32 w-32 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#f4e3af]/85 bg-white/14 shadow-[0_0_0_1px_rgba(255,247,214,0.18)]" />
            <div className="absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#ffcc66] shadow-[0_18px_38px_rgba(249,115,22,0.18)] animate-[ts-sun-breathe_10s_ease-in-out_infinite]" />
          </div>
          <div className="absolute right-[10%] top-[17%] h-[16vh] w-[16vw] rounded-full bg-[#dbeafe]/16 blur-[48px]" />
          <div className="absolute bottom-[14%] left-[22%] h-[16vh] w-[18vw] rounded-full bg-white/10 blur-[68px]" />
        </>
      ) : (
        <>
          <div className="absolute -left-[10%] bottom-[12%] h-[20rem] w-[28rem] rounded-full bg-white/[0.035] blur-[140px]" />
          <div className="absolute -right-[8%] bottom-[-8%] h-[18rem] w-[24rem] rounded-full bg-slate-400/[0.05] blur-[150px]" />
        </>
      )}

      {shouldRenderParticles && ParticlesCanvas ? (
        <ParticlesCanvas
          id="landing-particles"
          className="absolute inset-0 z-[1]"
          options={createParticleOptions(compact, theme)}
        />
      ) : null}

      {meteors.map((meteor) => (
        <div
          key={meteor.id}
          className="absolute left-0 top-0 overflow-visible mix-blend-screen"
          style={{
            left: `${meteor.x}%`,
            top: `${meteor.y}%`,
            opacity: meteor.opacity,
            transform: `rotate(${meteor.rotate}deg)`,
          }}
        >
          <div
            className="ts-shooting-star will-change-transform"
            style={{
              width: `${meteor.tailWidth}px`,
              animationDuration: `${meteor.duration}s`,
              animationDelay: `-${meteor.delay}s`,
              animationIterationCount: "infinite",
            }}
          >
            <div
              className="absolute inset-x-0 top-1/2 h-[1.5px] -translate-y-1/2 rounded-full bg-[linear-gradient(90deg,rgba(255,255,255,0)_0%,rgba(255,255,255,0.08)_52%,rgba(255,255,255,0.96)_100%)]"
              style={{
                filter: "drop-shadow(0 0 6px rgba(255,255,255,0.22))",
              }}
            />
          </div>
        </div>
      ))}

      <div
        className="absolute left-1/2 top-1/2 h-[18rem] w-[18rem] -translate-x-1/2 -translate-y-1/2 rounded-full sm:h-[24rem] sm:w-[24rem]"
        style={{ border: `1px solid ${isDay ? "rgba(15,23,42,0.18)" : "rgba(255,255,255,0.10)"}` }}
      />
      <div
        className="absolute left-1/2 top-1/2 h-[12rem] w-[12rem] -translate-x-1/2 -translate-y-1/2 rounded-full sm:h-[16rem] sm:w-[16rem]"
        style={{ border: `1px solid ${isDay ? "rgba(15,23,42,0.22)" : "rgba(255,255,255,0.10)"}` }}
      />
      <div
        className="absolute left-1/2 top-1/2 h-32 w-32 -translate-x-1/2 -translate-y-1/2 rounded-full sm:h-40 sm:w-40"
        style={{ background: isDay ? "rgba(255,247,214,0.28)" : "rgba(255,255,255,0.08)", filter: "blur(60px)" }}
      />
      <div
        className="absolute inset-x-[16%] bottom-[14%] h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${isDay ? "rgba(15,23,42,0.18)" : "rgba(255,255,255,0.30)"}, transparent)` }}
      />
      <div
        className="absolute inset-x-[28%] top-[22%] h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${isDay ? "rgba(15,23,42,0.12)" : "rgba(255,255,255,0.18)"}, transparent)` }}
      />
    </div>
  );
}
