# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Corvid is a permanent cross-project memory layer for AI coding agents (Claude Code, Codex, Gemini CLI). Single Python file (`corvid.py`, ~750 lines), distributed as `corvid-remember` on PyPI. Users say `/remember` in their agent and corvid distills the insight into a searchable markdown article stored at `~/corvid/wiki/`.

## Build and Run

```bash
# Install in development mode
pip install -e .

# Install with semantic search (fastembed + sqlite-vec)
pip install -e ".[lite]"   # keyword-only, no heavy deps

# Run directly
python corvid.py <command>

# Or via installed entry point
corvid <command>
```

No Makefile, no linter, no test suite. The project has zero automated tests.

## Commands

```bash
corvid install                  # Detect agents, install /remember skill, init DB
corvid init                     # Create wiki dir + DB schema only
corvid index <file>             # Index a single markdown file
corvid index-all                # Re-index all wiki/*.md files
corvid search "<query>"         # Human-readable search output
corvid search "<query>" --json  # JSON output (for agent consumption)
corvid search "<q>" --tags x,y  # Filter by tags before searching
corvid facts [subject]          # Show extracted facts (current + superseded)
corvid stats                    # Article counts by category
```

## Architecture

**Single-file monolith**: Everything lives in `corvid.py` — DB schema, indexing, search, CLI, and the embedded SKILL.md template. No internal packages or modules.

**Storage**: SQLite at `~/corvid/corvid.db` (or `$CORVID_HOME/corvid.db`). Six tables:
- `articles` — source of truth (filepath, filehash, title, category, tags, content, source_project, timestamps)
- `articles_fts` — FTS5 with Porter stemming + unicode61 tokenizer, auto-synced via INSERT/DELETE/UPDATE triggers
- `articles_vec` — sqlite-vec for 384-dim embeddings (only created when fastembed + sqlite-vec are installed)
- `facts` — temporal entity-relationship triples (subject, predicate, object, confidence, valid_from, valid_to, article_id)
- `search_hits` — memory feedback loop: records (article_id, query, hit_at) for every search result. Frequently-hit articles get RRF boost (+5% per hit, capped +25%).
- `links` — article relations extracted from markdown links. (source_id, target_id, relation). JSON search output includes `"related"` articles.

**Hybrid search with RRF**: Keyword (FTS5/BM25) always runs. Semantic (fastembed ONNX + sqlite-vec) runs if available. Results merged via Reciprocal Rank Fusion (k=60) — results both methods agree on rank highest (`hybrid` tag). Optional `--tags` pre-filtering narrows the search space before computing similarity.

**Temporal facts**: During indexing, regex patterns extract structured facts from article content. When a new fact contradicts an existing one (same subject+predicate, different object), the old fact gets `valid_to` set rather than deleted. History is preserved.

**Smart snippets**: Keyword results use FTS5 64-char snippets. Semantic results use `_best_paragraph()` which scores paragraphs by query word overlap and returns the most relevant one — not the first 200 chars.

**Graceful degradation**: `_SEMANTIC_AVAILABLE` flag set at import time via try/except. All semantic code paths check this flag. The tool works fine keyword-only.

**Change detection**: SHA256 filehash on article content. `cmd_index` upserts — skips unchanged files, updates on hash mismatch.

**Skill installation**: `corvid install` checks for `~/.claude` and `~/.codex` directories, writes `SKILL.md` into each agent's skill directory. The skill template is embedded as `_SKILL_MD` in corvid.py. A copy also exists at `skills/remember/SKILL.md` — these must stay in sync.

**PreToolUse hook**: `corvid install` writes a Python hook to `~/.claude/hooks/corvid_remind.py` and registers it in `~/.claude/settings.json`. Fires before Bash/Glob/Grep with a wiki reminder. Skips self-triggering on corvid commands.

**Auto-migration**: `get_db()` detects missing columns (`tags`, `confidence`) and tables (`facts`, `search_hits`, `links`) on existing databases and adds them automatically. No need to delete `corvid.db` when upgrading.

## Key Design Decisions

- **Markdown is source of truth**, database is disposable. `corvid index-all` rebuilds from scratch.
- **No config files**. Only env var is `CORVID_HOME` (default `~/corvid`).
- **CPU-only inference**. Embedding model is BAAI/bge-small-en-v1.5 (33MB, ONNX via fastembed). No GPU, no API calls.
- **Lazy model loading**. `_get_embedding_model()` initializes on first use, not at import.

## Paths

| Constant | Default | Purpose |
|---|---|---|
| `WIKI_DIR` | `~/corvid` | Root wiki directory |
| `DB_PATH` | `~/corvid/corvid.db` | SQLite database |
| `ARTICLES_DIR` | `~/corvid/wiki` | Markdown articles by category |
