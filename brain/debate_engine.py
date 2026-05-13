import asyncio
import copy
import importlib.util
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from brain.models import ALL_MODELS
from brain.libs.web_search import WebSearcher

logger = logging.getLogger("Brain.DebateEngine")

# Use absolute path relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEBATE_LOGS_PATH = DATA_DIR / "debate_logs.json"
SEARCH_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "search_config.py"


def _load_search_configuration() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Load Agentic RAG search config from `brain/config/search_config.py`."""
    default_model_config = {
        "GLM": {
            "source": "General Web Search",
            "tools": ["google", "duckduckgo"],
            "description": "Fallback web search",
            "prompt": "Perform broad web search for this query.",
            "enabled": True,
        }
    }
    default_search_settings = {
        "max_queries_per_model": 3,
        "max_results_per_source": 5,
        "search_timeout_seconds": 10,
        "enable_round_0": True,
        "fallback_to_knowledge": True,
    }

    try:
        spec = importlib.util.spec_from_file_location("brain_search_config_file", SEARCH_CONFIG_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load search config from {SEARCH_CONFIG_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        model_config = getattr(module, "MODEL_SEARCH_CONFIG", {}) or {}
        search_settings = getattr(module, "SEARCH_SETTINGS", {}) or {}
        if not isinstance(model_config, dict):
            model_config = {}
        if not isinstance(search_settings, dict):
            search_settings = {}
        return copy.deepcopy(model_config) or default_model_config, {
            **default_search_settings,
            **copy.deepcopy(search_settings),
        }
    except Exception as e:
        logger.warning("Failed to load search config file: %s", e)
        return copy.deepcopy(default_model_config), copy.deepcopy(default_search_settings)

class DebateEngine:
    def __init__(
        self,
        models: Optional[List[Any]] = None,
        searcher: Optional[WebSearcher] = None,
        model_search_config: Optional[Dict[str, Dict[str, Any]]] = None,
        search_settings: Optional[Dict[str, Any]] = None,
    ):
        loaded_model_config, loaded_search_settings = _load_search_configuration()
        self.models = models if models is not None else ALL_MODELS
        self.rounds = 5
        self.current_logs = []
        self.model_search_config = copy.deepcopy(model_search_config) if model_search_config is not None else loaded_model_config
        self.search_settings = {**loaded_search_settings, **(copy.deepcopy(search_settings) if search_settings is not None else {})}
        self.searcher = searcher or WebSearcher(
            search_timeout=float(self.search_settings.get("search_timeout_seconds", 10)),
            max_results_per_source=int(self.search_settings.get("max_results_per_source", 5)),
        )
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._write_state(False)

    def _add_log(self, message: str):
        # We use print for terminal visibility while keeping logs for the JSON file
        if any(marker in message for marker in ["=== ROUND", "🚀 Starting", "🧠 [DeepSeek Synthesis]"]):
            print(f"\n[THINKING] {message}", flush=True)
        elif "✅" in message or "⚠️" in message or "⏭️" in message:
             print(f"  {message}", flush=True)
             
        self.current_logs.append(message)
        self._write_state(True)

    def _write_state(self, is_debating: bool):
        try:
            with open(DEBATE_LOGS_PATH, "w", encoding="utf-8") as f:
                json.dump({"is_debating": is_debating, "logs": self.current_logs}, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to write debate state: {e}")

    async def run_round_0_search(self, query: str, vision_context: str) -> Dict[str, str]:
        """
        Round 0: Agentic RAG.
        Each model gathers information from its configured web-wide search mix, then the
        pooled findings are shared with all models in Round 1.
        """
        del vision_context
        if not self.search_settings.get("enable_round_0", True):
            self._add_log("=== ROUND 0: Distributed Search disabled by config ===")
            return {}

        self._add_log("=== ROUND 0: Distributed Search (Agentic RAG) ===")

        tasks = []
        for model in self.models:
            config = self._get_search_config_for_model(model.name)
            if not config.get("enabled", True):
                self._add_log(f"⏭️ [{model.name}] Round 0 search disabled in config.")
                continue
            self._add_log(
                f"🔎 [{model.name}] Searching {config.get('source', 'configured sources')} via {', '.join(config.get('tools', []))}"
            )
            tasks.append(self._search_with_model(model, query, config))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        search_results = {}
        enabled_models = [model for model in self.models if self._get_search_config_for_model(model.name).get("enabled", True)]

        for model, result in zip(enabled_models, results):
            if isinstance(result, Exception):
                self._add_log(f"⚠️ [{model.name}] Search failed: {str(result)}")
                if self.search_settings.get("fallback_to_knowledge", True):
                    search_results[model.name] = "[Search failed - will use internal knowledge]"
                else:
                    search_results[model.name] = "[Search failed]"
            else:
                self._add_log(
                    f"🔍 [{model.name}] Found information from {result.get('source', 'unknown')} "
                    f"using {', '.join(result.get('tools_used', []))}"
                )
                search_results[model.name] = result.get('summary', '')
        return search_results

    async def _search_with_model(self, model, query: str, config: dict) -> dict:
        """Use specialized search tools and model to summarize findings"""
        try:
            max_queries = int(self.search_settings.get("max_queries_per_model", 3))
            tools = config.get("tools", []) or ["duckduckgo"]
            search_prompt = f"""You need to search for information about: {query}
            Your search focus: {config['source']}
            Available tools: {', '.join(tools)}
            Search goal: {config.get('prompt') or config.get('description', '')}

            Generate up to {max_queries} optimized search queries for these sources.
            Return ONLY the queries, one per line."""

            search_queries = await model.generate(search_prompt, "")
            queries = self._normalize_generated_queries(search_queries, query, max_queries)
            all_results = {}

            for q in queries:
                results = await self.searcher.search_multiple_sources(q, tools)
                for source, items in results.items():
                    all_results.setdefault(source, []).extend(items)

            formatted_results = self.searcher.format_results_for_llm(all_results)
            summary_prompt = f"""Based on these search results about: {query}

            {formatted_results}

            Summarize the key information you found in 3-5 sentences.
            Focus on facts and data that will help answer the user's question."""

            summary = await model.generate(summary_prompt, "")
            return {
                "source": config["source"],
                "summary": summary,
                "queries": queries,
                "tools_used": self.searcher.resolve_sources(tools),
                "result_count": sum(len(v) for v in all_results.values())
            }
        except Exception as e:
            logger.error(f"[{model.name}] Search error: {e}")
            raise e

    async def run_round_1(self, query: str, vision_context: str, search_context: Dict[str, str] = None) -> Dict[str, str]:
        self._add_log("=== ROUND 1: Independent Reasoning With Shared Research ===")

        search_text = ""
        if search_context:
            search_text = "\n\n=== POOLED RESEARCH FINDINGS FROM ROUND 0 ===\n"
            for model_name, findings in search_context.items():
                if findings and not findings.startswith("[Search failed"):
                    search_text += f"\n[{model_name}] found:\n{findings}\n"

        system_prompt = f"""You are participating in a 6-round Multi-Agent Debate.
        ROUND 1 RULES:
        - Think independently about the answer and reasoning.
        - You MAY use the pooled Round 0 research collected collaboratively by all models.
        - Do not mention the debate process, other models, or internal coordination.
        Produce your full answer, state confidence (0-100%), and reasoning approach.

        Use the pooled Round 0 findings along with your own knowledge.
        {search_text}

        <vision_context>{vision_context}</vision_context>
        <audio_input>{query}</audio_input>
        """

        tasks = []
        for model in self.models:
            tasks.append(self._safe_generate(model, query, system_prompt))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        round_outputs = {}
        for model, result in zip(self.models, results):
            if isinstance(result, Exception):
                self._add_log(f"⚠️ [{model.name}] FAILED in Round 1: {result}")
                round_outputs[model.name] = "[FAILED - No Response]"
            else:
                self._add_log(f"✅ [{model.name}] Responded:\n{result}")
                round_outputs[model.name] = result
                
        return round_outputs

    async def run_review_round(self, round_num: int, previous_outputs: Dict[str, str], original_query: str, active_models: List = None) -> Dict[str, str]:
        if active_models is None:
            active_models = self.models
            
        self._add_log(f"=== ROUND {round_num}: Cross Review ===")
        
        history_text = "\n\n".join([f"[{name}] said:\n{resp}" for name, resp in previous_outputs.items()])
        
        system_prompt = f"""You are in Round {round_num} of a 6-round Debate.
        Read the following answers from the previous round.
        Identify agreements ✓, disagreements ✗, and missed points ⚠️.
        Update your answer. State what changed and WHY. Update confidence.
        
        PREVIOUS ROUND RESPONSES:
        {history_text}
        """
        
        tasks = []
        for model in active_models:
            tasks.append(self._safe_generate(model, "Review the previous round and update your stance.", system_prompt))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        round_outputs = {}
        for model, result in zip(active_models, results):
            if isinstance(result, Exception):
                self._add_log(f"⚠️ [{model.name}] FAILED in Round {round_num}: {result}")
                round_outputs[model.name] = "[FAILED - Missed Round]"
            else:
                self._add_log(f"✅ [{model.name}] Reviewed and Updated:\n{result}")
                round_outputs[model.name] = result
                
        return round_outputs

    async def run_synthesis(self, round_outputs: Dict[str, str]) -> str:
        self._add_log("=== ROUND 3: Final Synthesis (DeepSeek Only) ===")
        
        history_text = "\n\n".join([f"[{name}] final stance:\n{resp}" for name, resp in round_outputs.items()])
        
        system_prompt = f"""You are the Final Synthesizer. Round 3.
        Collect all final answers from Round 2. Identify core consensus.
        Build ONE final unified answer. Resolving any disagreements.
        
        CRITICAL RULES:
        1. Speak directly to the user in Egyptian Arabic (unless the user requested another language).
        2. Provide the actual answer/solution/code directly to the user.
        3. DO NOT talk about the "debate process", "consensus", "models", or "agents". Provide the final synthesized knowledge as if you are a single helpful AI.
        4. Output ONLY the final synthesized answer inside <spoken_response> tags.
        
        5. Use Arabic diacritics (tashkeel) on important or potentially mispronounced words to guide the TTS system.
        
        FINAL ROUND 2 RESPONSES:
        {history_text}
        """
        
        try:
            from brain.models import deepseek
            result = await deepseek.generate("Synthesize the final response.", system_prompt)
            self._add_log(f"🧠 [DeepSeek Synthesis] Final Decision:\n{result}")
            return result
        except Exception as e:
            logger.error(f"DeepSeek failed synthesis: {e}")
            self._add_log(f"❌ [DeepSeek Synthesis] FAILED: {e}")
            return "<spoken_response>عذراً، حدث خطأ في النظام العقلي أثناء تجميع الإجابة.</spoken_response>"

    async def _safe_generate(self, model, prompt, system_prompt):
        return await model.generate(prompt, system_prompt)

    def _get_search_config_for_model(self, model_name: str) -> Dict[str, Any]:
        config = self.model_search_config.get(model_name)
        if config:
            return config
        return self.model_search_config.get("GLM", {
            "source": "General Web Search",
            "tools": ["google", "duckduckgo"],
            "description": "Fallback web search",
            "prompt": "Perform broad web search for this query.",
            "enabled": True,
        })

    @staticmethod
    def _normalize_generated_queries(raw_queries: str, original_query: str, max_queries: int) -> List[str]:
        queries: List[str] = []
        for line in str(raw_queries or "").splitlines():
            candidate = re.sub(r"^\s*(?:[-*]\s*)?(?:\d+[\).\:\-]\s*)?", "", line).strip()
            if candidate and candidate not in queries:
                queries.append(candidate)
            if len(queries) >= max_queries:
                break
        return queries or [original_query]

    async def start_debate(self, query: str, vision_context: str, status_callback=None) -> str:
        self.current_logs = []
        self._add_log(f"🚀 Starting Multi-Agent Debate for query: '{query}'")
        
        # Round 0: Agentic RAG Search (NEW)
        search_context = await self.run_round_0_search(query, vision_context)
        
        # Round 1: Independent thinking with search context
        current_outputs = await self.run_round_1(query, vision_context, search_context)
        
        # Keep only models that completed successfully in the previous round.
        active_models = [m for m in self.models if current_outputs.get(m.name) and not current_outputs[m.name].startswith("[FAILED")]
        if not active_models:
            self._add_log("❌ ALL models failed in Round 1. Aborting debate.")
            self._write_state(False)
            return "عذراً، حصل عطل في مجلس الذكاء الاصطناعي ومحدش قدر يجاوب دلوقتي."
        
        # Round 2
        for round_num in range(2, 3):
            if status_callback:
                try:
                    await status_callback("براجع المعلومات وقربت أخلص...")
                except Exception:
                    pass
                    
            current_outputs = await self.run_review_round(round_num, current_outputs, query, active_models=active_models)
            
            # Update active models to drop only models that actually failed.
            active_models = [m for m in active_models if current_outputs.get(m.name) and not current_outputs[m.name].startswith("[FAILED")]
            if not active_models:
                self._add_log(f"❌ ALL models failed in Round {round_num}. Aborting debate.")
                self._write_state(False)
                return "عذراً، حصل عطل في مجلس الذكاء الاصطناعي ومحدش قدر يكمل المناظرة."
            
        # Round 3
        final_response = await self.run_synthesis(current_outputs)
        self._add_log(f"🏁 Debate concluded. Final output generated.")
        self._write_state(False)
        
        return final_response
