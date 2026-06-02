from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
import json
import random
import logging

from brain.config import BrainConfig
from brain.llm.ollama_client import OllamaClient
from brain.llm.openai_client import OpenAIClient
from brain.memory.sqlite_memory import SqliteMemory
from brain.types import ActionCommand, PerceptionState

logger = logging.getLogger("Brain.Planner")


class Planner:
    async def plan(self, perception: PerceptionState) -> ActionCommand:
        raise NotImplementedError


@dataclass
class RuleBasedPlanner(Planner):
    memory: SqliteMemory
    cfg: BrainConfig

    def _is_visual_question(self, text: str) -> bool:
        visual_kws = [
            "شايف", "لابس", "اقرا", "اقرأ", "مكتوب", "قدامك", "ولد ولا بنت", "بنت ولا ولد", "شكلي",
            "روشتة", "روشته", "ورقة", "ورقه", "معايا إيه", "معايا ايه", "إيه ده", "ايه ده",
            "الكاميرا", "الكاميرا بتاعتي", "صورة", "صوره"
        ]
        return any(k in text.lower() for k in visual_kws)

    def _quick_visual_reply(self, question: str, vision: dict | None) -> str:
        if not isinstance(vision, dict):
            return ""
        q = str(question or "").strip().lower()
        face = vision.get("face") if isinstance(vision.get("face"), dict) else {}
        pose = vision.get("pose") if isinstance(vision.get("pose"), dict) else {}
        ocr = vision.get("ocr") if isinstance(vision.get("ocr"), dict) else {}
        appearance = face.get("appearance") if isinstance(face.get("appearance"), dict) else {}
        shirt_color = str(appearance.get("shirt_color") or "").strip()
        ocr_text = str(ocr.get("text") or "").strip()
        if ocr_text and any(k in q for k in ("اقرا", "اقرأ", "مكتوب", "read", "text", "ocr")):
            return f"النص المقروء: {ocr_text}"
        if "لابس" in q and shirt_color:
            return f"إنت لابس تيشيرت {shirt_color}."
        if "شايف" in q and shirt_color:
            return f"شايفك قدامي، وإنت لابس تيشيرت {shirt_color}."
        if "شايف" in q and (face or pose):
            return "شايفك قدامي."
        return ""

    def _llm_vision_answer(self, question: str, vision_desc: str) -> str:
        provider = str(self.cfg.provider or "ollama").strip().lower()
        if provider in ("openrouter", "huggingface") or self.cfg.hf_api_key:
            model = self.cfg.hf_model or "moonshotai/kimi-k2.6:free"
        elif provider == "gemini" or self.cfg.google_api_key:
            model = self.cfg.gemini_model
        else:
            model = self.cfg.ollama_model
        
        if not model:
            return ""
        question_type = "scene"
        q = str(question or "")
        if "لابس" in q:
            question_type = "clothes"
        elif "اقرا" in q or "اقرأ" in q or "مكتوب" in q:
            question_type = "reading"
        system = (
            "You convert complex robot vision descriptions into short, friendly spoken answers. "
            "Answer ONLY in Egyptian Slang (Ammiya). "
            "Prioritize a natural, helpful tone. "
            "Speak directly to the user. "
            "If the description is in English, translate the meaning to Egyptian Slang. "
            "Keep it short and clear. "
            "Example: If you see one person, say 'أيوة، أنا شايفك قدامي يا صاحبي ومش شايف حد تاني دلوقتي'. "
        )
        user = json.dumps(
            {"question_type": question_type, "question": question, "scene_description": vision_desc},
            ensure_ascii=False,
        )
        try:
            if provider in ("openrouter", "huggingface") or self.cfg.hf_api_key:
                from brain.llm.huggingface_client import HuggingFaceClient
                try:
                    from brain.pi5.web_ui_backend.routers.api_keys import _get_key_manager
                    key_manager = _get_key_manager()
                except Exception:
                    key_manager = None
                client = HuggingFaceClient(api_key=self.cfg.hf_api_key, default_model=model, key_manager=key_manager)
                return client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.1,
                ).strip()
            elif provider == "gemini" or self.cfg.google_api_key:
                from brain.llm.gemini_client import GeminiClient
                client = GeminiClient(api_key=self.cfg.google_api_key)
                return client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.1,
                    response_mime_type="text/plain"
                ).strip()
            else:
                client = OllamaClient(base_url=self.cfg.ollama_base_url)
                return client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.1,
                    device=self.cfg.llm_device,
                ).strip()
        except Exception as e:
            return ""

    async def _visual_reply(self, question: str, vision_desc: str, vision: dict | None = None) -> str:
        quick = self._quick_visual_reply(question, vision)
        if quick:
            return quick
        desc = str(vision_desc or "").strip()
        if not desc:
            return "مش شايف بوضوح دلوقتي."
            
        # Always try to process the description through the LLM to get a natural Egyptian response
        try:
            reply = await asyncio.to_thread(self._llm_vision_answer, question, desc)
            if reply:
                return reply
        except Exception as e:
            logger.error(f"Visual LLM conversion failed: {e}")
            
        return "شايف قدامي حاجات بس مش عارف أوصفها بالظبط دلوقتي."

    async def plan(self, perception: PerceptionState) -> ActionCommand:
        gestures = perception.gestures or {}
        primary = gestures.get("primary")
        primary_type = ""
        
        # Handle simple string format from new gesture detector
        if isinstance(primary, str):
            primary_type = primary.strip().lower()
        # Fallback for old dict format just in case
        elif isinstance(primary, dict):
            gt = primary.get("gesture_type")
            if isinstance(gt, str):
                primary_type = gt.strip().lower()

        if primary_type and bool(self.cfg.gesture_detection_enabled):
            binding = ""
            if isinstance(self.cfg.gesture_bindings, dict):
                binding_raw = self.cfg.gesture_bindings.get(primary_type)
                if isinstance(binding_raw, str):
                    binding = binding_raw.strip().lower()

            # Default explicit bindings if not in config
            if not binding:
                if primary_type == "wave":
                    binding = "greet"
                elif primary_type == "thumbs_up":
                    binding = "positive_feedback"
                elif primary_type == "thumbs_down":
                    binding = "negative_feedback"
                elif primary_type in {"heart", "finger_heart"}:
                    binding = "affection"
                elif primary_type == "ok":
                    binding = "positive_feedback"
                elif primary_type in {"open_palm", "paper"}:
                    binding = "greet"
                elif primary_type == "i_love_you":
                    binding = "affection"
            
            if binding == "rps" or primary_type in {"rock", "paper", "scissors"}:
                 # Implicit RPS if gesture is one of them
                if primary_type in {"rock", "paper", "scissors"}:
                     binding = "rps"

            if binding == "rps" and primary_type in {"rock", "paper", "scissors"}:
                robot = random.choice(["rock", "paper", "scissors"])
                user = primary_type
                winner = "tie"
                if (user, robot) in {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}:
                    winner = "user"
                elif (robot, user) in {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}:
                    winner = "robot"
                arabic = {"rock": "حجر", "paper": "ورقة", "scissors": "مقص"}
                if winner == "tie":
                    txt = f"أنا: {arabic[robot]} — تعادل!"
                elif winner == "user":
                    txt = f"أنا: {arabic[robot]} — أنت كسبت!"
                else:
                    txt = f"أنا: {arabic[robot]} — أنا كسبت!"
                await self.memory.append_short_term(role="assistant", content=f"rps:{user}:{robot}:{winner}")
                return ActionCommand(kind="say", payload={"text": txt})

            if binding == "follow":
                return ActionCommand(kind="motion", payload={"direction": "forward", "speed": 0.4, "duration_ms": 800})

            if binding == "greet":
                return ActionCommand(kind="say", payload={"text": "أهلًا، أنا معاك دلوقتي."})

            if binding == "positive_feedback":
                return ActionCommand(kind="say", payload={"text": "تمام، شكرًا!"})

            if binding == "negative_feedback":
                return ActionCommand(kind="say", payload={"text": "تمام، هحاول أتحسن."})

            if binding == "affection":
                return ActionCommand(kind="say", payload={"text": "شوفت الإشارة. حركة لطيفة جدًا."})

        raw_text = (perception.text or "").strip()
        text = raw_text.lower()
        if text:
            words = text.split()
            if "نام" in words or "sleep" in words: return ActionCommand(kind="set_state",payload={"mode":"sleep","eye":"closed"})
            if "ورايا" in text or "تعالى" in text or "اتبعني" in text:return ActionCommand(kind="motion",payload={"direction":"forward","speed":0.35,"duration_ms":1200})
            if "قف" in text or "وقف" in text or "stop" in text:return ActionCommand(kind="motion",payload={"direction":"stop","speed":0.0,"duration_ms":0})
            if "يمين" in text:return ActionCommand(kind="motion",payload={"direction":"right","speed":0.3,"duration_ms":700})
            if "شمال" in text:return ActionCommand(kind="motion",payload={"direction":"left","speed":0.3,"duration_ms":700})
            if "لورا" in text or "ارجع" in text:return ActionCommand(kind="motion",payload={"direction":"backward","speed":0.3,"duration_ms":900})
            if self._is_visual_question(text):return ActionCommand(kind="say",payload={"text":await self._visual_reply(raw_text, perception.vision_desc or "", perception.vision)})                                                                                       
        sensors = perception.sensors or {}
        temp = sensors.get("temp_c")

        # motion = sensors.get("motion") # Legacy sensor check
        if perception.motion_detected:
            return ActionCommand(kind="set_led", payload={"id": 1, "state": "on"})
        if isinstance(temp, (int, float)) and temp >= 30:
            return ActionCommand(kind="set_fan", payload={"state": "on"})
        return ActionCommand(kind="noop", payload={})


