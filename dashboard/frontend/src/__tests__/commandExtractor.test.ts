import { extractCommandsFromText } from "../utils/commandExtractor";

test("extractCommandsFromText يستخرج أوامر عربية بسيطة", () => {
  const cmds = extractCommandsFromText("شغل المروحة واطفي النور");
  const kinds = cmds.map((c) => c.kind).sort();
  expect(kinds).toEqual(["set_fan", "set_led"]);
});

