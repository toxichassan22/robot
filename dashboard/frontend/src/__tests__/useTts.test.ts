import { pickBestVoice } from "../hooks/useTts";

test("pickBestVoice يفضل الأصوات المحلية عند تساوي اللغة", () => {
  const voices = [
    { voiceURI: "cloud1", name: "Cloud", lang: "ar-EG", localService: false, default: false },
    { voiceURI: "local1", name: "Local", lang: "ar-EG", localService: true, default: false },
  ] as unknown as SpeechSynthesisVoice[];
  const v = pickBestVoice({ voices, lang: "ar-EG" });
  expect(v?.voiceURI).toBe("local1");
});
