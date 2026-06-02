import React, { useState } from "react";

interface MaintenanceTrayProps {
  onHalt?: () => void;
}

export function MaintenanceTray({ onHalt }: MaintenanceTrayProps) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [sessionToken, setSessionToken] = useState<string | null>(
    localStorage.getItem("maintenance_session")
  );
  const [loading, setLoading] = useState(false);

  // Motion states
  const [speed, setSpeed] = useState(0.5);
  const [servoAngle, setServoAngle] = useState(90);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pin.trim()) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/settings/auth", {
        method: "POST",
        headers: {
          "x-robot-pin": pin.trim(),
        },
      });

      if (res.ok) {
        const data = await res.json();
        setSessionToken(data.sessionToken);
        localStorage.setItem("maintenance_session", data.sessionToken);
        setPin("");
      } else {
        const data = await res.json();
        setError(data.error === "invalid_pin" ? "رمز PIN غير صحيح" : "فشل التحقق من الهوية");
      }
    } catch (err) {
      setError("خطأ في الاتصال بالخادم");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setSessionToken(null);
    localStorage.removeItem("maintenance_session");
  };

  const sendMotionCommand = async (direction: string) => {
    if (!sessionToken) return;
    try {
      await fetch("/api/motion/move", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-robot-session": sessionToken,
        },
        body: JSON.stringify({
          direction,
          speed,
          durationMs: 1000,
        }),
      });
    } catch (err) {
      console.error("Failed to send motion command", err);
    }
  };

  const sendServoCommand = async (angle: number) => {
    if (!sessionToken) return;
    try {
      await fetch("/api/motion/servo", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-robot-session": sessionToken,
        },
        body: JSON.stringify({
          servoId: 0,
          angle,
        }),
      });
    } catch (err) {
      console.error("Failed to send servo command", err);
    }
  };

  const sendStop = async () => {
    if (!sessionToken) return;
    try {
      await fetch("/api/motion/stop", {
        method: "POST",
        headers: {
          "x-robot-session": sessionToken,
        },
      });
      if (onHalt) onHalt();
    } catch (err) {
      console.error("Failed to send stop command", err);
    }
  };

  if (!sessionToken) {
    return (
      <div className="flex flex-col items-center justify-center p-8 bg-slate-900/80 backdrop-blur-md border border-slate-700/50 rounded-xl max-w-md mx-auto my-8 shadow-2xl">
        <div className="w-12 h-12 bg-indigo-500/10 border border-indigo-500/30 rounded-full flex items-center justify-center text-indigo-400 mb-4 animate-pulse">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 00-2 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>
        <h3 className="text-slate-200 text-lg font-bold text-center">لوحة الصيانة المغلقة</h3>
        <p className="text-slate-500 text-xs text-center mt-1 mb-6">
          يرجى إدخال رمز PIN الخاص بالروبوت للوصول إلى أدوات التحكم اليدوية وتجاوز أفعال الروبوت الحالية.
        </p>

        <form onSubmit={handleVerify} className="w-full flex flex-col gap-4">
          <div>
            <input
              type="password"
              placeholder="رمز PIN للروبوت"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              className="w-full px-4 py-2.5 bg-slate-950/80 border border-slate-800 rounded-lg text-slate-200 text-center font-mono placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
              disabled={loading}
              maxLength={8}
            />
            {error && <div className="text-rose-500 text-xs mt-1.5 text-center">{error}</div>}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 disabled:bg-slate-800 text-white rounded-lg text-sm font-semibold transition-colors flex justify-center items-center"
          >
            {loading ? "جاري التحقق..." : "تأكيد الدخول"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex flex-col bg-slate-900/60 backdrop-blur-md border border-slate-700/50 rounded-xl p-5 shadow-2xl h-full">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
        <div>
          <h3 className="text-slate-200 text-sm font-bold flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
            لوحة الصيانة المباشرة
          </h3>
          <p className="text-slate-500 text-xs mt-0.5">تحكم يدوي كامل بوحدات الروبوت الميكانيكية.</p>
        </div>
        <button
          onClick={handleLogout}
          className="text-xs text-slate-500 hover:text-slate-300 font-medium px-2 py-1 bg-slate-950/80 border border-slate-800 rounded-md transition-colors"
        >
          خروج
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1">
        {/* Left Side: Directional controls */}
        <div className="flex flex-col justify-between">
          <span className="text-xs font-semibold text-slate-400">لوحة الحركة الاتجاهية</span>
          
          <div className="flex flex-col items-center justify-center my-4">
            {/* D-Pad controls */}
            <div className="grid grid-cols-3 gap-2 w-48 h-48">
              <div />
              <button
                onClick={() => sendMotionCommand("forward")}
                className="bg-slate-800 hover:bg-slate-700 active:bg-indigo-600 text-slate-200 rounded-lg flex items-center justify-center transition-colors shadow-md"
              >
                ▲
              </button>
              <div />

              <button
                onClick={() => sendMotionCommand("left")}
                className="bg-slate-800 hover:bg-slate-700 active:bg-indigo-600 text-slate-200 rounded-lg flex items-center justify-center transition-colors shadow-md"
              >
                ◀
              </button>
              <button
                onClick={sendStop}
                className="bg-rose-600/30 border border-rose-500 hover:bg-rose-600 active:bg-rose-700 text-rose-200 rounded-lg flex flex-col items-center justify-center transition-colors font-bold text-xs"
              >
                STOP
              </button>
              <button
                onClick={() => sendMotionCommand("right")}
                className="bg-slate-800 hover:bg-slate-700 active:bg-indigo-600 text-slate-200 rounded-lg flex items-center justify-center transition-colors shadow-md"
              >
                ▶
              </button>

              <div />
              <button
                onClick={() => sendMotionCommand("backward")}
                className="bg-slate-800 hover:bg-slate-700 active:bg-indigo-600 text-slate-200 rounded-lg flex items-center justify-center transition-colors shadow-md"
              >
                ▼
              </button>
              <div />
            </div>
          </div>

          {/* Speed slider */}
          <div>
            <div className="flex justify-between text-xs text-slate-400 mb-1.5">
              <span>سرعة المحركات</span>
              <span className="font-mono text-indigo-400">{(speed * 100).toFixed(0)}%</span>
            </div>
            <input
              type="range"
              min="0.1"
              max="1.0"
              step="0.05"
              value={speed}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}
              className="w-full accent-indigo-500 bg-slate-950 rounded-lg h-2"
            />
          </div>
        </div>

        {/* Right Side: Servo & Actuator Overrides */}
        <div className="flex flex-col justify-between">
          <span className="text-xs font-semibold text-slate-400 text-right md:text-left">محركات السيرفو ومحاور الدوران</span>
          
          <div className="space-y-5 my-4">
            {/* Servo 1 Slider */}
            <div>
              <div className="flex justify-between text-xs text-slate-400 mb-1.5">
                <span>سيرفو الكاميرا (محور X)</span>
                <span className="font-mono text-amber-500">{servoAngle}°</span>
              </div>
              <input
                type="range"
                min="0"
                max="180"
                value={servoAngle}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  setServoAngle(val);
                  sendServoCommand(val);
                }}
                className="w-full accent-amber-500 bg-slate-950 rounded-lg h-2"
              />
            </div>

            {/* Status grid */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 bg-slate-950/60 border border-slate-800/80 rounded-lg">
                <span className="text-slate-500 block">جهد البطارية</span>
                <span className="text-slate-300 font-mono font-semibold">12.4 V</span>
              </div>
              <div className="p-2.5 bg-slate-950/60 border border-slate-800/80 rounded-lg">
                <span className="text-slate-500 block">درجة الحرارة</span>
                <span className="text-slate-300 font-mono font-semibold">47°C</span>
              </div>
            </div>
          </div>

          <button
            onClick={sendStop}
            className="w-full py-2.5 bg-rose-600 hover:bg-rose-500 active:bg-rose-700 text-white rounded-lg text-sm font-semibold transition-colors flex justify-center items-center shadow-lg shadow-rose-600/20"
          >
            إيقاف طارئ للمحركات (Halt)
          </button>
        </div>
      </div>
    </div>
  );
}
