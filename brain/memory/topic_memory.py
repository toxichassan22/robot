"""
Topic-Based Persistent Memory System for Robot AI.

Automatically extracts topics from conversations, saves them to JSON files,
and retrieves relevant context when the same topic comes up again.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Brain.TopicMemory")

# Topic keywords mapping (Arabic + English)
TOPIC_KEYWORDS = {
    "programming": ["كود", "برمجة", "بايثون", "python", "جافا", "code", "programming", "javascript", "html", "css", "api", "server", "database", "bug", "error", "function", "class"],
    "math": ["رياضيات", "حساب", "معادلة", "math", "equation", "calculus", "algebra", "geometry", "number", "حل", "جمع", "طرح", "ضرب", "قسمة"],
    "science": ["علم", "فيزياء", "كيمياء", "أحياء", "science", "physics", "chemistry", "biology", "atom", "molecule", "energy", "force"],
    "history": ["تاريخ", "حضارة", "حرب", "history", "civilization", "war", "ancient", "فراعنة", "مصر القديمة"],
    "geography": ["جغرافيا", "بلد", "قارة", "geography", "country", "continent", "ocean", "mountain"],
    "technology": ["تكنولوجيا", "تقنية", "ذكاء اصطناعي", "ai", "technology", "robot", "machine learning", "neural", "gpu", "cpu"],
    "personal": ["اسمي", "بحب", "عمري", "my name", "i like", "i love", "favorite", "hobby", "هواية", "شغلي", "دراستي"],
    "health": ["صحة", "دكتور", "مرض", "health", "doctor", "medicine", "diet", "exercise", "رياضة", "أكل"],
    "language": ["لغة", "عربي", "انجليزي", "ترجمة", "language", "arabic", "english", "translate", "grammar", "نحو"],
    "philosophy": ["فلسفة", "معنى", "حياة", "philosophy", "meaning", "life", "existence", "أخلاق", "ethics"],
    "robot": ["روبوت", "أريا", "حركة", "موتور", "سيرفو", "كاميرا", "robot", "aria", "motor", "servo", "sensor", "esp32"],
    "project": ["مشروع", "تخرج", "graduation", "project", "thesis", "بحث", "research"],
    "islam": ["إسلام", "قرآن", "حديث", "صلاة", "islam", "quran", "prayer", "دين", "دعاء"],
    "entertainment": ["فيلم", "أغنية", "لعبة", "movie", "song", "game", "music", "موسيقى", "مسلسل"],
    "general_chat": [],  # Fallback for unclassified conversations
}


class TopicMemory:
    """Manages topic-based persistent memory stored as JSON files."""

    def __init__(self, topics_dir: str = "./config/data/topics", max_entries_per_topic: int = 50):
        self.topics_dir = Path(topics_dir).resolve()
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries_per_topic
        logger.info(f"TopicMemory initialized at {self.topics_dir}")

    def extract_topic(self, text: str) -> str:
        """Extract the most relevant topic from the given text."""
        if not text:
            return "general_chat"

        text_lower = text.lower().strip()
        best_topic = "general_chat"
        best_score = 0

        for topic, keywords in TOPIC_KEYWORDS.items():
            if not keywords:
                continue
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_topic = topic

        return best_topic

    def _topic_path(self, topic: str) -> Path:
        """Get the file path for a topic."""
        safe_name = re.sub(r'[^\w\-]', '_', topic)
        return self.topics_dir / f"{safe_name}.json"

    def _load_topic(self, topic: str) -> list[dict]:
        """Load all entries for a topic."""
        path = self._topic_path(topic)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load topic '{topic}': {e}")
            return []

    def _save_topic(self, topic: str, entries: list[dict]) -> None:
        """Save entries for a topic, trimming if too many."""
        if len(entries) > self.max_entries:
            entries = entries[-self.max_entries:]
        path = self._topic_path(topic)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save topic '{topic}': {e}")

    def save_conversation(self, user_text: str, ai_response: str, topic: Optional[str] = None) -> str:
        """
        Save a conversation exchange under the appropriate topic.
        Returns the topic it was saved under.
        """
        if topic is None:
            topic = self.extract_topic(user_text + " " + ai_response)

        entries = self._load_topic(topic)
        entries.append({
            "ts": int(time.time() * 1000),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "user": user_text,
            "ai": ai_response,
        })
        self._save_topic(topic, entries)
        logger.debug(f"Saved conversation to topic '{topic}' ({len(entries)} entries)")
        return topic

    def get_topic_context(self, text: str, max_entries: int = 8) -> str:
        """
        Get relevant past conversation context for the given text.
        Returns a formatted string of past conversations on the same topic.
        """
        topic = self.extract_topic(text)
        entries = self._load_topic(topic)

        if not entries:
            return ""

        # Get the most recent entries
        recent = entries[-max_entries:]
        
        lines = [f"=== Previous conversations about '{topic}' ==="]
        for entry in recent:
            ts = entry.get("timestamp", "?")
            user = entry.get("user", "")
            ai = entry.get("ai", "")
            lines.append(f"[{ts}] User: {user}")
            lines.append(f"[{ts}] AI: {ai}")
            lines.append("")

        return "\n".join(lines)

    def get_all_topics(self) -> list[str]:
        """List all topics that have saved conversations."""
        topics = []
        for f in self.topics_dir.glob("*.json"):
            topics.append(f.stem)
        return sorted(topics)

    def get_topic_summary(self) -> dict[str, int]:
        """Get a summary of all topics and their entry counts."""
        summary = {}
        for f in self.topics_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                summary[f.stem] = len(data) if isinstance(data, list) else 0
            except Exception:
                summary[f.stem] = 0
        return summary

    def search_across_topics(self, query: str, max_results: int = 5) -> list[dict]:
        """Search for a query across all topics."""
        query_lower = query.lower()
        results = []

        for f in self.topics_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    user_text = str(entry.get("user", "")).lower()
                    ai_text = str(entry.get("ai", "")).lower()
                    if query_lower in user_text or query_lower in ai_text:
                        results.append({
                            "topic": f.stem,
                            **entry
                        })
                        if len(results) >= max_results:
                            return results
            except Exception:
                continue

        return results

    def find_exact_answer(self, query: str) -> Optional[str]:
        """
        Check if the exact (or highly similar) question has been asked before.
        Returns the AI's response if found, else None.
        """
        query_lower = query.lower().strip()
        # Remove common punctuation for better matching
        for char in ['؟', '?', '.', ',', '،', '!']:
            query_lower = query_lower.replace(char, '')
            
        if len(query_lower) < 5:
            return None # Ignore very short generic queries for caching

        for f in self.topics_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    continue
                
                # Check backwards to get the most recent matching answer
                for entry in reversed(entries):
                    user_text = str(entry.get("user", "")).lower().strip()
                    for char in ['؟', '?', '.', ',', '،', '!']:
                        user_text = user_text.replace(char, '')
                        
                    # If it's a 100% exact text match
                    if query_lower == user_text:
                        return entry.get("ai")
            except Exception:
                continue

        return None
