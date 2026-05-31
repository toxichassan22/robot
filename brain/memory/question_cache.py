"""
Folder-Based Question Cache for Robot AI.

Structure:
    cache_dir/
        صحة/                  ← topic folder
            عامل_اي.json      ← question file (filename = question)
            كيف_الحال.json
            ازيك.json
        ترحيب/
            سلام_عليكم.json
            اهلا.json

Each file contains:
    {"answer": "...", "ts": 1234567890, "hits": 3}

Lookup checks all topic folders for a matching filename — O(n) where n = number of topic folders.
Exact match is fast (filesystem check); fuzzy fallback scans each folder's files.
All models share this cache so none of them waste time re-answering known questions.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Brain.QuestionCache")

# ── Topic classification ────────────────────────────────────────────
TOPIC_MAP = {
    "صحة": ["عامل", "ازيك", "اخبارك", "كيفك", "صحتك", "تعبان", "كويس", "بخير", "الحمد"],
    "ترحيب": ["سلام", "اهلا", "صباح", "مساء", "نهارك", "يا_عسل", "يا_حبيبي", "منور"],
    "وداع": ["باي", "مع_السلامه", "سلام", "يلا", "هروح"],
    "هوية": ["اسمك", "مين_انت", "انت_مين", "بتعمل_ايه", "وظيفتك"],
    "شكر": ["شكرا", "تسلم", "ميرسي", "جزاك", "يعطيك"],
    "مشاعر": ["بحبك", "وحشتني", "زعلان", "فرحان", "مبسوط", "حزين"],
    "برمجة": ["كود", "برمجة", "بايثون", "python", "javascript", "api", "bug", "error"],
    "رياضيات": ["رياضيات", "حساب", "معادلة", "math", "جمع", "طرح", "ضرب"],
    "علوم": ["فيزياء", "كيمياء", "أحياء", "physics", "chemistry", "biology"],
    "تاريخ": ["تاريخ", "حضارة", "فراعنة", "حرب", "history"],
    "تكنولوجيا": ["ذكاء_اصطناعي", "ai", "تكنولوجيا", "robot", "machine"],
    "دين": ["قرآن", "صلاة", "إسلام", "حديث", "دعاء", "دين"],
    "ترفيه": ["فيلم", "أغنية", "لعبة", "مسلسل", "موسيقى"],
    "عام": [],  # fallback
}


def _sanitize_filename(text: str) -> str:
    """Turn a question into a safe filename (keeps Arabic, removes junk)."""
    t = text.strip()
    # Remove punctuation
    for ch in "؟?!.,:;،\"'()[]{}":
        t = t.replace(ch, "")
    # Collapse whitespace → underscore
    t = re.sub(r"\s+", "_", t.strip())
    # Remove any remaining unsafe chars (keep Arabic, alphanumerics, underscores, hyphens)
    t = re.sub(r"[^\w\u0600-\u06FF\-]", "", t)
    # Limit length
    if len(t) > 120:
        t = t[:120]
    return t or "unknown"


def _classify_topic(text: str) -> str:
    """Pick the best topic folder for the given text."""
    lower = text.lower().strip()
    best, best_score = "عام", 0
    for topic, keywords in TOPIC_MAP.items():
        if not keywords:
            continue
        score = sum(1 for kw in keywords if kw.replace("_", " ") in lower or kw in lower)
        if score > best_score:
            best, best_score = topic, score
    return best


class QuestionCache:
    """Filesystem-based question cache. Folder = topic, file = question."""

    def __init__(self, cache_dir: str = "./config/data/question_cache"):
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"QuestionCache initialized at {self.cache_dir}")

    # ── Write ────────────────────────────────────────────────────────

    def save(self, question: str, answer: str, topic: str | None = None) -> Path:
        """Save an answer for a question. Returns the file path."""
        if not question.strip() or not answer.strip():
            return Path()

        topic = topic or _classify_topic(question)
        folder = self.cache_dir / topic
        folder.mkdir(parents=True, exist_ok=True)

        fname = _sanitize_filename(question) + ".json"
        fpath = folder / fname

        # If file exists, update it (keep hit counter)
        data = {"answer": answer, "ts": int(time.time()), "hits": 0}
        if fpath.exists():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    old = json.load(f)
                data["hits"] = old.get("hits", 0)
            except Exception:
                pass

        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Cached Q: '{question}' → {topic}/{fname}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

        return fpath

    # ── Read (fast path — direct filename match) ─────────────────────

    def lookup(self, question: str) -> Optional[str]:
        """
        Instant lookup: check if a file with this question name exists
        in ANY topic folder. Returns the cached answer or None.
        """
        fname = _sanitize_filename(question) + ".json"

        # Search all topic folders
        for folder in self.cache_dir.iterdir():
            if not folder.is_dir():
                continue
            fpath = folder / fname
            if fpath.exists():
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # Bump hit counter
                    data["hits"] = data.get("hits", 0) + 1
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Cache HIT: '{question}' (hits={data['hits']})")
                    return data.get("answer")
                except Exception as e:
                    logger.error(f"Cache read error: {e}")
                    continue
        return None

    # ── Fuzzy read (check similar questions in same topic) ───────────

    def lookup_similar(self, question: str) -> Optional[str]:
        """
        If exact match fails, check other files in the same topic folder
        for questions that share most words with the input.
        """
        topic = _classify_topic(question)
        folder = self.cache_dir / topic
        if not folder.exists():
            return None

        q_words = set(question.lower().strip().split())
        if len(q_words) < 2:
            return None  # Too short for fuzzy matching

        best_answer = None
        best_overlap = 0.0

        for fpath in folder.glob("*.json"):
            # Decode filename back to words
            file_words = set(fpath.stem.replace("_", " ").lower().split())
            if not file_words:
                continue

            # Jaccard similarity
            intersection = q_words & file_words
            union = q_words | file_words
            similarity = len(intersection) / len(union) if union else 0

            if similarity > 0.4 and similarity > best_overlap:
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    best_answer = data.get("answer")
                    best_overlap = similarity
                except Exception:
                    continue

        if best_answer:
            logger.info(f"Fuzzy cache HIT for '{question}' (overlap={best_overlap:.0%})")
        return best_answer

    # ── Combined lookup (exact → fuzzy) ──────────────────────────────

    def find_answer(self, question: str) -> Optional[str]:
        """Try exact match first, then fuzzy match."""
        answer = self.lookup(question)
        if answer:
            return answer
        return self.lookup_similar(question)

    # ── Stats ────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get cache statistics: topics, total questions, etc."""
        stats = {"topics": {}, "total_questions": 0, "total_hits": 0}
        for folder in self.cache_dir.iterdir():
            if not folder.is_dir():
                continue
            count = 0
            hits = 0
            for fpath in folder.glob("*.json"):
                count += 1
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    hits += data.get("hits", 0)
                except Exception:
                    pass
            stats["topics"][folder.name] = {"questions": count, "hits": hits}
            stats["total_questions"] += count
            stats["total_hits"] += hits
        return stats
