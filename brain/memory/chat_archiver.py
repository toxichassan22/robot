import asyncio
import json
import logging
import os
import time
from pathlib import Path
from brain.config import BrainConfig

logger = logging.getLogger("Brain.ChatArchiver")

class ChatArchiver:
    def __init__(self, memory, config: BrainConfig, archive_dir="./config/data/data_of_chat", context_limit=30000000):
        self.memory = memory
        self.cfg = config
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.context_limit = context_limit
        self.is_compressing = False
        
    async def check_and_compress(self):
        if self.is_compressing:
            return
            
        try:
            # Get a large batch of recent messages to check context size
            recent = await self.memory.get_recent_short_term(limit=1000)
            
            # Count actual chat messages and calculate total context size
            chat_msgs = [m for m in recent if m["role"] in ("user", "assistant")]
            
            total_context_length = sum(len(str(m["content"])) for m in chat_msgs)
            
            if total_context_length < self.context_limit:
                return
                
            self.is_compressing = True
            logger.info(f"Chat context limit reached ({total_context_length} / {self.context_limit}). Starting compression...")
            
            # oldest first
            msgs_to_compress = reversed(recent)
            
            chat_text = []
            for msg in msgs_to_compress:
                role = "User" if msg["role"] == "user" else "Aria"
                content = msg["content"]
                if role == "Aria":
                    try:
                        data = json.loads(content)
                        if data.get("kind") == "say":
                            content = data.get("payload", {}).get("text", "")
                        else:
                            content = f"[{data.get('kind')} action]"
                    except Exception:
                        pass
                chat_text.append(f"{role}: {content}")
                
            full_chat = "\n".join(chat_text)
            
            system_prompt = (
                "You are an AI memory manager. Summarize the following conversation history concisely. "
                "Extract all important facts, user preferences, names, and the current topic context so the AI can continue the conversation seamlessly. "
                "Keep the summary short but highly informative."
            )
            
            summary = await self.run_llm(system_prompt, full_chat)
            
            if not summary or len(summary) < 10:
                logger.warning("Compression yielded empty or very short summary. Aborting.")
                return
                
            # save to file
            filename = f"chat_archive_{int(time.time())}.txt"
            filepath = self.archive_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"=== Chat Archive ===\nTime: {time.ctime()}\n\n=== Full Chat ===\n{full_chat}\n\n=== Summary ===\n{summary}")
                
            newest_ts = recent[0]["ts_ms"]
            
            # Delete ONLY the messages we just compressed
            # since sqlite doesn't easily expose bulk delete by IDs without a new method,
            # we will use our new delete_short_term_before method
            await self.memory.delete_short_term_before(newest_ts)
            
            # Inject summary as system message to guide future thinking
            await self.memory.append_short_term(
                role="system", 
                content=f"[Previous Chat Summary: {summary}]\nUse this context for the following conversation.", 
                ts_ms=int(time.time() * 1000)
            )
            
            logger.info(f"Chat compressed and archived successfully to {filename}")
            
        except Exception as e:
            logger.error(f"Chat compression failed: {e}")
        finally:
            self.is_compressing = False
            
    async def run_llm(self, system: str, user: str) -> str:
        # Try to use best available model for summarization
        try:
            if self.cfg.google_api_key:
                from brain.llm.gemini_client import GeminiClient
                client = GeminiClient(api_key=self.cfg.google_api_key)
                return await asyncio.to_thread(client.chat, model=self.cfg.gemini_model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.1)
            elif self.cfg.openai_api_key:
                from brain.llm.openai_client import OpenAIClient
                client = OpenAIClient(api_key=self.cfg.openai_api_key, base_url=self.cfg.openai_base_url)
                return await asyncio.to_thread(client.chat, model=self.cfg.openai_model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.1)
            elif self.cfg.ollama_cloud_url:
                from brain.llm.ollama_client import OllamaClient
                client = OllamaClient(base_url=self.cfg.ollama_cloud_url)
                return await asyncio.to_thread(client.chat, model=self.cfg.ollama_cloud_model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.1)
            elif self.cfg.ollama_base_url:
                from brain.llm.ollama_client import OllamaClient
                client = OllamaClient(base_url=self.cfg.ollama_base_url)
                return await asyncio.to_thread(client.chat, model=self.cfg.ollama_model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.1)
        except Exception as e:
            logger.error(f"LLM compression failed: {e}")
        return ""
