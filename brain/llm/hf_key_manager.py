"""HuggingFace API Key Manager — Sequential rotation with auto-recovery.

Manages multiple HF API keys stored in a JSON file.
When a key fails (401/429/402), it automatically rotates to the next key
**in order** (not random). Exhausted keys are retried after 30 days.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Brain.HFKeyManager")

# Keys that have been exhausted are retried after this many days
EXHAUSTED_RETRY_DAYS = 30

# HTTP status codes that indicate a key is exhausted or invalid
EXHAUSTED_STATUS_CODES = {429, 402}  # rate-limit / quota exceeded
INVALID_STATUS_CODES = {401, 403}     # unauthorized / forbidden


class HFKeyManager:
    """Manages a pool of HuggingFace API keys with sequential rotation."""

    def __init__(self, keys_file: str):
        self._keys_file = Path(keys_file)
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {"keys": [], "current_index": 0}
        self._load()

    # ── persistence ──────────────────────────────────────────────────

    def _load(self) -> None:
        """Read keys from disk."""
        if not self._keys_file.exists():
            logger.warning("HF keys file not found: %s — starting with empty pool", self._keys_file)
            self._save()
            return
        try:
            with open(self._keys_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self._data = raw
                # Auto-recover exhausted keys older than EXHAUSTED_RETRY_DAYS
                self._auto_recover()
            else:
                logger.error("HF keys file has invalid format, resetting.")
                self._data = {"keys": [], "current_index": 0}
        except Exception as e:
            logger.error("Failed to load HF keys file: %s", e)

    def _save(self) -> None:
        """Write current state to disk."""
        try:
            self._keys_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._keys_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save HF keys file: %s", e)

    def reload(self) -> None:
        """Re-read keys from disk (called when web UI changes the file)."""
        with self._lock:
            self._load()

    # ── auto-recovery ────────────────────────────────────────────────

    def _auto_recover(self) -> None:
        """Re-activate exhausted keys that have been waiting for >= 30 days."""
        now = datetime.utcnow()
        changed = False
        for entry in self._data.get("keys", []):
            if entry.get("status") == "exhausted" and entry.get("exhausted_at"):
                try:
                    exhausted_at = datetime.fromisoformat(entry["exhausted_at"])
                    if now - exhausted_at >= timedelta(days=EXHAUSTED_RETRY_DAYS):
                        entry["status"] = "active"
                        entry["fail_count"] = 0
                        entry["exhausted_at"] = None
                        changed = True
                        logger.info("Auto-recovered key %s (%s) after %d days",
                                    entry.get("id"), entry.get("label"), EXHAUSTED_RETRY_DAYS)
                except Exception:
                    pass
        if changed:
            self._save()

    # ── key access ───────────────────────────────────────────────────

    def _active_keys(self) -> List[Dict[str, Any]]:
        """Return only keys with status == 'active'."""
        return [k for k in self._data.get("keys", []) if k.get("status") == "active"]

    def get_current_key(self) -> Optional[str]:
        """Return the current active API key string, or None if no keys available."""
        with self._lock:
            keys = self._data.get("keys", [])
            if not keys:
                return None
            idx = self._data.get("current_index", 0) % len(keys)
            # Walk forward to find the first active key starting from idx
            for offset in range(len(keys)):
                candidate = keys[(idx + offset) % len(keys)]
                if candidate.get("status") == "active":
                    # Update current_index to point to this key
                    self._data["current_index"] = (idx + offset) % len(keys)
                    return candidate.get("key")
            return None  # all keys exhausted/invalid/disabled

    def get_current_key_id(self) -> Optional[str]:
        """Return the id of the current key."""
        with self._lock:
            keys = self._data.get("keys", [])
            if not keys:
                return None
            idx = self._data.get("current_index", 0) % len(keys)
            return keys[idx].get("id")

    # ── rotation ─────────────────────────────────────────────────────

    def mark_exhausted(self, key_id: Optional[str] = None, status: str = "exhausted") -> None:
        """Mark the current (or specified) key as exhausted/invalid and save."""
        with self._lock:
            keys = self._data.get("keys", [])
            target_id = key_id
            if target_id is None:
                idx = self._data.get("current_index", 0) % len(keys) if keys else 0
                target_id = keys[idx].get("id") if idx < len(keys) else None

            for entry in keys:
                if entry.get("id") == target_id:
                    entry["status"] = status
                    entry["fail_count"] = entry.get("fail_count", 0) + 1
                    entry["exhausted_at"] = datetime.utcnow().isoformat()
                    logger.warning("Key %s (%s) marked as %s (fail #%d)",
                                   entry.get("id"), entry.get("label"), status, entry["fail_count"])
                    break
            self._save()

    def rotate_to_next(self) -> Optional[str]:
        """Move to the next key in order. Returns the new key string or None."""
        with self._lock:
            keys = self._data.get("keys", [])
            if not keys:
                return None
            current_idx = self._data.get("current_index", 0) % len(keys)
            # Try each key after the current one, in order
            for offset in range(1, len(keys) + 1):
                next_idx = (current_idx + offset) % len(keys)
                candidate = keys[next_idx]
                if candidate.get("status") == "active":
                    self._data["current_index"] = next_idx
                    self._save()
                    logger.info("Rotated to key #%d: %s (%s)",
                                next_idx, candidate.get("id"), candidate.get("label"))
                    return candidate.get("key")
            logger.error("All HF API keys exhausted! No active keys remaining.")
            return None

    def mark_current_exhausted_and_rotate(self, status: str = "exhausted") -> Optional[str]:
        """Convenience: mark current key, then rotate. Returns new key or None."""
        self.mark_exhausted(status=status)
        return self.rotate_to_next()

    def record_success(self) -> None:
        """Record that the current key was used successfully."""
        with self._lock:
            keys = self._data.get("keys", [])
            if not keys:
                return
            idx = self._data.get("current_index", 0) % len(keys)
            keys[idx]["last_used_at"] = datetime.utcnow().isoformat()
            self._save()

    # ── CRUD for web UI ──────────────────────────────────────────────

    def get_all_keys_status(self) -> List[Dict[str, Any]]:
        """Return a sanitized list of all keys with their status (no raw key exposed fully)."""
        with self._lock:
            result = []
            current_idx = self._data.get("current_index", 0)
            for i, entry in enumerate(self._data.get("keys", [])):
                result.append({
                    "id": entry.get("id"),
                    "label": entry.get("label", ""),
                    "key_preview": entry.get("key", "")[:8] + "..." if entry.get("key") else "",
                    "status": entry.get("status", "active"),
                    "added_at": entry.get("added_at"),
                    "last_used_at": entry.get("last_used_at"),
                    "fail_count": entry.get("fail_count", 0),
                    "exhausted_at": entry.get("exhausted_at"),
                    "is_current": i == current_idx,
                })
            return result

    def add_key(self, key: str, label: str = "") -> Dict[str, Any]:
        """Add a new API key to the pool."""
        with self._lock:
            new_entry = {
                "id": f"key_{uuid.uuid4().hex[:8]}",
                "key": key.strip(),
                "label": label.strip() or f"مفتاح {len(self._data.get('keys', [])) + 1}",
                "status": "active",
                "added_at": datetime.utcnow().isoformat(),
                "last_used_at": None,
                "fail_count": 0,
                "exhausted_at": None,
            }
            self._data.setdefault("keys", []).append(new_entry)
            self._save()
            logger.info("Added new HF key: %s (%s)", new_entry["id"], new_entry["label"])
            return {"id": new_entry["id"], "label": new_entry["label"]}

    def remove_key(self, key_id: str) -> bool:
        """Remove a key by its id."""
        with self._lock:
            keys = self._data.get("keys", [])
            before = len(keys)
            self._data["keys"] = [k for k in keys if k.get("id") != key_id]
            if len(self._data["keys"]) < before:
                # Fix current_index if needed
                if self._data["current_index"] >= len(self._data["keys"]):
                    self._data["current_index"] = 0
                self._save()
                logger.info("Removed HF key: %s", key_id)
                return True
            return False

    def reset_key(self, key_id: str) -> bool:
        """Re-activate a key (set status back to active)."""
        with self._lock:
            for entry in self._data.get("keys", []):
                if entry.get("id") == key_id:
                    entry["status"] = "active"
                    entry["fail_count"] = 0
                    entry["exhausted_at"] = None
                    self._save()
                    logger.info("Reset HF key: %s (%s)", key_id, entry.get("label"))
                    return True
            return False

    def disable_key(self, key_id: str) -> bool:
        """Manually disable a key."""
        with self._lock:
            for entry in self._data.get("keys", []):
                if entry.get("id") == key_id:
                    entry["status"] = "disabled"
                    self._save()
                    logger.info("Disabled HF key: %s (%s)", key_id, entry.get("label"))
                    return True
            return False

    def reorder_keys(self, key_ids: List[str]) -> bool:
        """Reorder keys according to the given id list."""
        with self._lock:
            keys = self._data.get("keys", [])
            id_map = {k["id"]: k for k in keys}
            # Build new order — include only valid ids, append any missing at end
            new_order = []
            seen = set()
            for kid in key_ids:
                if kid in id_map and kid not in seen:
                    new_order.append(id_map[kid])
                    seen.add(kid)
            # Append any keys not mentioned in the reorder list
            for k in keys:
                if k["id"] not in seen:
                    new_order.append(k)
            self._data["keys"] = new_order
            self._data["current_index"] = 0
            self._save()
            logger.info("Reordered HF keys: %s", key_ids)
            return True

    def get_status_summary(self) -> Dict[str, Any]:
        """Get overall system status."""
        with self._lock:
            keys = self._data.get("keys", [])
            active_count = sum(1 for k in keys if k.get("status") == "active")
            current_idx = self._data.get("current_index", 0)
            current_key = keys[current_idx] if current_idx < len(keys) else None
            return {
                "total_keys": len(keys),
                "active_keys": active_count,
                "current_index": current_idx,
                "current_key_id": current_key.get("id") if current_key else None,
                "current_key_label": current_key.get("label") if current_key else None,
                "current_key_status": current_key.get("status") if current_key else None,
                "exhausted_retry_days": EXHAUSTED_RETRY_DAYS,
            }

    # ── helper for error classification ──────────────────────────────

    @staticmethod
    def is_key_error(error: Exception) -> str | None:
        """Classify an error. Returns 'exhausted', 'invalid', or None (not a key error)."""
        err_str = str(error).lower()
        
        # Avoid treating model-specific errors or bad requests as key errors
        if "model" in err_str and ("not found" in err_str or "not support" in err_str or "not exist" in err_str or "invalid_request" in err_str):
            return None
        if "provider or policy" in err_str or "not valid" in err_str:
            return None
            
        # Check for HTTP status codes in the error message
        for code in EXHAUSTED_STATUS_CODES:
            if str(code) in err_str or "rate" in err_str or "quota" in err_str or "limit" in err_str:
                return "exhausted"
        for code in INVALID_STATUS_CODES:
            if str(code) in err_str or "unauthorized" in err_str or "forbidden" in err_str or "invalid" in err_str:
                return "invalid"
        return None
