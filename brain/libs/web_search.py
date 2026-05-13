"""
Web Search Utilities for Agentic RAG.
Supports real multi-source search handlers plus a few compatibility aliases.
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from urllib.parse import quote_plus

logger = logging.getLogger("Brain.Search")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


class WebSearcher:
    """Multi-source web search utility with configurable handlers."""

    SOURCE_ALIASES = {
        "duckduckgo": "duckduckgo",
        "wikipedia": "wikipedia",
        "wikipedia_ar": "wikipedia_ar",
        "arxiv": "arxiv",
        "semantic_scholar": "semantic_scholar",
        "pubmed": "pubmed",
        "google_books": "google_books",
        "open_library": "open_library",
        "archive_org": "archive_org",
        "github": "github",
        "stackoverflow": "stackoverflow",
        "news": "news",
        "google": "google",
        # Backward-compatible aliases for older configs.
        "arabic_web": "google",
        "asian_sources": "duckduckgo",
        "tech_docs": "google",
    }

    def __init__(self, search_timeout: float = 10.0, max_results_per_source: int = 5):
        self.search_timeout = search_timeout
        self.max_results_per_source = max_results_per_source
        self._source_handlers: Dict[str, Callable[..., object]] = {
            "duckduckgo": self.search_duckduckgo,
            "wikipedia": self.search_wikipedia,
            "wikipedia_ar": self.search_wikipedia_ar,
            "arxiv": self.search_arxiv,
            "semantic_scholar": self.search_semantic_scholar,
            "pubmed": self.search_pubmed,
            "google_books": self.search_google_books,
            "open_library": self.search_open_library,
            "archive_org": self.search_archive_org,
            "github": self.search_github,
            "stackoverflow": self.search_stackoverflow,
            "news": self.search_news,
            "google": self.search_google,
        }

    @staticmethod
    def _truncate(text: object, limit: int = 300) -> str:
        value = " ".join(str(text or "").split())
        return value[:limit]

    def resolve_sources(self, sources: Optional[List[str]]) -> List[str]:
        if not sources:
            return ["duckduckgo", "wikipedia"]

        resolved: List[str] = []
        for source in sources:
            canonical = self.SOURCE_ALIASES.get(source)
            if not canonical:
                logger.warning("Unsupported search source '%s' ignored", source)
                continue
            if canonical not in resolved:
                resolved.append(canonical)
        return resolved or ["duckduckgo"]

    async def search_duckduckgo(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Free DuckDuckGo HTML search (no API key needed)."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://lite.duckduckgo.com/lite/",
                    data={"q": query},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                    },
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "html.parser")
            results: List[SearchResult] = []

            for tr in soup.select("tr"):
                td = tr.select_one("td.result-snippet")
                if td:
                    snippet = self._truncate(td.get_text(" ", strip=True), 300)
                    prev_tr = tr.find_previous_sibling("tr")
                    if prev_tr:
                        a_tag = prev_tr.select_one("a.result-url") or prev_tr.find("a")
                        if a_tag:
                            title = self._truncate(a_tag.get_text(" ", strip=True), 200)
                            url = a_tag.get("href", "")
                            results.append(SearchResult(title=title, url=url, snippet=snippet, source="DuckDuckGo"))
                            if len(results) >= max_results:
                                break

            return results
        except ImportError:
            logger.warning("BeautifulSoup not installed. Falling back to simplified DDG parsing.")
            return await self._simple_ddg_search(query, max_results)
        except Exception as e:
            logger.error("DuckDuckGo search failed: %s", e)
            return []

    async def _simple_ddg_search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Simple DDG search without BeautifulSoup."""
        del max_results
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://lite.duckduckgo.com/lite/",
                    data={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            text = response.text[:2000]
            return [
                SearchResult(
                    title=f"DDG results for: {query}",
                    url="",
                    snippet=self._truncate(text, 500),
                    source="DuckDuckGo",
                )
            ]
        except Exception as e:
            logger.error("Simple DDG search failed: %s", e)
            return []

    async def search_google(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Free Google HTML search using beautifulsoup."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.google.com/search",
                    params={"q": query, "hl": "ar"}, # Force Arabic locale
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "ar,en-US;q=0.7,en;q=0.3",
                    },
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "html.parser")
            results: List[SearchResult] = []

            for g in soup.select("div.g"):
                a_tag = g.select_one("a")
                title_tag = g.select_one("h3")
                
                # Several possible classes for snippets in Google
                snippet_tag = g.select_one("div.VwiC3b") or g.select_one("div.IsZvec") or g.select_one("span.aCOpRe")

                if not a_tag or not title_tag:
                    continue

                title = title_tag.get_text(" ", strip=True)
                url = a_tag.get("href", "")
                snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""

                if title and url and url.startswith("http"):
                    results.append(
                        SearchResult(
                            title=self._truncate(title, 200),
                            url=url,
                            snippet=self._truncate(snippet, 300),
                            source="Google Search"
                        )
                    )
                    if len(results) >= max_results:
                        break

            return results
        except Exception as e:
            logger.error("Google search failed: %s", e)
            return []

    async def search_arxiv(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search academic papers on arXiv."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://export.arxiv.org/api/query",
                    params={"search_query": f"all:{query}", "max_results": max_results},
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            root = ET.fromstring(response.text)
            results: List[SearchResult] = []
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns)[:max_results]:
                title = entry.findtext("atom:title", default="", namespaces=ns).strip()
                summary = entry.findtext("atom:summary", default="", namespaces=ns).strip()
                url = entry.findtext("atom:id", default="", namespaces=ns).strip()
                if not title:
                    continue
                results.append(
                    SearchResult(
                        title=self._truncate(title, 200),
                        url=url,
                        snippet=self._truncate(summary, 300),
                        source="arXiv",
                    )
                )
            return results
        except Exception as e:
            logger.error("arXiv search failed: %s", e)
            return []

    async def search_wikipedia(self, query: str, language: str = "en", max_results: Optional[int] = None) -> List[SearchResult]:
        """Search Wikipedia via the public Action API."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://{language}.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "format": "json",
                        "srsearch": query,
                        "srlimit": max_results,
                    },
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            data = response.json()
            results: List[SearchResult] = []
            for item in data.get("query", {}).get("search", [])[:max_results]:
                title = item.get("title", "")
                if not title:
                    continue
                results.append(
                    SearchResult(
                        title=title,
                        url=f"https://{language}.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                        snippet=self._truncate(item.get("snippet", ""), 300),
                        source=f"Wikipedia ({language})",
                    )
                )
            return results
        except Exception as e:
            logger.error("Wikipedia search failed: %s", e)
            return []

    async def search_wikipedia_ar(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        return await self.search_wikipedia(query, language="ar", max_results=max_results)

    async def search_semantic_scholar(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search Semantic Scholar public graph API."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params={
                        "query": query,
                        "limit": max_results,
                        "fields": "title,abstract,url,year",
                    },
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            data = response.json()
            return [
                SearchResult(
                    title=self._truncate(item.get("title", ""), 200),
                    url=item.get("url", ""),
                    snippet=self._truncate(item.get("abstract", ""), 300),
                    source="Semantic Scholar",
                )
                for item in data.get("data", [])[:max_results]
                if item.get("title")
            ]
        except Exception as e:
            logger.error("Semantic Scholar search failed: %s", e)
            return []

    async def search_pubmed(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search PubMed via NCBI E-utilities."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                search_response = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={
                        "db": "pubmed",
                        "retmode": "json",
                        "retmax": max_results,
                        "term": query,
                    },
                    timeout=self.search_timeout,
                )
                if search_response.status_code != 200:
                    return []

                ids = search_response.json().get("esearchresult", {}).get("idlist", [])
                if not ids:
                    return []

                summary_response = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                    params={
                        "db": "pubmed",
                        "retmode": "json",
                        "id": ",".join(ids[:max_results]),
                    },
                    timeout=self.search_timeout,
                )
                if summary_response.status_code != 200:
                    return []

            data = summary_response.json().get("result", {})
            results: List[SearchResult] = []
            for paper_id in ids[:max_results]:
                item = data.get(str(paper_id), {})
                title = item.get("title", "")
                if not title:
                    continue
                authors = ", ".join(author.get("name", "") for author in item.get("authors", [])[:3] if author.get("name"))
                snippet = f"{item.get('pubdate', '')}. {authors}".strip(". ")
                results.append(
                    SearchResult(
                        title=self._truncate(title, 200),
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{paper_id}/",
                        snippet=self._truncate(snippet, 300),
                        source="PubMed",
                    )
                )
            return results
        except Exception as e:
            logger.error("PubMed search failed: %s", e)
            return []

    async def search_google_books(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search Google Books public API."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={"q": query, "maxResults": min(max_results, 40)},
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            data = response.json()
            results: List[SearchResult] = []
            for item in data.get("items", [])[:max_results]:
                volume = item.get("volumeInfo", {})
                title = volume.get("title", "")
                if not title:
                    continue
                authors = ", ".join(volume.get("authors", [])[:3])
                description = volume.get("description", "")
                results.append(
                    SearchResult(
                        title=self._truncate(title, 200),
                        url=volume.get("infoLink", ""),
                        snippet=self._truncate(f"{authors}. {description}".strip(". "), 300),
                        source="Google Books",
                    )
                )
            return results
        except Exception as e:
            logger.error("Google Books search failed: %s", e)
            return []

    async def search_open_library(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search Open Library."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://openlibrary.org/search.json",
                    params={"q": query, "limit": max_results},
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            data = response.json()
            results: List[SearchResult] = []
            for item in data.get("docs", [])[:max_results]:
                title = item.get("title", "")
                if not title:
                    continue
                key = item.get("key", "")
                author = ", ".join(item.get("author_name", [])[:3])
                year = item.get("first_publish_year", "")
                results.append(
                    SearchResult(
                        title=self._truncate(title, 200),
                        url=f"https://openlibrary.org{key}" if key else "",
                        snippet=self._truncate(f"{author}. First published: {year}".strip(". "), 300),
                        source="Open Library",
                    )
                )
            return results
        except Exception as e:
            logger.error("Open Library search failed: %s", e)
            return []

    async def search_archive_org(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search Internet Archive metadata."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://archive.org/advancedsearch.php",
                    params={
                        "q": query,
                        "fl[]": ["identifier", "title", "description"],
                        "rows": max_results,
                        "page": 1,
                        "output": "json",
                    },
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            docs = response.json().get("response", {}).get("docs", [])
            results: List[SearchResult] = []
            for item in docs[:max_results]:
                title = item.get("title", "")
                identifier = item.get("identifier", "")
                description = item.get("description", "")
                if not title:
                    continue
                if isinstance(description, list):
                    description = " ".join(str(part) for part in description[:2])
                results.append(
                    SearchResult(
                        title=self._truncate(title, 200),
                        url=f"https://archive.org/details/{identifier}" if identifier else "",
                        snippet=self._truncate(description, 300),
                        source="Internet Archive",
                    )
                )
            return results
        except Exception as e:
            logger.error("Archive.org search failed: %s", e)
            return []

    async def search_github(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search GitHub repositories without requiring authentication."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": query, "per_page": max_results},
                    headers={"Accept": "application/vnd.github+json"},
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            data = response.json()
            return [
                SearchResult(
                    title=self._truncate(item.get("full_name", ""), 200),
                    url=item.get("html_url", ""),
                    snippet=self._truncate(item.get("description", ""), 300),
                    source="GitHub",
                )
                for item in data.get("items", [])[:max_results]
                if item.get("full_name")
            ]
        except Exception as e:
            logger.error("GitHub search failed: %s", e)
            return []

    async def search_stackoverflow(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search Stack Overflow via the public Stack Exchange API."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.stackexchange.com/2.3/search/advanced",
                    params={
                        "order": "desc",
                        "sort": "relevance",
                        "q": query,
                        "site": "stackoverflow",
                        "pagesize": max_results,
                    },
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            data = response.json()
            return [
                SearchResult(
                    title=self._truncate(item.get("title", ""), 200),
                    url=item.get("link", ""),
                    snippet=self._truncate(
                        f"Score: {item.get('score', 0)} | Answers: {item.get('answer_count', 0)}",
                        300,
                    ),
                    source="Stack Overflow",
                )
                for item in data.get("items", [])[:max_results]
                if item.get("title")
            ]
        except Exception as e:
            logger.error("Stack Overflow search failed: %s", e)
            return []

    async def search_news(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search Google News RSS."""
        max_results = max_results or self.max_results_per_source
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://news.google.com/rss/search",
                    params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                    timeout=self.search_timeout,
                )

            if response.status_code != 200:
                return []

            root = ET.fromstring(response.text)
            results: List[SearchResult] = []
            for item in root.findall("./channel/item")[:max_results]:
                title = item.findtext("title", default="").strip()
                url = item.findtext("link", default="").strip()
                description = item.findtext("description", default="").strip()
                if not title:
                    continue
                results.append(
                    SearchResult(
                        title=self._truncate(title, 200),
                        url=url,
                        snippet=self._truncate(description, 300),
                        source="Google News",
                    )
                )
            return results
        except Exception as e:
            logger.error("News search failed: %s", e)
            return []

    async def search_multiple_sources(self, query: str, sources: Optional[List[str]] = None) -> Dict[str, List[SearchResult]]:
        """Search across multiple real sources in parallel."""
        resolved_sources = self.resolve_sources(sources)
        search_tasks = {
            source: self._source_handlers[source](query, self.max_results_per_source)
            for source in resolved_sources
            if source in self._source_handlers
        }

        results = await asyncio.gather(*search_tasks.values(), return_exceptions=True)

        output: Dict[str, List[SearchResult]] = {}
        for source, result in zip(search_tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error("%s search failed: %s", source, result)
                output[source] = []
            else:
                output[source] = result
        return output

    def format_results_for_llm(self, results: Dict[str, List[SearchResult]], max_snippet_length: int = 200) -> str:
        """Format search results into text for LLM consumption."""
        if not results:
            return "No search results found."

        formatted: List[str] = []
        for source, items in results.items():
            if not items:
                continue
            formatted.append(f"\n=== {source.upper()} RESULTS ===")
            for i, item in enumerate(items, 1):
                formatted.append(f"\n{i}. {item.title}")
                formatted.append(f"   URL: {item.url}")
                formatted.append(f"   {item.snippet[:max_snippet_length]}...")
        return "\n".join(formatted) if formatted else "No relevant results found."
