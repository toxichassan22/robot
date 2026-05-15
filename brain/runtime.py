from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import sys
import warnings
import ctypes
from dataclasses import asdict

# THE NUCLEAR OPTION: Redirect low-level stderr (FD 2) to NUL
# This kills all C++ warnings from MediaPipe, TF, etc.
try:
    if os.name == 'nt':
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
        os.environ['GLOG_minloglevel'] = '3'
        import os as _os
        _null_fd = _os.open(_os.devnull, _os.O_WRONLY)
        _os.dup2(_null_fd, 2) 
except Exception:
    pass

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR, format='%(message)s')

try:
    import absl.logging
    absl.logging.set_verbosity(absl.logging.ERROR)
    absl.logging.set_stderrthreshold("fatal")
except Exception:
    pass

import httpx  # type: ignore
import sys
from brain.config import BrainConfig
from brain.cognition.planner import build_planner
from brain.cognition.wakeword_gate import WakeWordGate
from brain.memory.sqlite_memory import SqliteMemory
from brain.perception.perceiver import UnifiedPerceiver
from brain.speech.audio_input import AudioStream
from brain.speech.stt import VoskSTT, build_stt
from brain.speech.tts import build_tts
from brain.transport.esp32_client import Esp32Client
from brain.transport.transport_base import Transport
from brain.types import ActionCommand, MotionCommand, ServoCommand, PerceptionState
from brain.state.robot_state_manager import RobotStateManager, RobotMode, AudioState
from brain.heartbeat.heartbeat_manager import HeartbeatManager
from brain.cognition.safety.behavior_tree import BehaviorTree
from brain.cognition.safety.rules import ModeCheckRule, SpeedLimitRule, ObstacleRule, ThermalRule
from brain.cognition.safe_executor import SafeCommandExecutor
from brain.thermal.thermal_monitor import ThermalMonitor
from brain.perception.governed_perceiver import GovernedPerceiver
from brain.speech.audio_fsm import AudioFSM
from brain.speech.gemini_live_audio import (
    build_live_audio_config,
    close_live_audio_streams,
    create_live_client,
    open_live_audio_streams,
    play_gemini_audio,
    resolve_live_model,
    send_mic_to_gemini,
    send_text_turn,
)
from brain.cognition.motion_planner import MotionPlanner
from brain.debate_engine import DebateEngine
from brain.memory.chat_archiver import ChatArchiver

