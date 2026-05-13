export type ExtractedCommand = {
  kind: "set_fan" | "set_led" | "set_state"
  payload: Record<string, unknown>
  label: string
}

export function extractCommandsFromText(text: string): ExtractedCommand[] {
  const t = (text || "").toLowerCase()
  const out: ExtractedCommand[] = []

  const normalized = t.replace(/(^|\s)و(?=(?:اطفي|اطفى|شغل|تشغيل|افتح|اقفل|قفل|sleep|نام|نامي|نامى|نوم))/g, "$1|")
  const parts = normalized
    .split(/[|،\n\r.;]+/g)
    .map((x) => x.trim())
    .filter(Boolean)

  for (const p of parts) {
    const wantsSleep = /(sleep|نام|نامي|نامى|نوم)/.test(p)
    if (wantsSleep) {
      out.push({ kind: "set_state", payload: { mode: "sleep", eye: "closed" }, label: "وضع النوم" })
    }

    const fan = /(fan|مروحه|مروحة)/.test(p)
    if (fan) {
      const on = /(\bon\b|تشغيل|شغل|افتح)/.test(p)
      const off = /(\boff\b|اطفي|اطفى|اقفل|قفل)/.test(p)
      if (on && !off) out.push({ kind: "set_fan", payload: { state: "on" }, label: "تشغيل المروحة" })
      else if (off && !on) out.push({ kind: "set_fan", payload: { state: "off" }, label: "إيقاف المروحة" })
    }

    const led = /(led|light|نور|ضوء|لمبه|لمبة)/.test(p)
    if (led) {
      const on = /(\bon\b|تشغيل|شغل|افتح)/.test(p)
      const off = /(\boff\b|اطفي|اطفى|اقفل|قفل)/.test(p)
      if (on && !off) out.push({ kind: "set_led", payload: { id: 1, state: "on" }, label: "تشغيل النور" })
      else if (off && !on) out.push({ kind: "set_led", payload: { id: 1, state: "off" }, label: "إيقاف النور" })
    }
  }

  return out
}
