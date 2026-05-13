import type { CSSProperties } from "react";

type DayCloudVariant = "app" | "landing";

type DayCloudConfig = {
  top: string;
  left: string;
  width: number;
  height: number;
  opacity: number;
  pulse: string;
  travelDuration: string;
  travelDelay: string;
  floatDuration: string;
  floatDelay: string;
  startX: string;
  endX: string;
  startY: string;
  endY: string;
};

type CloudTravelStyle = CSSProperties & {
  "--ts-cloud-start-x": string;
  "--ts-cloud-end-x": string;
  "--ts-cloud-start-y": string;
  "--ts-cloud-end-y": string;
};

const DAY_CLOUDS: Record<DayCloudVariant, DayCloudConfig[]> = {
  app: [
    {
      top: "5%",
      left: "-24%",
      width: 440,
      height: 146,
      opacity: 0.94,
      pulse: "12.4s",
      travelDuration: "54s",
      travelDelay: "-17s",
      floatDuration: "15.4s",
      floatDelay: "-5s",
      startX: "0vw",
      endX: "34vw",
      startY: "0px",
      endY: "8px",
    },
    {
      top: "12%",
      left: "18%",
      width: 320,
      height: 110,
      opacity: 0.82,
      pulse: "10.4s",
      travelDuration: "44s",
      travelDelay: "-9s",
      floatDuration: "12.4s",
      floatDelay: "-7s",
      startX: "-3vw",
      endX: "17vw",
      startY: "0px",
      endY: "-7px",
    },
    {
      top: "18%",
      left: "72%",
      width: 340,
      height: 118,
      opacity: 0.88,
      pulse: "11.8s",
      travelDuration: "48s",
      travelDelay: "-24s",
      floatDuration: "13.8s",
      floatDelay: "-3s",
      startX: "-23vw",
      endX: "3vw",
      startY: "1px",
      endY: "-8px",
    },
    {
      top: "30%",
      left: "-6%",
      width: 500,
      height: 166,
      opacity: 0.76,
      pulse: "14.2s",
      travelDuration: "60s",
      travelDelay: "-31s",
      floatDuration: "16.8s",
      floatDelay: "-2s",
      startX: "0vw",
      endX: "28vw",
      startY: "0px",
      endY: "10px",
    },
    {
      top: "8%",
      left: "88%",
      width: 250,
      height: 88,
      opacity: 0.62,
      pulse: "9.2s",
      travelDuration: "42s",
      travelDelay: "-20s",
      floatDuration: "10.6s",
      floatDelay: "-6s",
      startX: "-18vw",
      endX: "2vw",
      startY: "0px",
      endY: "-6px",
    },
  ],
  landing: [
    {
      top: "4%",
      left: "-26%",
      width: 500,
      height: 164,
      opacity: 0.98,
      pulse: "12.8s",
      travelDuration: "58s",
      travelDelay: "-18s",
      floatDuration: "15.8s",
      floatDelay: "-4s",
      startX: "0vw",
      endX: "38vw",
      startY: "0px",
      endY: "9px",
    },
    {
      top: "12%",
      left: "20%",
      width: 340,
      height: 116,
      opacity: 0.84,
      pulse: "10.2s",
      travelDuration: "46s",
      travelDelay: "-11s",
      floatDuration: "12.2s",
      floatDelay: "-8s",
      startX: "-4vw",
      endX: "16vw",
      startY: "0px",
      endY: "-7px",
    },
    {
      top: "20%",
      left: "74%",
      width: 380,
      height: 126,
      opacity: 0.9,
      pulse: "12.6s",
      travelDuration: "50s",
      travelDelay: "-26s",
      floatDuration: "14.4s",
      floatDelay: "-5s",
      startX: "-24vw",
      endX: "4vw",
      startY: "2px",
      endY: "-8px",
    },
    {
      top: "31%",
      left: "-8%",
      width: 540,
      height: 176,
      opacity: 0.8,
      pulse: "14.6s",
      travelDuration: "62s",
      travelDelay: "-34s",
      floatDuration: "17s",
      floatDelay: "-3s",
      startX: "0vw",
      endX: "30vw",
      startY: "0px",
      endY: "11px",
    },
    {
      top: "36%",
      left: "84%",
      width: 300,
      height: 102,
      opacity: 0.68,
      pulse: "9.8s",
      travelDuration: "44s",
      travelDelay: "-22s",
      floatDuration: "11.6s",
      floatDelay: "-6s",
      startX: "-18vw",
      endX: "4vw",
      startY: "0px",
      endY: "-6px",
    },
  ],
};