@dataclass
class HybridPlanner(Planner):
    rule: RuleBasedPlanner
    llm: Planner | None

    async def plan(self, perception: PerceptionState) -> ActionCommand:
        rule_action = await self.rule.plan(perception)
        if rule_action.kind != "noop":
            return rule_action
        if self.llm is None:
            return rule_action
        return await self.llm.plan(perception)


@dataclass
class FallbackLlmPlanner(Planner):
    planners: list[Planner]

    async def plan(self, perception: PerceptionState) -> ActionCommand:
        last_error = None
        for p in self.planners:
            action = await p.plan(perception)
            if action.kind == "noop" and action.payload.get("reason") == "llm_error":
                last_error = action
                continue
            return action
        return last_error or ActionCommand(kind="noop", payload={"reason": "all_planners_failed"})


@dataclass
class LlmPlanner(Planner):
    memory: SqliteMemory
    provider: str
    base_url: str
    model: str
    device: str = "cpu"
    api_key: str = ""
    allowed_topics: tuple[str, ...] = ()
    robot_language: str = "ar-EG"

    def _spoken_response_instructions(self) -> str:
        language = str(self.robot_language or "").strip().lower()
        if language.startswith("ar-eg"):
            return (
                "Write exclusively in Egyptian Slang. Prioritize phonetic spelling over formal grammar. "
                "Respond with the EXACT length or detail requested by the user. "
                "Maintain your identity as 'Aria', a smart robot. Distinguish between real people and fictional characters. "
                "GENDER & NUMBER: Always address the user in the SINGULAR form unless you explicitly see multiple people in vision. "
                "Check 'perception.vision' for gender: If gender is 'male', use masculine forms (e.g., 'يا صاحبي', 'عامل إيه'). If 'female', use feminine forms (e.g., 'يا صاحبتي', 'عاملة إيه'). If vision is missing, default to masculine. "
                "Use ONLY authentic Egyptian vocabulary: Use 'بقى' NOT 'صار', 'عشان' NOT 'لكي', 'هـ' prefix NOT 'سوف'. "
                "The tone should be like a native Egyptian friend chatting. "
                "If the user simply calls your name, reply concisely and naturally. Do NOT repeat the user's call. "
                "Do NOT exaggerate or stretch letters unnaturally. "
                "Ask one direct follow-up if the request is unclear."
            )
        if language.startswith("ar"):
            return (
                "If kind='say', the reply text must be clear spoken Arabic in Arabic script, short and easy to say aloud."
            )
        return (
            "If kind='say', keep the reply concise, natural, and easy to speak aloud in the configured user language."
        )

    async def plan(self, perception: PerceptionState) -> ActionCommand:
        # --- CONTEXT-AWARE MEMORY ---
        user_text = (perception.text or "").strip()
        is_lightweight = len(user_text.split()) <= 12 and not perception.vision and not perception.vision_desc
        
        # For very short follow-up queries (like "and now?", "so?"), we MUST use more history to understand the subject
        is_short_followup = len(user_text.split()) <= 2
        memory_limit = 12 if (is_lightweight or is_short_followup) else 15
        recent_raw = await self.memory.get_recent_short_term(limit=memory_limit)
        
        recent = []
        import json
        for msg in recent_raw:
            cleaned_msg = {"role": msg["role"], "content": msg["content"]}
            if msg["role"] == "assistant":
                try:
                    payload = json.loads(msg["content"])
                    if payload.get("kind") == "say":
                        cleaned_msg["content"] = payload.get("payload", {}).get("text", "")
                    else:
                        cleaned_msg["content"] = f"[Action: {payload.get('kind')}]"
                except:
                    pass
            recent.append(cleaned_msg)
        
        recent_feedback = []
                
        # --- LONG TERM MEMORY INJECTION ---
        long_term_facts_dict = await self.memory.get_all_long_term_facts()
        long_term_facts = [{"key": k, "value": v} for k, v in long_term_facts_dict.items()]
                
        system = (
            "You are a robotics decision module. Produce only strict JSON with keys: kind (string) and payload (object). "
            "No markdown, no extra text. "
            "If the user is chatting or asking a general question, use kind='say' with payload={'text': <answer>}. "
            "IMPORTANT: Always check the 'recent_memory' to see if you are in the middle of a game, a specific topic, or a task. "
            "If you just asked the user to play a game (like 'Two Truths and a Lie'), and they respond with options, PLAY THE GAME and pick the answer. "
            "When proposing games, be creative and varied. Don't always suggest the same thing. You can invent new simple games or interactive challenges. "
            "Use vision_desc for context ONLY if the user asks about what you see. "
            "For move, follow, come, turn, and stop requests, prefer short motion. "
            + self._spoken_response_instructions()
        )
        if self.allowed_topics:
            system = (
                system
                + " The robot is only allowed to talk about these topics: "
                + ", ".join(self.allowed_topics)
                + ". However, storytelling and general friendly chat are ALWAYS allowed. "
                + "If the user asks about anything else strictly forbidden, respond with kind='say' using a brief refusal."
            )
            
        # Strip None values to drastically reduce token size
        p_dict = {}
        if perception.text: p_dict["text"] = perception.text
        if perception.vision: p_dict["vision"] = perception.vision
        if perception.sensors: p_dict["sensors"] = perception.sensors
        if perception.gestures: p_dict["gestures"] = perception.gestures
        if perception.vision_desc: p_dict["vision_desc"] = perception.vision_desc
        if perception.summary: p_dict["summary"] = perception.summary
        
        user = {
            "situation": perception.summary,
            "perception": p_dict,
            "recent_memory": recent,
            "recent_feedback": recent_feedback,
            "long_term_facts": long_term_facts,
            "available_actions": [
                {"kind": "set_led", "payload": {"id": 1, "state": "on|off"}},
                {"kind": "set_fan", "payload": {"state": "on|off"}},
                {"kind": "set_state", "payload": {"mode": "awake|sleep", "eye": "open|closed"}},
                {"kind": "motion", "payload": {"direction": "forward|backward|left|right|stop", "speed": "0..1", "duration_ms": "int"}},
                {"kind": "servo", "payload": {"servo_id": "int", "angle": "0..180"}},
                {"kind": "say", "payload": {"text": "string"}},
                {"kind": "remember", "payload": {"key": "string", "value": "string"}},
                {"kind": "noop", "payload": {}},
            ],
        }

        if self.provider == "ollama":
            try:
                reply = await asyncio.to_thread(self._ollama_json, system, json.dumps(user, ensure_ascii=False))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await asyncio.sleep(0)
                return ActionCommand(kind="noop", payload={"reason": "llm_error", "provider": "ollama", "error": str(e)[:200]})
        elif self.provider == "openai":
            try:
                reply = await asyncio.to_thread(self._openai_json, system, json.dumps(user, ensure_ascii=False))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await asyncio.sleep(0)
                return ActionCommand(kind="noop", payload={"reason": "llm_error", "provider": "openai", "error": str(e)[:200]})
        elif self.provider == "gemini":
            try:
                reply = await asyncio.to_thread(self._gemini_json, system, json.dumps(user, ensure_ascii=False))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await asyncio.sleep(0)
                return ActionCommand(kind="noop", payload={"reason": "llm_error", "provider": "gemini", "error": str(e)[:200]})
        elif self.provider == "huggingface":
            try:
                reply = await asyncio.to_thread(self._huggingface_json, system, json.dumps(user, ensure_ascii=False))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await asyncio.sleep(0)
                return ActionCommand(kind="noop", payload={"reason": "llm_error", "provider": "huggingface", "error": str(e)[:200]})
        else:
            await asyncio.sleep(0)
            return ActionCommand(kind="noop", payload={"reason": "llm_provider_not_wired", "provider": self.provider})
        try:
            import re
            clean_reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()
            # If nothing left, try the original just in case
            if not clean_reply:
                clean_reply = reply.strip()
                
            data = json.loads(clean_reply)
            kind = data.get("kind")
            payload = data.get("payload")
            if isinstance(kind, str) and isinstance(payload, dict):
                return ActionCommand(kind=kind, payload=payload)
        except Exception:
            import re
            fallback_text = clean_reply
            match = re.search(r'"text"\s*:\s*"([^"]+)"', reply)
            if match:
                fallback_text = match.group(1)
            else:
                fallback_text = re.sub(r'[\{\}\[\]]', '', fallback_text).strip()
                fallback_text = re.sub(r'^["]|["]$', '', fallback_text).strip()
            
            if fallback_text and fallback_text.lower() not in ["null", "none", ""]:
                return ActionCommand(kind="say", payload={"text": fallback_text})
                
        return ActionCommand(kind="noop", payload={"reason": "invalid_llm_output", "raw": reply[:200]})

    def _ollama_json(self, system: str, user: str) -> str:
        client = OllamaClient(base_url=self.base_url)
        return client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            device=self.device,
        )

    def _openai_json(self, system: str, user: str) -> str:
        client = OpenAIClient(api_key=self.api_key, base_url=self.base_url)
        return client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )

    def _gemini_json(self, system: str, user: str) -> str:
        from brain.llm.gemini_client import GeminiClient
        client = GeminiClient(api_key=self.api_key)
        return client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )

    def _huggingface_json(self, system: str, user: str) -> str:
        from brain.llm.huggingface_client import HuggingFaceClient
        try:
            from brain.pi5.web_ui_backend.routers.api_keys import _get_key_manager
            key_manager = _get_key_manager()
        except Exception:
            key_manager = None
        client = HuggingFaceClient(api_key=self.api_key, default_model=self.model, key_manager=key_manager)
        return client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )


