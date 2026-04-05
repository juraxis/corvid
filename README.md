# corvid

A permanent memory layer for AI coding agents.

Save what matters with `/remember`. Retrieve it from any project with search. Stop re-solving the same problem twice.

Claude Code, Codex, Gemini CLI, or any agent that can run a shell command. One Python file, one skill file, works everywhere.

## Why

The expensive part of working with AI is not writing things down. It is re-learning the same thing three months later in a different project.

Built-in AI memory is per-project, short, and has no search. You solve a hard problem on Monday, start a new project on Friday, and your agent has no idea it ever happened.

corvid fixes that. Every project feeds one shared knowledge base. Search finds things by meaning, not just keywords. A 33MB local model runs the semantic search on your CPU in milliseconds. No server, no API calls, no GPU.

## Who this is for

### The agentic coder

You spend 90 minutes figuring out why a background job deadlocks only under production concurrency.

```
You: /remember
```

corvid saves the root cause, what looked misleading, the fix, and how to verify it. Three projects later, same stack, similar symptom. Your agent finds the article and starts from the answer.

### The lawyer working with AI

You are reviewing a target's contracts and find that a change-of-control clause puts a meaningful share of revenue at risk.

```
You: /remember
```

corvid saves the clause pattern, why it matters, what follow-up to request, and what mitigation language actually worked. Next deal, same pattern. Your agent already knows what to flag.

### The vibe-coder with too many projects

One week it is a deploy config. Next week a webhook edge case. Then a schema drift between local and remote. Each one takes an hour. Each one feels obvious after you solve it. Each one gets forgotten anyway.

```
You: /remember
```

Those become searchable articles instead of disappearing into chat history.

## What people actually save

- The deploy fix that only breaks in production
- The clause pattern that killed a deal
- The migration sequence that avoided data loss
- The negotiation fallback language that got accepted
- The API behavior nobody documented
- The architecture decision and the reasoning behind it
- The research summary you do not want to recreate in six weeks

## How it compares to built-in memory

| | Built-in agent memory | corvid |
|---|---|---|
| Scope | Per-project | Cross-project |
| Size | Truncates at ~200 lines | Unlimited articles |
| Search | None | Keyword + semantic (finds by meaning) |
| Control | Agent decides what to save | You decide with `/remember` |
| Retrieval | Only in that one project | Any project, any session |
| Format | Short notes | Full articles with tables, numbers, reasoning |

## Setup

```bash
pip install corvid-wiki
corvid init
```

That is it. corvid creates `~/corvid/` with the database and wiki directory.

To connect it to Claude Code:

```bash
corvid install-skill
```

This drops the skill file into `~/.claude/skills/remember/`. Now `/remember` works in every session.

For other agents (Codex, Gemini CLI, Cursor), add this to your agent's system instructions or project config:

```
Before starting work, search for relevant knowledge:
python3 ~/corvid/corvid.py search "<topic>" --json

When the user says /remember, distill the insight and save it:
write to ~/corvid/wiki/<category>/<slug>.md
then run: python3 ~/corvid/corvid.py index <filepath>
```

### Optional: semantic search

```bash
pip install fastembed sqlite-vec
```

This adds a 33MB embedding model that runs locally on CPU. Now searching "concurrent writes deadlock" finds your article about a "race condition" even though it never uses those words. No GPU, no PyTorch, no server, no API calls.

Without these packages, corvid falls back to keyword search silently. Both modes work. Both are fast.

## Search

```bash
corvid search "change of control"
corvid search "indemnity structure" --json
corvid stats
```

Keyword search uses SQLite FTS5 with Porter stemming and BM25 ranking. "Finetuning" matches "fine-tuned."

With semantic search enabled, corvid also finds articles by meaning. Both results are merged: keyword matches first, then semantic fills in what keyword missed.

## What gets saved

Your agent writes markdown articles organized by category. You never touch the structure.

```
~/corvid/
  corvid.py          # one file, Python stdlib + optional fastembed/sqlite-vec
  corvid.db          # search index (disposable, rebuildable from articles)
  INDEX.md           # table of contents your agent maintains
  wiki/
    contracts/
      indemnity-cap-carveouts.md
      coc-termination-risk.md
    debugging/
      job-queue-deadlock-under-load.md
      schema-drift-local-remote.md
```

These are real articles. Tables, exact numbers, specific commands, reasoning. Not chat logs.

## Inspired by Karpathy's LLM Wiki

Karpathy's [llm-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) builds knowledge bases by ingesting external docs into a wiki. corvid borrows the core idea but changes the entry point: your source is the conversation, not external files.

| | Karpathy's LLM Wiki | corvid |
|---|---|---|
| Source | External docs, papers, repos | Your conversation with the agent |
| Ingest | Copy to `raw/`, LLM compiles | `/remember` distills in real-time |
| Search | qmd (BM25 + vector + re-ranking) | Hybrid: FTS5 keyword + semantic vector |
| Best for | Research knowledge | Working knowledge |

His system is a research librarian. This is a working notebook. They compose if you want both.

## Under the hood

corvid is one Python file. The search index is [SQLite FTS5](https://www.sqlite.org/fts5.html) for keyword search and [sqlite-vec](https://github.com/asg017/sqlite-vec) for vector search, both running inside the same SQLite database. Embeddings come from [fastembed](https://github.com/qdrant/fastembed) (ONNX Runtime, CPU-only, 33MB model). No external services. Everything runs locally.

The database is a disposable cache. Delete it and run `corvid index-all` to rebuild from the markdown files. The articles are always the source of truth.

## Commands

| Command | What it does |
|---|---|
| `corvid init` | Create the database and wiki directory |
| `corvid index <file>` | Index one markdown file |
| `corvid index-all` | Re-index all files in wiki/ |
| `corvid search <query>` | Search (human-readable) |
| `corvid search <query> --json` | Search (JSON for agents) |
| `corvid stats` | Show article counts |
| `corvid install-skill` | Install the /remember skill for Claude Code |

## License

MIT