function CloudShape({ cloud }: { cloud: DayCloudConfig }) {
  return (
    <>
      <div
        className="absolute inset-[2%] rounded-[999px]"
        style={{
          opacity: cloud.opacity * 0.98,
          background:
            "radial-gradient(ellipse at 50% 54%, rgba(112,131,154,1) 0%, rgba(112,131,154,0.9) 38%, rgba(112,131,154,0.6) 66%, transparent 90%)",
          filter: "blur(19px)",
          animation: `ts-cloud-breathe ${cloud.pulse} ease-in-out infinite`,
          animationDelay: cloud.travelDelay,
        }}
      />
      <div
        className="absolute inset-x-[18%] top-[10%] h-[28%] rounded-[999px]"
        style={{
          opacity: cloud.opacity * 0.58,
          background:
            "radial-gradient(ellipse at 50% 52%, rgba(255,255,255,0.84) 0%, rgba(255,255,255,0.24) 70%, transparent 100%)",
          filter: "blur(10px)",
          animation: `ts-cloud-breathe calc(${cloud.pulse} * 0.82) ease-in-out infinite`,
          animationDelay: `calc(${cloud.travelDelay} - 1.4s)`,
        }}
      />
      <div
        className="absolute bottom-[16%] left-[2%] h-[48%] w-[30%] rounded-full"
        style={{
          opacity: cloud.opacity,
          background:
            "radial-gradient(circle at 50% 46%, rgba(236,241,247,0.98) 0%, rgba(158,173,192,0.94) 44%, rgba(112,131,154,0.44) 74%, transparent 100%)",
          filter: "blur(13px)",
          animation: `ts-cloud-breathe ${cloud.pulse} ease-in-out infinite`,
          animationDelay: cloud.travelDelay,
        }}
      />
      <div
        className="absolute bottom-[28%] left-[21%] h-[54%] w-[38%] rounded-full"
        style={{
          opacity: cloud.opacity,
          background:
            "radial-gradient(circle at 50% 44%, rgba(245,248,252,1) 0%, rgba(181,195,209,0.94) 50%, rgba(112,131,154,0.42) 78%, transparent 100%)",
          filter: "blur(14px)",
          animation: `ts-cloud-breathe calc(${cloud.pulse} * 0.88) ease-in-out infinite`,
          animationDelay: `calc(${cloud.travelDelay} - 1.2s)`,
        }}
      />
      <div
        className="absolute bottom-[20%] left-[53%] h-[44%] w-[26%] rounded-full"
        style={{
          opacity: cloud.opacity,
          background:
            "radial-gradient(circle at 50% 48%, rgba(231,237,244,0.96) 0%, rgba(152,168,188,0.9) 48%, rgba(112,131,154,0.4) 76%, transparent 100%)",
          filter: "blur(13px)",
          animation: `ts-cloud-breathe calc(${cloud.pulse} * 1.08) ease-in-out infinite`,
          animationDelay: `calc(${cloud.travelDelay} - 0.7s)`,
        }}
      />
      <div
        className="absolute bottom-[14%] left-[70%] h-[30%] w-[18%] rounded-full"
        style={{
          opacity: cloud.opacity * 0.92,
          background:
            "radial-gradient(circle at 50% 48%, rgba(230,236,242,0.92) 0%, rgba(148,163,184,0.82) 54%, rgba(112,131,154,0.34) 80%, transparent 100%)",
          filter: "blur(11px)",
          animation: `ts-cloud-breathe calc(${cloud.pulse} * 0.9) ease-in-out infinite`,
          animationDelay: `calc(${cloud.travelDelay} - 0.3s)`,
        }}
      />
      <div
        className="absolute inset-x-[16%] top-[18%] h-[16%] rounded-[999px]"
        style={{
          opacity: cloud.opacity * 0.34,
          background:
            "linear-gradient(180deg, rgba(255,255,255,0.58) 0%, rgba(255,255,255,0.16) 54%, transparent 100%)",
          filter: "blur(8px)",
        }}
      />
      <div
        className="absolute inset-x-[10%] bottom-[5%] h-[24%] rounded-[999px]"
        style={{
          opacity: cloud.opacity * 0.92,
          background:
            "radial-gradient(ellipse at 50% 52%, rgba(51,65,85,0.7) 0%, rgba(51,65,85,0.34) 58%, transparent 100%)",
          filter: "blur(12px)",
        }}
      />
      <div
        className="absolute inset-[8%] rounded-[999px]"
        style={{
          opacity: cloud.opacity * 0.42,
          background:
            "linear-gradient(180deg, rgba(255,255,255,0.12) 0%, rgba(112,131,154,0.18) 54%, rgba(51,65,85,0.38) 100%)",
          filter: "blur(14px)",
        }}
      />
    </>
  );
}

export default function DayClouds({ variant }: { variant: DayCloudVariant }) {
  const clouds = DAY_CLOUDS[variant].slice(0, 3);
  const opacityScale = variant === "app" ? 0.76 : 0.82;

  return (
    <div className="pointer-events-none absolute inset-0 z-[2] overflow-hidden">
      {clouds.map((cloud, index) => (
        <div
          key={`${variant}-${index}`}
          className="absolute will-change-transform"
          style={
            {
              top: cloud.top,
              left: cloud.left,
              width: `${cloud.width}px`,
              height: `${cloud.height}px`,
              opacity: opacityScale,
              animation: `ts-cloud-travel ${cloud.travelDuration} linear infinite`,
              animationDelay: cloud.travelDelay,
              "--ts-cloud-start-x": cloud.startX,
              "--ts-cloud-end-x": cloud.endX,
              "--ts-cloud-start-y": cloud.startY,
              "--ts-cloud-end-y": cloud.endY,
            } as CloudTravelStyle
          }
        >
          <div
            className="absolute inset-0 will-change-transform"
            style={{
              animation: `ts-cloud-float ${cloud.floatDuration} ease-in-out infinite`,
              animationDelay: cloud.floatDelay,
              filter: "drop-shadow(0 24px 42px rgba(51,65,85,0.3))",
            }}
          >
            <CloudShape cloud={cloud} />
          </div>
        </div>
      ))}
    </div>
  );
}
