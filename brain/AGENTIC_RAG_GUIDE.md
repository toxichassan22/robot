# 🧠 Agentic RAG System - Complete Guide

## 📋 Overview

Your robot now has **Agentic RAG** (Retrieval-Augmented Generation) capability. Before the 5 AI models start thinking, they each **search the internet broadly**, then enrich the result with their own focus areas when useful.

## 🔄 How It Works

### Before (Old System - 6 Rounds):
```
Round 1-5: Models think using only their internal knowledge
Round 6: DeepSeek synthesizes final answer
```

### Now (New System - 7 Rounds):
```
Round 0: 🆕 Each model searches the internet
Round 1-5: Models think using search results + internal knowledge
Round 6: DeepSeek synthesizes final answer
```

## 🔍 Round 0: Distributed Search

Each of the 5 models starts with broad web search, then adds a focus area:

| Model | Searches | Best For |
|-------|----------|----------|
| **DeepSeek** | Web + papers + scientific references | Research, academic topics |
| **Minimax** | Web + books + long-form references | Comprehensive information |
| **Qwen** | Web + Arabic/regional coverage | Arabic content |
| **Nemotron** | Web + GitHub + Stack Overflow + technical refs | Technical/scientific data |
| **GLM** | Broad multilingual web search | General current information |

## 📝 Example Flow

**User asks:** "What are the latest advances in quantum computing?"

1. **Round 0 (Search):**
   - DeepSeek searches the open web, then strengthens results with papers
   - Qwen searches the open web with extra Arabic coverage
   - Nemotron searches the open web plus technical sources
   - All models gather real-time information

2. **Round 1-5 (Debate):**
   - Each model uses their search findings + internal knowledge
   - They debate and refine their answers

3. **Round 6 (Synthesis):**
   - DeepSeek creates final answer combining all insights

## 🚀 Usage

### Test the Search System:
```bash
cd brain
python -m brain.tests.test_agentic_rag
```

### Run Full System (includes search automatically):
```bash
cd brain
python -m brain.runtime
```

## ⚙️ Configuration

Edit `brain/config/search_config.py` to customize:

```python
# Enable/disable search for specific models
MODEL_SEARCH_CONFIG = {
    "DeepSeek": {
        "enabled": True  # Set to False to skip search
    }
}

# Master switch
SEARCH_SETTINGS = {
    "enable_round_0": True  # Set to False to disable all search
}
```

## 📦 Dependencies

The system uses free APIs (no API keys needed):
- ✅ DuckDuckGo (web search)
- ✅ arXiv (academic papers)
- ✅ Wikipedia (multi-language)

Optional (for better results):
- Google Custom Search API
- Bing Search API
- Serper API

## 🎯 Benefits

1. **More Accurate Answers**: Models have access to current information
2. **Diverse Sources**: Each model searches different areas
3. **Better Coverage**: Combines research + web + books + technical docs
4. **Multi-lingual**: Searches Arabic, English, and Asian sources
5. **Automatic**: No manual intervention needed

## ⚡ Performance

- **Search Time**: ~5-15 seconds (parallel searches)
- **Total Debate Time**: ~60-120 seconds (including search)
- **Fail-safe**: If search fails, model uses internal knowledge

## 🔧 Troubleshooting

**Search failing?**
- Check internet connection
- Some sources may be rate-limited
- Models will fallback to internal knowledge

**Want faster responses?**
- Disable Round 0 in config: `"enable_round_0": False`
- Reduce `max_queries_per_model` from 3 to 2

**Want better results?**
- Add paid API keys in `search_config.py`
- Increase `max_results_per_source`

## 📊 What Changed in Code

1. **`brain/debate_engine.py`**:
   - Added `run_round_0_search()` method
   - Added `_search_with_model()` method
   - Modified `run_round_1()` to accept search context
   - Modified `start_debate()` to run Round 0 first

2. **`brain/libs/web_search.py`** (NEW):
   - Multi-source search utility
   - DuckDuckGo, arXiv, Wikipedia integration
   - Parallel search execution

3. **`brain/config/search_config.py`** (NEW):
   - Configuration for search behavior
   - Model-to-source mapping

## 🎓 Technical Details

### Search Process:
1. Model generates 3 optimized search queries
2. System searches multiple sources in parallel
3. Results are formatted and sent back to model
4. Model summarizes findings for use in debate

### Error Handling:
- If search fails → model uses internal knowledge
- If timeout → skips that source
- All errors are logged for debugging

## 🚀 Next Steps (Future Enhancements)

You mentioned there's another important issue. Some possible improvements:
- Add more search sources (Google Scholar, news APIs)
- Implement caching for frequently searched topics
- Add relevance scoring to filter search results
- Enable/disable search per query type

---

**Ready to test?** Run `python brain/tests/test_agentic_rag.py` and see your models search in action.