def build_planner(cfg: BrainConfig, memory: SqliteMemory) -> Planner:
    rule = RuleBasedPlanner(memory=memory, cfg=cfg)
    
    provider = str(cfg.provider or "ollama").strip().lower()
    
    if provider in ("openrouter", "huggingface"):
        model = cfg.hf_model or "moonshotai/kimi-k2.6:free"
        llm = LlmPlanner(
            memory=memory,
            provider="huggingface",
            base_url="",
            model=model,
            api_key=cfg.hf_api_key,
            allowed_topics=cfg.allowed_topics,
            robot_language=cfg.robot_language,
        )
        return HybridPlanner(rule=rule, llm=llm)
        
    elif provider == "openai":
        llm = LlmPlanner(
            memory=memory,
            provider="openai",
            base_url=cfg.openai_base_url,
            model=cfg.openai_model,
            api_key=cfg.openai_api_key,
            allowed_topics=cfg.allowed_topics,
            robot_language=cfg.robot_language,
        )
        return HybridPlanner(rule=rule, llm=llm)
        
    elif provider == "gemini":
        llm = LlmPlanner(
            memory=memory,
            provider="gemini",
            base_url="",
            model=cfg.gemini_model,
            api_key=cfg.google_api_key,
            allowed_topics=cfg.allowed_topics,
            robot_language=cfg.robot_language,
        )
        return HybridPlanner(rule=rule, llm=llm)
        
    elif provider == "ollama":
        planners: list[Planner] = []
        # Add Cloud Ollama if configured
        if cfg.ollama_cloud_url and cfg.ollama_cloud_model:
            planners.append(LlmPlanner(
                memory=memory,
                provider="ollama",
                base_url=cfg.ollama_cloud_url,
                model=cfg.ollama_cloud_model,
                device=cfg.llm_device,
                allowed_topics=cfg.allowed_topics,
                robot_language=cfg.robot_language,
            ))
            
        # Add Local Ollama if configured
        if cfg.ollama_model:
            planners.append(LlmPlanner(
                memory=memory,
                provider="ollama",
                base_url=cfg.ollama_base_url,
                model=cfg.ollama_model,
                device=cfg.llm_device,
                allowed_topics=cfg.allowed_topics,
                robot_language=cfg.robot_language,
            ))

        if planners:
            llm = FallbackLlmPlanner(planners=planners) if len(planners) > 1 else planners[0]
            return HybridPlanner(rule=rule, llm=llm)
            
    # Fallback to older env-based resolution if provider is unknown/empty
    if cfg.openai_api_key:
        llm = LlmPlanner(
            memory=memory,
            provider="openai",
            base_url=cfg.openai_base_url,
            model=cfg.openai_model,
            api_key=cfg.openai_api_key,
            allowed_topics=cfg.allowed_topics,
            robot_language=cfg.robot_language,
        )
        return HybridPlanner(rule=rule, llm=llm)
    
    if cfg.hf_api_key:
        llm = LlmPlanner(
            memory=memory,
            provider="huggingface",
            base_url="",
            model=cfg.hf_model,
            api_key=cfg.hf_api_key,
            allowed_topics=cfg.allowed_topics,
            robot_language=cfg.robot_language,
        )
        return HybridPlanner(rule=rule, llm=llm)
        
    if cfg.google_api_key:
        llm = LlmPlanner(
            memory=memory,
            provider="gemini",
            base_url="",
            model=cfg.gemini_model,
            api_key=cfg.google_api_key,
            allowed_topics=cfg.allowed_topics,
            robot_language=cfg.robot_language,
        )
        return HybridPlanner(rule=rule, llm=llm)
    
    return rule
