export function normalizeArabic(text: string): string {
    if (!text) return text;

    let t = text.normalize("NFKC");

    const map: Record<string, string> = {
        "ی": "ي",
        "ک": "ك",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
        "ـ": "",
        "\u200f": "",
        "\u200e": "",
        "\u202a": "",
        "\u202b": "",
        "\u202c": "",
    };

    for (const k in map) {
        t = t.split(k).join(map[k]);
    }

    return t;
}
