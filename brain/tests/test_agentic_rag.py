import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from brain.debate_engine import DebateEngine
from brain.libs.web_search import WebSearcher


class FakeModel:
    def __init__(self, name: str):
        self.name = name
        self.calls = []

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        if "Generate up to" in prompt:
            return "1. distributed rag\n2. agentic retrieval"
        if "Summarize the key information" in prompt:
            return f"{self.name} summary"
        return f"{self.name} response"


class FakeSearcher:
    def __init__(self):
        self.calls = []

    def resolve_sources(self, sources):
        return list(dict.fromkeys(sources or []))

    async def search_multiple_sources(self, query, sources=None):
        resolved = self.resolve_sources(sources)
        self.calls.append({"query": query, "sources": resolved})
        return {
            source: [
                {
                    "title": f"{source}:{query}",
                    "url": f"https://example.com/{source}",
                    "snippet": f"snippet from {source}",
                }
            ]
            for source in resolved
        }

    def format_results_for_llm(self, results, max_snippet_length: int = 200):
        del max_snippet_length
        return "\n".join(f"{source}:{len(items)}" for source, items in results.items())


class TestAgenticRag(unittest.IsolatedAsyncioTestCase):
    async def test_round_0_uses_shared_configured_sources(self):
        models = [FakeModel("DeepSeek"), FakeModel("Minimax")]
        searcher = FakeSearcher()
        engine = DebateEngine(
            models=models,
            searcher=searcher,
            model_search_config={
                "DeepSeek": {
                    "source": "Research",
                    "tools": ["arxiv", "pubmed"],
                    "prompt": "papers",
                    "enabled": True,
                },
                "Minimax": {
                    "source": "Books",
                    "tools": ["google_books", "open_library"],
                    "prompt": "books",
                    "enabled": True,
                },
            },
            search_settings={
                "max_queries_per_model": 2,
                "max_results_per_source": 3,
                "enable_round_0": True,
            },
        )

        results = await engine.run_round_0_search("agentic rag", "")

        self.assertEqual(results["DeepSeek"], "DeepSeek summary")
        self.assertEqual(results["Minimax"], "Minimax summary")
        self.assertIn({"query": "distributed rag", "sources": ["arxiv", "pubmed"]}, searcher.calls)
        self.assertIn({"query": "agentic retrieval", "sources": ["google_books", "open_library"]}, searcher.calls)

    async def test_round_1_shares_pooled_research_with_all_models(self):
        models = [FakeModel("DeepSeek"), FakeModel("Qwen")]
        engine = DebateEngine(
            models=models,
            searcher=FakeSearcher(),
            model_search_config={"GLM": {"source": "Web", "tools": ["duckduckgo"], "enabled": True}},
        )

        outputs = await engine.run_round_1(
            "what is agentic rag",
            "vision info",
            {"DeepSeek": "paper findings", "Qwen": "arabic findings"},
        )

        self.assertEqual(outputs["DeepSeek"], "DeepSeek response")
        self.assertEqual(outputs["Qwen"], "Qwen response")
        for model in models:
            system_prompt = model.calls[-1]["system_prompt"]
            self.assertIn("POOLED RESEARCH FINDINGS FROM ROUND 0", system_prompt)
            self.assertIn("[DeepSeek] found:\npaper findings", system_prompt)
            self.assertIn("[Qwen] found:\narabic findings", system_prompt)
            self.assertIn("You MAY use the pooled Round 0 research", system_prompt)

    def test_web_searcher_resolves_supported_sources(self):
        searcher = WebSearcher()

        resolved = searcher.resolve_sources(
            ["google_books", "open_library", "archive_org", "github", "stackoverflow", "news", "unknown"]
        )

        self.assertEqual(
            resolved,
            ["google_books", "open_library", "archive_org", "github", "stackoverflow", "news"],
        )

    def test_query_normalization_strips_bullets_and_numbers(self):
        queries = DebateEngine._normalize_generated_queries(
            "1. first query\n2) second query\n- third query",
            "fallback query",
            2,
        )

        self.assertEqual(queries, ["first query", "second query"])


if __name__ == "__main__":
    unittest.main()