def _ensure_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _load_robot_settings(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class BrainRuntime:
    @classmethod
    def from_env(cls) -> "BrainRuntime":
        from brain.transport.transport_mock import MockTransport

        return cls(BrainConfig.from_env(), MockTransport())

    def __init__(self, cfg: BrainConfig, transport: Transport):
        settings = _load_robot_settings(cfg.settings_path)
        if settings:
            cfg = cfg.with_robot_settings(settings)
        self.cfg = cfg
        logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))
        
        # --- SILENCE UNNECESSARY LOGS ---
        for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "httpcore"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
        
        class CleanOutputFilter(logging.Filter):
            def filter(self, record):
                msg = str(record.msg)
                if "VLM: Using local analysis" in msg: return False
                if "Gemini Live connected with model" in msg: return False
                if "Brain: Command processor started" in msg: return False
                if "Brain: Perception loop started" in msg: return False
                if "Brain received command" in msg: return False
                if "Chat interaction received" in msg: return False
                if "Brain: Connection health monitor" in msg: return False
                if "Saying:" in msg: return False
                return True
        logging.getLogger().addFilter(CleanOutputFilter())
        
        _ensure_dir(cfg.memory_db_path)
        self.memory = SqliteMemory(cfg.memory_db_path)
        self.transport = transport
        self.esp32 = Esp32Client(self.transport)

        # Safety & State
        self.state_manager = RobotStateManager(config=cfg, initial_mode=RobotMode.IDLE)
        self.heartbeat_manager = HeartbeatManager(
            esp32_client=self.esp32,
            state_manager=self.state_manager,
            interval_ms=cfg.heartbeat_interval_ms
        )
        self.behavior_tree = BehaviorTree(rules=[
            ModeCheckRule(), 
            SpeedLimitRule(), 
            ObstacleRule(), 
            ThermalRule()
        ])
        self.safe_executor = SafeCommandExecutor(
            esp32_client=self.esp32,
            state_manager=self.state_manager,
            behavior_tree=self.behavior_tree
        )
        self.thermal_monitor = ThermalMonitor(
            state_manager=self.state_manager, 
            interval_s=cfg.thermal_monitor_interval_s
        )

        # Perceiver wrapped with Governor
        unified_perceiver = UnifiedPerceiver(cfg)
        self.perceiver = GovernedPerceiver(perceiver=unified_perceiver, state_manager=self.state_manager)

        self.planner = build_planner(cfg, self.memory)
        self.gate = WakeWordGate(wake_word=cfg.wake_word, sleep_timeout_s=cfg.sleep_timeout_s)
        
        self.gemini_live_audio_enabled = str(cfg.stt_provider or "").strip().lower() in {
            "gemini",
            "gemini_live",
            "gemini-live",
            "live",
        }

        # Speech components. Gemini Live mode sends mic audio directly to Gemini,
        # so no local Vosk/Google STT object is created for the live voice loop.
        self.audio = None
        self.stt = None
        self.audio_fsm = None
        if not self.gemini_live_audio_enabled:
            self.audio = AudioStream(sample_rate=16000)
            model_path = cfg.vosk_model_path if cfg.vosk_model_path else "./config/data/vosk-model"
            self.stt = build_stt(
                provider=cfg.stt_provider,
                online_enabled=cfg.stt_online_enabled,
                language=cfg.robot_language,
                vosk_model_path=model_path,
                sample_rate=16000,
            )
        self.tts = build_tts(
            provider=cfg.tts_provider,
            voice_gender=cfg.tts_voice_gender,
            language=cfg.tts_lang,
            voice_uri=cfg.tts_voice_uri,
            tts_rate=cfg.tts_rate,
            gemini_api_key=cfg.google_api_key,
            chatterbox_base_url=cfg.chatterbox_base_url,
            chatterbox_voice_mode=cfg.chatterbox_voice_mode,
            chatterbox_reference_audio=cfg.chatterbox_reference_audio,
            xtts_base_dir=cfg.xtts_base_dir,
            xtts_checkpoint=cfg.xtts_checkpoint,
            xtts_speaker_wav=cfg.xtts_speaker_wav,
            cache_dir=cfg.tts_cache_dir,
        )
        # Start TTS thread immediately so chat interactions work even before voice_loop starts
        self.tts.start()
        
        if not self.gemini_live_audio_enabled:
            self.audio_fsm = AudioFSM(
                audio_stream=self.audio,
                stt=self.stt,
                state_manager=self.state_manager,
                wake_word=cfg.wake_word,
                active_timeout_s=cfg.sleep_timeout_s # Reuse sleep timeout
            )
        else:
            self.state_manager.set_audio_state(AudioState.ACTIVE)
            logging.info("Gemini Live audio enabled: local STT voice loop is disabled.")


        self.motion_planner = MotionPlanner()
        self.debate_engine = DebateEngine()
        
        # Topic-based persistent memory
        from brain.memory.topic_memory import TopicMemory
        self.topic_memory = TopicMemory(
            topics_dir=os.path.join(os.path.dirname(cfg.memory_db_path), "topics")
        )
        
        # Folder-based question cache (shared by ALL models)
        from brain.memory.question_cache import QuestionCache
        self.question_cache = QuestionCache(
            cache_dir=os.path.join(os.path.dirname(cfg.memory_db_path), "question_cache")
        )
        
        self.chat_archiver = ChatArchiver(
            memory=self.memory,
            config=self.cfg,
            archive_dir=os.path.join(os.path.dirname(cfg.memory_db_path), "data_of_chat"),
            context_limit=30000000
        )
        
        self.command_queue = asyncio.Queue()
        self._register_debug_providers()

    def _register_debug_providers(self) -> None:
        try:
            from brain.pi5.web_ui_backend import core as backend_core
            backend_core.app.state.perceiver = self.perceiver

            backend_core.set_debug_camera_frame_provider(
                lambda: self.perceiver.snapshot_jpeg() if hasattr(self.perceiver, "snapshot_jpeg") else None
            )
            backend_core.set_debug_vision_describe_provider(
                lambda prompt=None: self.perceiver.describe_now(prompt=prompt) if hasattr(self.perceiver, "describe_now") else None
            )
        except Exception:
            pass

    def _background_vlm_enabled(self) -> bool:
        model = str(getattr(self.cfg, "vlm_model", "") or "").strip().lower()
        return bool(model)

    def _publish_runtime_debug_snapshot(
        self,
        *,
        heard_text: str | None,
        rewritten_text: str | None,
        perception: PerceptionState | None,
        action: ActionCommand | None,
        source: str = "runtime",
    ) -> None:
        try:
            from brain.pi5.web_ui_backend import core as backend_core

            previous = backend_core.get_runtime_debug_snapshot() or {}
            payload = {
                "freshAtMs": int(time.time() * 1000),
                "source": source,
                "heardText": heard_text if heard_text is not None else previous.get("heardText"),
                "rewrittenText": rewritten_text if rewritten_text is not None else previous.get("rewrittenText"),
                "visionDesc": (perception.vision_desc if perception and perception.vision_desc is not None else previous.get("visionDesc")),
                "visionDescFrameTsMs": (getattr(perception, "vision_desc_ts_ms", None) if perception and getattr(perception, "vision_desc_ts_ms", None) is not None else previous.get("visionDescFrameTsMs")),
                "visionDescLatencyMs": (getattr(perception, "vision_desc_latency_ms", None) if perception and getattr(perception, "vision_desc_latency_ms", None) is not None else previous.get("visionDescLatencyMs")),
                "visionDescEvent": (getattr(perception, "vision_desc_event", None) if perception and getattr(perception, "vision_desc_event", None) is not None else previous.get("visionDescEvent")),
                "visionDescAgeMs": (getattr(perception, "vision_desc_age_ms", None) if perception and getattr(perception, "vision_desc_age_ms", None) is not None else previous.get("visionDescAgeMs")),
                "vlmQueue": (getattr(perception, "vlm_queue", None) if perception and getattr(perception, "vlm_queue", None) is not None else previous.get("vlmQueue")),
                "vision": (perception.vision if perception and perception.vision is not None else previous.get("vision")),
                "gestures": (perception.gestures if perception and perception.gestures is not None else previous.get("gestures")),
                "sensors": (perception.sensors if perception and perception.sensors is not None else previous.get("sensors")),
                "motionDetected": (bool(perception.motion_detected) if perception is not None else bool(previous.get("motionDetected"))),
                "action": asdict(action) if action is not None else previous.get("action"),
                "detailedVisionDesc": previous.get("detailedVisionDesc"),
                "detailedVisionFreshAtMs": previous.get("detailedVisionFreshAtMs"),
                "detailedVisionModel": previous.get("detailedVisionModel"),
            }
            backend_core.set_runtime_debug_snapshot(payload)
        except Exception:
            pass

    def _is_visual_question(self, text: str) -> bool:
        visual_kws = [
            "شايف", "لابس", "اقرا", "اقرأ", "مكتوب", "قدامك", "ولد ولا بنت", "بنت ولا ولد", "شكلي", 
            "روشتة", "روشته", "ورقة", "ورقه", "معايا إيه", "معايا ايه", "إيه ده", "ايه ده", "كده", "كدا", "دي", "ده"
        ]
        return any(k in text.lower() for k in visual_kws)

    @staticmethod
    def _has_visual_context(perception: PerceptionState | None) -> bool:
        if perception is None:
            return False
        if isinstance(perception.vision_desc, str) and perception.vision_desc.strip():
            return True
        vision = perception.vision
        if not isinstance(vision, dict):
            return False
        face = vision.get("face") if isinstance(vision.get("face"), dict) else {}
        pose = vision.get("pose") if isinstance(vision.get("pose"), dict) else {}
        appearance = face.get("appearance") if isinstance(face.get("appearance"), dict) else {}
        if appearance.get("shirt_color"):
            return True
        return bool(face or pose)

    async def _capture_live_visual_context(self, text: str | None, sensors: dict | None = None) -> PerceptionState | None:
        if not self._is_visual_question(text):
            return None
        try:
            self.perceiver.start()
        except Exception:
            pass
        best: PerceptionState | None = None
        for _ in range(6):
            snap = await asyncio.to_thread(self.perceiver.perceive, text=None, sensors=sensors or {})
            best = snap
            if self._has_visual_context(snap):
                return snap
            await asyncio.sleep(0.25)
        try:
            desc = await asyncio.to_thread(
                self.perceiver.describe_now,
                "In 3 short sentences: 1) Describe the person's facial expression and emotion in detail. 2) Describe their clothes colors and appearance. 3) List visible objects and any readable text.",
            )
        except Exception:
            desc = None
        if isinstance(desc, str) and desc.strip():
            return self.perceiver.from_inputs(
                text=None,
                vision=(best.vision if best else None),
                sensors=sensors or {},
                gestures=(best.gestures if best else None),
                vision_desc=desc.strip(),
            )
        return best

    async def _is_complex_query(self, user_text: str) -> bool:
        """Smart LLM-based router to determine if query requires Debate Engine (Agentic RAG)."""
        word_count = len(user_text.split())
        if word_count > 15:
            return True
            
        system = (
            "You are a routing system. Answer with exactly and only 'YES' or 'NO'. "
            "Does the following request require deep internet research, complex philosophical analysis, or multi-agent debate? "
            "Simple math (e.g. 1+1), everyday chat, storytelling (احكي قصة), basic factual questions, and short requests should be 'NO'. "
            "Only answer 'YES' for advanced topics, deep research, complex comparisons, or difficult coding tasks."
        )
        
        try:
            # We can reuse the chat_archiver's LLM runner since it's already configured
            result = await self.chat_archiver._run_llm(system, user_text)
            response = str(result).strip().upper()
            return "YES" in response
        except Exception:
            # Fallback to a very minimal strict keyword list if LLM fails
            complex_kw = ["بحث عميق", "استراتيجية", "قضية معقدة", "قارن بين", "دراسة جدوى"]
            return any(kw in user_text.lower() for kw in complex_kw)

    async def demo(self, steps: int = 5) -> None:
        from brain.pi5.runtime import run_demo

        await run_demo(self, steps)

    async def _log_safety_event(self, event_type: str, reason: str, original: dict, safe: dict) -> None:
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                await client.post(
                    "http://localhost:8000/api/safety-events",
                    json={
                        "event": event_type,
                        "reason": reason,
                        "original": original,
                        "safe": safe
                    }
                )
        except Exception as e:
            logging.error(f"Failed to log safety event: {e}")

    async def _safe_await(self, func, *args, **kwargs):
        """Helper to await a function only if it's a coroutine."""
        if func is None: return None
        import inspect
        if inspect.iscoroutinefunction(func) or inspect.iscoroutine(func):
            return await func(*args, **kwargs)
        elif callable(func):
            return await asyncio.to_thread(func, *args, **kwargs)
        return func

    async def handle_perception(
        self,
        perception: PerceptionState,
        print_events: bool = False,
        tts_callback: callable | None = None
    ) -> None:
        raw_text = perception.text
        decision = self.gate.on_perception(perception)
        
        # --- FORCE CHAT RESPONSE ---
        if perception.summary == "[CHAT INTERACTION]":
            decision.should_plan = True
            if not self.gate.is_awake:
                self.gate.is_awake = True
                self.state_manager.set_audio_state(AudioState.ACTIVE)

        if print_events and raw_text is not None:
            print(json.dumps({"event": "heard", "text": raw_text}, ensure_ascii=False))
        if decision.rewritten_text is not None and print_events:
            print(json.dumps({"event": "asr", "text": decision.rewritten_text}, ensure_ascii=False))

        if decision.immediate_action is not None:
            if print_events:
                print(json.dumps({"event": "immediate_action", **asdict(decision.immediate_action)}, ensure_ascii=False))
            
            # Use safe await for executor
            validation_result = await self._safe_await(self.safe_executor.execute, decision.immediate_action)
            
            if validation_result and getattr(validation_result, 'was_modified', False):
                print(json.dumps({
                    "event": "immediate_override",
                    "original": asdict(decision.immediate_action),
                    "safe": asdict(validation_result.safe_command),
                    "reason": validation_result.reason,
                }, ensure_ascii=False))
                
                await self._safe_await(self._log_safety_event, 
                    event_type="command_override",
                    reason=validation_result.reason,
                    original=asdict(decision.immediate_action),
                    safe=asdict(validation_result.safe_command)
                )
            
            if decision.immediate_action.kind == "set_state":
                mode = (decision.immediate_action.payload or {}).get("mode")
                if mode == "sleep":
                    self.gate.is_awake = False
                    self.state_manager.set_audio_state(AudioState.SLEEP)
                elif mode == "awake":
                    self.gate.is_awake = True
                    self.state_manager.set_audio_state(AudioState.ACTIVE)
            
            if tts_callback and decision.immediate_action.kind == "set_state":
                mode = (decision.immediate_action.payload or {}).get("mode")
                if mode == "awake":
                    await self._safe_await(tts_callback, "نعم؟")

        if not decision.should_plan:
            return

        target_text = decision.rewritten_text if decision.rewritten_text is not None else raw_text
        if self._is_visual_question(target_text) and not self._has_visual_context(perception):
            try:
                live = await self._safe_await(self._capture_live_visual_context, target_text, perception.sensors)
            except Exception:
                live = None
            if live is not None:
                perception = PerceptionState(
                    ts_ms=perception.ts_ms,
                    text=perception.text,
                    vision=live.vision,
                    sensors=perception.sensors or live.sensors,
                    gestures=live.gestures,
                    vision_desc=live.vision_desc,
                    motion_detected=live.motion_detected,
                )

        # --- Sensory Fusion ---
        # Skip heavy fusion for simple chat interactions - just pass text through
        is_chat = (perception.summary == "[CHAT INTERACTION]")
        if not is_chat:
            perception = self._fuse_perception_summary(perception, target_text)

        planned = perception
        if decision.rewritten_text is not None:
            planned = PerceptionState(
                ts_ms=perception.ts_ms,
                text=decision.rewritten_text,
                vision=perception.vision,
                sensors=perception.sensors,
                gestures=perception.gestures,
                vision_desc=perception.vision_desc,
                summary=perception.summary,
            )
        if not bool(self.cfg.gesture_detection_enabled):
            planned = PerceptionState(
                ts_ms=planned.ts_ms,
                text=planned.text,
                vision=planned.vision,
                sensors=planned.sensors,
                gestures=None,
                vision_desc=planned.vision_desc,
                summary=planned.summary,
            )
        # --- EXACT MATCH CACHE & MULTI-AGENT DEBATE ROUTING ---
        user_text = planned.text or ""
        
        if user_text.strip():
            # 1. Check Question Cache first (folder-based, instant lookup)
            # Only check cache for standalone questions (>2 words) to avoid false hits on contextual words like "كمل"
            cached_answer = None
            if len(user_text.split()) > 2:
                try:
                    cached_answer = self.question_cache.find_answer(user_text)
                except Exception:
                    pass
                
            if cached_answer:
                logging.info(f"Cache HIT for '{user_text}'")
                action = ActionCommand(kind="say", payload={"text": cached_answer})
            else:
                # 2. Complexity Routing
                # Quick check: Is this a simple or creative query?
                creative_keywords = ["قصة", "قصه", "حكاية", "احكي", "story", "tell", "لعبة", "نلعب", "العب", "game", "play"]
                is_creative = any(kw in user_text.lower() for kw in creative_keywords)
                
                is_simple = not await self._safe_await(self._is_complex_query, user_text)
                
                if is_simple or is_creative:
                    logging.info(f"Simple query '{user_text}', routing to single LLM")
                    
                    # --- DYNAMIC VISION READING ---
                    # IMPROVEMENT: Take the snapshot IMMEDIATELY to avoid the user moving their hand
                    reading_keywords = [
                        "اقرا", "اقرأ", "مكتوب", "روشتة", "روشته", "صورة", "صوره", "شوف", "ورقة", "ورقه", "خط", 
                        "read", "what is written", "معايا إيه", "معايا ايه", "إيه دي", "ايه دي", "إيه ده", "ايه ده", "كده", "كدا"
                    ]
                    if any(kw in user_text.lower() for kw in reading_keywords):
                        logging.info("Dynamic reading request detected! Taking IMMEDIATE high-res snapshot...")
                        
                        # Tell user to stay still IMMEDIATELY
                        if tts_callback:
                             await self._safe_await(tts_callback, "ثبت إيدك ثانية واحدة، بشوفها أهو...")
                        
                        custom_prompt = f"The user asked: '{user_text}'. Look very closely at the image. If there is text, transcribe it exactly and accurately. If it's a medical prescription or document, explain what is written clearly."
                        new_desc = await self._safe_await(asyncio.to_thread, self.perceiver.describe_now, custom_prompt, level=2)
                        if new_desc:
                            import dataclasses
                            planned = dataclasses.replace(planned, vision_desc=new_desc)

                    # We pass the full planned perception so the LLM can use vision_desc/vision
                    action = await self._safe_await(self.planner.plan, planned)
                else:
                    logging.info(f"Complex query '{user_text}', routing to Debate Engine")
                    # Retrieve past topic context
                    topic_context = ""
                    try:
                        topic_context = self.topic_memory.get_topic_context(user_text, max_entries=6)
                    except Exception:
                        pass
                    
                    # Build vision context for debate
                    vision_context = ""
                    if planned.vision_desc:
                        vision_context = planned.vision_desc
                    elif planned.vision:
                        vision_context = json.dumps(planned.vision, ensure_ascii=False)
                    
                    # Inject topic memory into vision context for the debate
                    if topic_context:
                        vision_context = f"{vision_context}\n\n[PREVIOUS CONVERSATIONS ON THIS TOPIC]:\n{topic_context}"
                        
                    # Inject immediate short-term memory (chat history) into vision context
                    recent_raw = await self._safe_await(self.memory.get_recent_short_term, limit=8)
                    if recent_raw:
                        recent_text = []
                        for msg in recent_raw:
                            role = "User" if msg["role"] == "user" else "Aria"
                            content = msg["content"]
                            if msg["role"] == "assistant":
                                try:
                                    payload = json.loads(content)
                                    if payload.get("kind") == "say":
                                        content = payload.get("payload", {}).get("text", "")
                                    else:
                                        content = f"[{payload.get('kind')} action]"
                                except:
                                    pass
                            recent_text.append(f"{role}: {content}")
                        if recent_text:
                            vision_context = f"{vision_context}\n\n[RECENT CONVERSATION HISTORY]:\n" + "\n".join(recent_text)
                    
                    if tts_callback:
                        await self._safe_await(tts_callback, "ثواني، هفكر وأشوف المصادر وأقولك...")
                    
                    try:
                        # Pass a status callback to the debate engine
                        async def debate_status_cb(msg):
                            if tts_callback:
                                await self._safe_await(tts_callback, msg)
                                
                        debate_response = await self.debate_engine.start_debate(
                            user_text, 
                            vision_context, 
                            status_callback=debate_status_cb
                        )
                        
                        # Clean XML tags if present
                        if "<spoken_response>" in debate_response:
                            debate_response = debate_response.split("<spoken_response>")[1].split("</spoken_response>")[0].strip()
                        
                        if debate_response.strip():
                            action = ActionCommand(kind="say", payload={"text": debate_response.strip()})
                        else:
                            # Fallback to single planner if debate returned empty
                            action = await self._safe_await(self.planner.plan, planned)
                    except Exception as e:
                        logging.warning(f"Debate failed, falling back to single planner: {e}")
                        action = await self._safe_await(self.planner.plan, planned)
        else:
            # Non-text events (gestures, sensors) go through rule-based planner
            action = await self._safe_await(self.planner.plan, planned)
        
        if print_events:
            print(json.dumps({"event": "action", **asdict(action)}, ensure_ascii=False))
            if action.kind == "say":
                txt = (action.payload or {}).get("text")
                if isinstance(txt, str) and txt.strip():
                    print(json.dumps({"event": "say", "text": txt.strip()}, ensure_ascii=False))
        
        await self._safe_await(self.memory.append_short_term, role="user", content=planned.text or "")
        await self._safe_await(self.memory.append_short_term, role="assistant", content=json.dumps(asdict(action)))
        
        # Trigger async chat compression if we reached the limit
        asyncio.create_task(self.chat_archiver.check_and_compress())

        # Save to both caches (topic memory + question cache)
        if user_text.strip() and action.kind == "say":
            ai_text = (action.payload or {}).get("text", "")
            if ai_text:
                try:
                    self.topic_memory.save_conversation(user_text, ai_text)
                except Exception:
                    pass
                
                # Only cache standalone questions in the global question cache, and avoid caching failures
                # SKIP CACHING for stories, games, reading, and creative requests
                creative_keywords = [
                    "قصة", "قصه", "حكاية", "احكي", "story", "tell", 
                    "لعبة", "نلعب", "العب", "game", "play",
                    "روشتة", "روشته", "ورقة", "ورقه", "اقرا", "اقرأ", "مكتوب", "ايه ده", "إيه ده"
                ]
                is_creative = any(kw in user_text.lower() for kw in creative_keywords)
                
                if not is_creative and len(user_text.split()) > 2 and "مش فاهم" not in ai_text:
                    try:
                        self.question_cache.save(user_text, ai_text)
                    except Exception:
                        pass

        if tts_callback and action.kind == "say":
            txt = (action.payload or {}).get("text")
            if txt:
                await self._safe_await(tts_callback, txt)

        if action.kind == "set_state":
            mode = (action.payload or {}).get("mode")
            if mode == "sleep":
                self.gate.is_awake = False
                self.state_manager.set_audio_state(AudioState.SLEEP)
            elif mode == "awake":
                self.gate.is_awake = True
                self.state_manager.set_audio_state(AudioState.ACTIVE)

        elif action.kind == "remember":
            p = action.payload or {}
            key = p.get("key")
            val = p.get("value")
            if key and val:
                await self._safe_await(self.memory.upsert_long_term, str(key), str(val))
                if tts_callback:
                    await self._safe_await(tts_callback, f"تمام، هدوّن إن {key} هو {val}")

        elif action.kind in ("motion", "servo", "set_state") or action.kind not in ("say", "remember", "store_feedback"):
            if action.kind == "motion" and tts_callback:
                d = str((action.payload or {}).get("direction") or "").strip().lower()
                ack = {"forward": "تمام، لقدام.", "backward": "تمام، لورا.", "left": "تمام، شمال.", "right": "تمام، يمين.", "stop": "تمام، وقفت."}.get(d)
                if ack: await self._safe_await(tts_callback, ack)
            
            validation_result = await self._safe_await(self.safe_executor.execute, action)
            if validation_result and getattr(validation_result, 'was_modified', False):
                print(json.dumps({
                    "event": "command_override", 
                    "original": asdict(action), 
                    "safe": asdict(validation_result.safe_command), 
                    "reason": validation_result.reason
                }, ensure_ascii=False))
                await self._safe_await(self._log_safety_event, 
                    event_type="command_override", 
                    reason=validation_result.reason, 
                    original=asdict(action), 
                    safe=asdict(validation_result.safe_command)
                )

    async def process_commands(self) -> None:
        logging.info("Brain: Command processor started")
        while True:
            cmd = await self.command_queue.get()
            try:
                logging.info(f"Brain received command: {cmd}")
                kind = cmd.get("kind")
                payload = cmd.get("payload", {})
                
                if kind == "motion":
                    # Direct motion command from Web
                    direction = payload.get("direction")
                    speed = payload.get("speed", 1.0)
                    duration_ms = payload.get("duration_ms", 0)
                    
                    try:
                        cmd_obj = self.motion_planner.plan(
                            direction=str(direction),
                            speed=float(speed),
                            duration_ms=int(duration_ms),
                            sensors=None 
                        )
                        # Explicitly construct ActionCommand
                        action = ActionCommand(kind="motion", payload=asdict(cmd_obj))
                        await self.safe_executor.execute(action)
                    except Exception as e:
                        logging.error(f"Motion planning/exec failed: {e}")
                        
                elif kind == "servo":
                    try:
                        # Construct ActionCommand matching structural standard
                        action = ActionCommand(
                            kind="servo", 
                            payload={"servo_id": int(payload.get("servo_id", 0)), "angle": float(payload.get("angle", 0.0))}
                        )
                        await self.safe_executor.execute(action)
                    except Exception as e:
                        logging.error(f"Servo command failed: {e}")

                elif kind == "reload_settings":
                    settings = _load_robot_settings(self.cfg.settings_path)
                    if settings:
                        old_gate = self.gate
                        old_cfg = self.cfg
                        self.cfg = self.cfg.with_robot_settings(settings)
                        self.gemini_live_audio_enabled = str(self.cfg.stt_provider or "").strip().lower() in {
                            "gemini",
                            "gemini_live",
                            "gemini-live",
                            "live",
                        }
                        try:
                            self.state_manager.config = self.cfg
                        except Exception:
                            pass
                        self.planner = build_planner(self.cfg, self.memory)
                        self.gate = WakeWordGate(self.cfg.wake_word, self.cfg.sleep_timeout_s, old_gate.is_awake, old_gate.last_active_monotonic)
                        if self.audio_fsm is not None:
                            self.audio_fsm.active_timeout_s = self.cfg.sleep_timeout_s
                        # Only rebuild perceiver if camera/gesture settings changed
                        perceiver_changed = (
                            self.cfg.camera_resolution != old_cfg.camera_resolution or
                            self.cfg.camera_fps != old_cfg.camera_fps or
                            self.cfg.gesture_detection_enabled != old_cfg.gesture_detection_enabled
                        )
                        if perceiver_changed:
                            try:
                                self.perceiver.stop()
                            except Exception:
                                pass
                            import asyncio
                            await asyncio.sleep(0.5)  # Give camera hardware time to release
                            self.perceiver = GovernedPerceiver(UnifiedPerceiver(self.cfg), self.state_manager)
                            self.perceiver.start()
                            self._register_debug_providers()
                        else:
                            # Just update the config on the existing perceiver
                            if hasattr(self.perceiver, "perceiver"):
                                self.perceiver.perceiver.cfg = self.cfg
                        try:
                            self.tts.stop()
                            self.tts = build_tts(provider=self.cfg.tts_provider, voice_gender=self.cfg.tts_voice_gender, language=self.cfg.tts_lang, voice_uri=self.cfg.tts_voice_uri, tts_rate=self.cfg.tts_rate, gemini_api_key=self.cfg.google_api_key, chatterbox_base_url=self.cfg.chatterbox_base_url, chatterbox_voice_mode=self.cfg.chatterbox_voice_mode, chatterbox_reference_audio=self.cfg.chatterbox_reference_audio, xtts_base_dir=self.cfg.xtts_base_dir, xtts_checkpoint=self.cfg.xtts_checkpoint, xtts_speaker_wav=self.cfg.xtts_speaker_wav, cache_dir=self.cfg.tts_cache_dir)
                            self.tts.start()
                        except Exception as e:
                            logging.error(f"Failed to reload TTS: {e}")
                        if self.gemini_live_audio_enabled:
                            self.state_manager.set_audio_state(AudioState.ACTIVE)
                            logging.info("STT reload skipped: Gemini Live owns microphone transcription.")
                        else:
                            try:
                                stt_model_path = self.cfg.vosk_model_path if self.cfg.vosk_model_path else "./config/data/vosk-model"
                                self.stt = build_stt(
                                    provider=self.cfg.stt_provider,
                                    online_enabled=self.cfg.stt_online_enabled,
                                    language=self.cfg.robot_language,
                                    vosk_model_path=stt_model_path,
                                    sample_rate=16000,
                                )
                                if self.audio_fsm is not None:
                                    self.audio_fsm.stt = self.stt
                                logging.info(f"STT rebuilt: provider={self.cfg.stt_provider}, online={self.cfg.stt_online_enabled}")
                            except Exception as e:
                                logging.error(f"Failed to reload STT: {e}")
                        # live settings reload                                                                                                                                                                                                                                                                                                     
                elif kind == "hearing":
                    text = payload.get("text")
                    if text:
                        print(f"[CHAT DEBUG] ===== RECEIVED CHAT: {text} =====")
                        logging.info(f"Chat interaction received: {text}")
                        # Force awake and active
                        self.gate.is_awake = True
                        self.gate.last_active_monotonic = time.monotonic()
                        self.state_manager.set_audio_state(AudioState.ACTIVE)
                        
                        perception = PerceptionState(
                            ts_ms=int(time.time() * 1000),
                            text=text,
                            summary="[CHAT INTERACTION]"
                        )
                        print(f"[CHAT DEBUG] Calling handle_perception with tts={self.tts.say}")
                        try:
                            await self.handle_perception(perception, print_events=True, tts_callback=self.tts.say)
                            print(f"[CHAT DEBUG] handle_perception COMPLETED OK")
                        except Exception as ex:
                            print(f"[CHAT DEBUG] handle_perception FAILED: {type(ex).__name__}: {ex}")
                            import traceback
                            traceback.print_exc()
                elif kind == "say":
                    text = payload.get("text")
                    if text:
                        logging.info(f"Saying: {text}")

            except Exception as e:
                logging.error(f"Error processing command {cmd}: {e}")
            finally:
                self.command_queue.task_done()

    async def perception_loop(self) -> None:
        logging.info("Brain: Perception loop started")
        self.perceiver.start()
        
        # Give some time for camera to warm up
        await asyncio.sleep(2.0)
        
        try:
            while True:
                # 1. Sense Environment
                # Poll sensors from ESP32 occasionally (e.g., every 500ms) or just assume fast enough serial
                # Actually, serial poll might block if we wait for reply. Let's do it with timeout.
                sensors = {}
                try:
                    # We might want to rate limit sensor polling specifically, but let's try every loop
                    # If camera FPS is 15, we are looping ~66ms. Serial timeout 0.1s is risky.
                    # Ideally we poll sensors in separate task or less frequently.
                    # For now, let's skip polling in this loop to keep it fast for vision, 
                    # OR we implement non-blocking sensor reading if ESP pushes data.
                    # Current Esp32Client.poll_sensors sends request and waits.
                    # Let's poll every 1 second.
                    if int(time.time()) % 2 == 0: # crude 2s check
                         # sensors = await self.esp32.poll_sensors(timeout_s=0.1)
                         pass
                except Exception as e:
                    logging.error(f"Sensor poll failed: {e}")

                # 2. Perceive (Camera -> Gestures)
                # `perceiver.perceive` pulls latest frame
                # 2. Perceive (Camera -> Gestures)
                # `perceiver.perceive` pulls latest frame. Offload to thread to avoid blocking loop.
                perception = await asyncio.to_thread(
                    self.perceiver.perceive,
                    text=None,
                    sensors=sensors,
                    run_vlm=self._background_vlm_enabled(),
                )
                if perception.vision_desc or perception.vision or perception.gestures or perception.motion_detected:
                    self._publish_runtime_debug_snapshot(
                        heard_text=None,
                        rewritten_text=None,
                        perception=perception,
                        action=None,
                        source="perception_loop",
                    )
                
                # Only speech and gesture events should trigger planning here.
                # Pure background vision updates are published to debug/UI but should not
                # continuously re-plan while Qwen is still working on the scene.
                if perception.gestures or perception.text:
                    await self.handle_perception(perception, print_events=True)
                
                # Rate limit loop (lowered from 0.2s to 0.01s for millisecond-level responsiveness)
                await asyncio.sleep(0.01)
                
        except asyncio.CancelledError:
            pass
        finally:
            self.perceiver.stop()
            logging.info("Brain: Perception loop stopped")

    async def gemini_live_voice_loop(self) -> None:
        logging.info("Brain: Gemini Live voice loop started")
        client = create_live_client(self.cfg.google_api_key)
        model_id = resolve_live_model(self.cfg.gemini_live_model)
        streams = open_live_audio_streams()
        transcript_parts: list[str] = []
        processing_tasks: set[asyncio.Task] = set()
        speak_lock = asyncio.Lock()

        system_instruction = (
            "أنتِ أريا، واجهة الصوت الحي للروبوت. اسمعي صوت المستخدم من المايك وقدمي تفريغ الكلام للنظام. "
            "لا تردي على كلام المايك بنفسك. عندما يصلك نص يبدأ بـ SPEAK: انطقي النص الذي بعد العلامة حرفياً "
            "باللهجة المصرية وبدون أي إضافة."
        )
        live_config = build_live_audio_config(
            system_instruction=system_instruction,
            voice_gender=self.cfg.tts_voice_gender,
            input_transcription=True,
            output_transcription=True,
        )

        async def speak_via_gemini(text: str) -> None:
            clean = str(text or "").strip()
            if not clean:
                return
            async with speak_lock:
                await send_text_turn(session, f"SPEAK: {clean}")

        async def process_transcript(user_text: str) -> None:
            logging.info("Heard (via Gemini Live): %s", user_text)
            if not self.gate.is_awake:
                self.gate.is_awake = True
            self.gate.last_active_monotonic = time.monotonic()
            self.state_manager.set_audio_state(AudioState.ACTIVE)
            perception = PerceptionState(ts_ms=int(time.time() * 1000), text=user_text)
            self._publish_runtime_debug_snapshot(
                heard_text=user_text,
                rewritten_text=None,
                perception=perception,
                action=None,
                source="gemini_live_voice_loop",
            )
            await self.handle_perception(perception, tts_callback=speak_via_gemini)

        def track_task(task: asyncio.Task) -> None:
            processing_tasks.add(task)

            def done_callback(done: asyncio.Task) -> None:
                processing_tasks.discard(done)
                try:
                    done.result()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logging.exception("Gemini Live transcript processing failed")

            task.add_done_callback(done_callback)

        try:
            async with client.aio.live.connect(model=model_id, config=live_config) as session:
                logging.info("Gemini Live connected with model %s", model_id)

                async def receive_from_gemini() -> None:
                    async for response in session.receive():
                        server_content = response.server_content
                        if not server_content:
                            continue

                        transcription = server_content.input_transcription
                        if transcription:
                            text = (transcription.text or "").strip()
                            if text:
                                transcript_parts.append(text)
                                logging.info("Gemini Live transcript: %s", text)
                            if transcription.finished:
                                user_text = " ".join(part for part in transcript_parts if part).strip()
                                transcript_parts.clear()
                                if user_text and not user_text.startswith("SPEAK:"):
                                    track_task(asyncio.create_task(process_transcript(user_text)))

                        output_transcription = server_content.output_transcription
                        if output_transcription and output_transcription.text:
                            logging.info("Gemini Live output: %s", output_transcription.text.strip())

                        model_turn = server_content.model_turn
                        if model_turn is not None:
                            for part in model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    await play_gemini_audio(streams.speaker_stream, part.inline_data.data)

                await asyncio.gather(
                    send_mic_to_gemini(session, streams.mic_stream),
                    receive_from_gemini(),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Gemini Live voice loop failed")
            raise
        finally:
            for task in processing_tasks:
                task.cancel()
            close_live_audio_streams(streams)
            logging.info("Brain: Gemini Live voice loop stopped")

    async def voice_loop(self) -> None:
        logging.info("Brain: Voice loop started")
        if self.audio is None or self.audio_fsm is None:
            logging.info("Brain: local voice loop disabled because Gemini Live owns microphone audio.")
            return
        self.audio.start()
        self.tts.start()
        
        # Simple loop: Read audio -> Check Wakeword in STT -> If active, accumulate text -> Plan
        # Note: Vosk does STT. WakeWordGate checks string.
        # So flow is: Stream -> Vosk -> Text -> WakeWordGate -> Planner
        
        try:
            while True:
                chunk = await asyncio.to_thread(self.audio.read, timeout=0.1)
                if chunk is None:
                    continue
                
                # Use FSM to process audio
                text = self.audio_fsm.process_audio_chunk(chunk)
                
                if text:
                    logging.info(f"Heard (via FSM): {text}")
                    
                    # Sync gate if we hear text (means AudioFSM yielded it, so we are ACTIVE)
                    if not self.gate.is_awake:
                        self.gate.is_awake = True
                    self.state_manager.set_audio_state(AudioState.ACTIVE)

                    perception = PerceptionState(
                        ts_ms=int(time.time() * 1000),
                        text=text
                    )
                    await self.handle_perception(perception, tts_callback=self.tts.say)
                
                await asyncio.sleep(0.01)

        except Exception as e:

            logging.error(f"Voice loop error: {e}")
        finally:
            self.audio.stop()
            self.tts.stop()
            logging.info("Brain: Voice loop stopped")

    async def connection_health_loop(self) -> None:
        """Periodically check ESP32 connection health and log status."""
        logging.info("Brain: Connection health monitor started")
        while True:
            try:
                if hasattr(self.esp32, 'ping'):
                    ok = await self.esp32.ping()
                    if not ok:
                        if type(self.transport).__name__ == "MockTransport":
                            logging.debug("ESP32 health check failed (Mock transport, ignoring).")
                        else:
                            logging.warning("ESP32 health check failed — connection may be lost.")
                    else:
                        logging.debug("ESP32 health check OK.")
                elif hasattr(self.esp32, 'is_connected') and not self.esp32.is_connected:
                    if type(self.transport).__name__ == "MockTransport":
                        logging.debug("ESP32 reports disconnected (Mock transport).")
                    else:
                        logging.warning("ESP32 reports disconnected.")
            except Exception as e:
                logging.error(f"Connection health check error: {e}")
            await asyncio.sleep(30)  # Check every 30 seconds

    def _fuse_perception_summary(self, p: PerceptionState, heard_text: str | None) -> PerceptionState:
        """Create a one-sentence summary of all senses (SitRep).
        Only include vision details when actually detected (no defaults)."""
        vision = p.vision or {}
        face = vision.get("face") or {}
        face_id = face.get("face_id")
        # Only use emotion/attention if actually present in the data - NO defaults
        emotion = face.get("emotion") or None
        attention = face.get("attention") or None
        
        # --- Face Recognition Logic ---
        person_name = None
        if face_id and face_id != "unknown":
             person_name = f"شخص (بصمة: {face_id[:8]}...)"
        
        gestures = p.gestures or {}
        sign = gestures.get("sign_alphabet") or gestures.get("sign_word")
        
        parts = []
        if heard_text:
            parts.append(f"سمعت: '{heard_text}'")
        
        v_parts = []
        if face_id and person_name:
            v_parts.append(f"شايف {person_name}")
        if emotion:
            v_parts.append(f"بوجة {emotion}")
        if attention:
            v_parts.append(attention)
        if sign:
            v_parts.append(f"عمل إشارة '{sign}'")
            
        if v_parts:
            parts.append("بينما أرى: " + " و ".join(v_parts))
        
        if p.vision_desc:
            parts.append(f"(وصف البيئة: {p.vision_desc})")
            
        summary = " ".join(parts) if parts else None
        
        return PerceptionState(
            ts_ms=p.ts_ms,
            text=p.text,
            vision=p.vision,
            sensors=p.sensors,
            gestures=p.gestures,
            vision_desc=p.vision_desc,
            vision_desc_ts_ms=p.vision_desc_ts_ms,
            vision_desc_latency_ms=p.vision_desc_latency_ms,
            vision_desc_event=p.vision_desc_event,
            vision_desc_age_ms=p.vision_desc_age_ms,
            vlm_queue=p.vlm_queue,
            summary=summary,
            motion_detected=p.motion_detected
        )

    async def run(self) -> None:
        from brain.web_server import WebServer
        
        logging.info("Starting Brain Runtime...")
        
        # Initialize Web Server with our command queue
        web = WebServer(
            command_queue=self.command_queue, 
            settings_path=self.cfg.settings_path,
            state_manager=self.state_manager
        )

        # Print server URLs banner
        host = web.host if web.host != "0.0.0.0" else "localhost"
        port = web.port
        print(flush=True)
        print("=" * 55, flush=True)
        print("  ROBOT SERVER READY", flush=True)
        print("=" * 55, flush=True)
        print(f"  Dashboard:    http://{host}:{port}/", flush=True)
        print(f"  API Keys:     http://{host}:{port}/keys.html", flush=True)
        print(f"  API Docs:     http://{host}:{port}/docs", flush=True)
        print("=" * 55, flush=True)
        print(flush=True)

        # --- Resilient task wrapper ---
        # Non-critical tasks (camera, mic, heartbeat, etc.) should NOT
        # kill the web server if they crash.  Only log the error.
        async def _resilient(name: str, coro):
            try:
                await coro
            except asyncio.CancelledError:
                raise  # let cancellation propagate normally
            except Exception as exc:
                print(f"[WARNING] Task '{name}' crashed: {exc}", flush=True)
                logging.warning(f"Task '{name}' crashed and will not restart: {exc}")

        # Create tasks – wrap optional hardware tasks so failures are isolated
        server_task = asyncio.create_task(web.serve())          # CRITICAL
        cmd_task    = asyncio.create_task(self.process_commands())  # CRITICAL

        perception_task = asyncio.create_task(
            _resilient("perception_loop", self.perception_loop())
        )
        voice_task = asyncio.create_task(
            _resilient(
                "voice_loop",
                self.gemini_live_voice_loop() if self.gemini_live_audio_enabled else self.voice_loop(),
            )
        )
        heartbeat_task = asyncio.create_task(
            _resilient("heartbeat", self.heartbeat_manager.start())
        )
        thermal_task = asyncio.create_task(
            _resilient("thermal_monitor", self.thermal_monitor.start())
        )
        health_task = asyncio.create_task(
            _resilient("connection_health", self.connection_health_loop())
        )
        
        # Say welcome message
        self.command_queue.put_nowait({
            "kind": "say",
            "payload": {
                "text": "أهلاً، أنا آريا المساعد الذكي الخاص بيك. أقدر أحكي قصص، أتناقش معاك، أشرحلك حاجات... أقدر أساعدك في إيه النهاردة؟"
            }
        })
        
        # Keep alive – only the critical pair (server + commands) must stay up
        try:
            await asyncio.gather(
                server_task, 
                cmd_task, 
                perception_task, 
                voice_task,
                heartbeat_task,
                thermal_task,
                health_task,
            )
        except asyncio.CancelledError:
            logging.info("Brain runtime cancelled")
