"""
Configuration for Agentic RAG Search System
Customize which sources each model searches
"""

# Search configuration for each model.
# Keep tool names aligned with the concrete handlers implemented in
# `brain/libs/web_search.py` to avoid "prompt-only" source claims.

MODEL_SEARCH_CONFIG = {
    "DeepSeek": {
        "source": "Web-Wide Search With Research Focus",
        "tools": ["duckduckgo", "news", "wikipedia", "arxiv", "semantic_scholar", "pubmed"],
        "description": "Search the open web broadly, then enrich with academic and scientific references",
        "prompt": "Search the web broadly for this query, then strengthen the answer with research papers and scientific references when useful.",
        "enabled": True
    },
    "Minimax": {
        "source": "Web-Wide Search With Long-Form Focus",
        "tools": ["duckduckgo", "news", "wikipedia", "google_books", "open_library", "archive_org"],
        "description": "Search the open web broadly, then pull in books and long-form references when helpful",
        "prompt": "Search the web broadly for this query, then look for books and long-form references that add depth.",
        "enabled": True
    },
    "Qwen": {
        "source": "Web-Wide Search With Arabic Focus",
        "tools": ["duckduckgo", "news", "wikipedia", "wikipedia_ar"],
        "description": "Search the open web broadly with extra attention to Arabic and regional sources",
        "prompt": "Search the web broadly for this query, with extra effort on Arabic-language and regional coverage.",
        "enabled": True
    },
    "Nemotron": {
        "source": "Web-Wide Search With Technical Focus",
        "tools": ["duckduckgo", "news", "wikipedia", "github", "stackoverflow", "arxiv"],
        "description": "Search the open web broadly, then enrich with technical repos, dev Q&A, and technical references",
        "prompt": "Search the web broadly for this query, then add technical repositories, dev Q&A, and technical references when relevant.",
        "enabled": True
    },
    "GLM": {
        "source": "General Web-Wide Search",
        "tools": ["duckduckgo", "news", "wikipedia", "wikipedia_ar"],
        "description": "Comprehensive multilingual search across the open web",
        "prompt": "Perform broad multilingual web search across the open web and collect general-purpose context for this query.",
        "enabled": True
    }
}

# Search settings
SEARCH_SETTINGS = {
    "max_queries_per_model": 3,        # Number of search queries each model generates
    "max_results_per_source": 5,       # Maximum results from each search source
    "search_timeout_seconds": 10,      # Timeout for each search request
    "enable_round_0": True,            # Master switch for Round 0 search
    "fallback_to_knowledge": True,     # Use internal knowledge if search fails
}

# Advanced: Custom search API configurations
# Uncomment and fill in if you want to use paid APIs for better results
CUSTOM_APIS = {
    # "google_search": {
    #     "api_key": "YOUR_API_KEY",
    #     "search_engine_id": "YOUR_CSE_ID",
    #     "enabled": False
    # },
    # "bing_search": {
    #     "api_key": "YOUR_API_KEY",
    #     "enabled": False
    # },
    # "serper_api": {
    #     "api_key": "YOUR_API_KEY",
    #     "enabled": False
    # }
}
