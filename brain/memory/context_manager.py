import json
import logging
from collections import deque
from datetime import datetime

logger = logging.getLogger("Brain.ContextManager")

class ContextManager:
    def __init__(self, max_history=5):
        self.max_history = max_history
        self.vision_history = deque(maxlen=max_history)

    def add_vision_state(self, entities: list, action: str, raw_description: str):
        state = {
            "timestamp": datetime.now().isoformat(),
            "entities": entities,
            "action": action,
            "raw": raw_description
        }
        self.vision_history.append(state)
        logger.debug(f"Added vision state. Current queue size: {len(self.vision_history)}")

    def get_vision_context_json(self) -> str:
        """Returns the sliding window memory of vision states as a JSON string."""
        if not self.vision_history:
            return json.dumps({"status": "no_vision_data_available"})
        
        return json.dumps(list(self.vision_history), ensure_ascii=False, indent=2)

# Global singleton for use across the app
context_manager = ContextManager()
