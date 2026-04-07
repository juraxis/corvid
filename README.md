# corvid

A permanent memory layer for AI coding agents. Installs as a native skill. One command: `/remember`.

Inspired by Karpathy's [llm-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) for building knowledge bases with LLMs, but instead of ingesting external docs, corvid captures what you learn during the conversation itself.

### What's new in 0.2.0

Smarter retrieval, fewer tokens, structured knowledge.

- **Reciprocal Rank Fusion** — keyword and semantic results merged by agreement, not appended. Best matches surface first.
- **Tag pre-filtering** — `corvid search "query" --tags deploy,auth` narrows the search space before computing similarity.
- **Temporal facts** — corvid extracts structured facts during indexing. When a fact changes, the old one gets marked superseded, not duplicated. `corvid facts` shows what's current.
- **Smart snippets** — search returns the most relevant paragraph, not the first 200 characters. Agent gets the answer without reading the full file.

## Why

Every AI session starts from zero. You figure something out, close the terminal, and next month your agent has no memory of it.

Built-in memory is per-project, 200 lines, no search. corvid gives you cross-project memory with semantic search. What you figure out once stays figured out.

## Install

```bash
pip install corvid-remember
corvid install
```

`corvid install` detects your agents (Claude Code, Codex, Gemini CLI) and adds `/remember` as a native skill in each one.

```
$ corvid install

  ✓ Claude Code      → ~/.claude/skills/remember/SKILL.md
  ✓ Codex CLI        → ~/.codex/skills/remember/SKILL.md

  Wiki: ~/corvid
  Semantic search: enabled (BAAI/bge-small-en-v1.5)
```

Lightweight mode (keyword search only, no embedding model):

```bash
pip install corvid-remember[lite]
corvid install
```

## How it works

Say `/remember` and your agent distills the current insight into a searchable article:

```
You: /remember the Google OAuth deploy gotchas

corvid writes → ~/corvid/wiki/auth/google-oauth-deploy-gotchas.md

  # Google OAuth Deploy Issues
  Three things break after deploy that work locally:
  1. Callback URL must match EXACT casing in Google Console
  2. Consent screen redirect URI needs the production domain with https
  3. Cookie SameSite=None + Secure required behind reverse proxy
  Symptoms: silent 400 on redirect, no error in server logs.
```

Next session, any project, your agent pulls up what you already solved.

## Search

Two search modes, both local, both fast. Results merged via [Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) — when both methods agree on a result, it ranks highest.

**Keyword** (always on): [SQLite FTS5](https://www.sqlite.org/fts5.html) with Porter stemming and BM25 ranking. "Finetuning" matches "fine-tuned." Zero dependencies.

**Semantic** (full install): [fastembed](https://github.com/qdrant/fastembed) generates embeddings with a 33MB model ([bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)), [sqlite-vec](https://github.com/asg017/sqlite-vec) stores and searches them inside the same SQLite database. "Login callback issue" finds your article about "OAuth redirect" even though it never uses those words. Runs on CPU in ~50ms. No GPU. No server. No API calls.

**Tag filtering**: Articles can include a `tags:` line. Search with `--tags` to narrow results before computing similarity — fewer results, higher precision.

```bash
corvid search "oauth redirect"
corvid search "deploy config" --tags gcp,docker
corvid search "liability caps" --json
```

## Built-in memory vs corvid

No clash — they complement. Built-in memory loads everything every turn for project prefs; corvid uses embeddings to retrieve only what's relevant, so you store more knowledge while consuming fewer tokens per conversation.

| | Built-in | corvid |
|---|---|---|
| Scope | Per-project | Cross-project |
| Limit | ~200 lines | Unlimited |
| Retrieval | Entire file loaded into context | Search by keyword + semantic similarity |
| Token cost | Grows with memory size | Only relevant results enter context |
| Control | You or agent decides | You decide with `/remember` |

## What people save

- The auth fix that works locally but breaks after deploy
- The contract clause taxonomy the parser needs to handle
- The database index that stopped the timeout
- The API behavior that is not in the docs
- The architecture decision and why you made it
- The deploy config that makes CI pass after it randomly started failing

## What gets saved

Your agent writes markdown articles by category with tags for search filtering. You never touch the structure.

```
~/corvid/
  corvid.db          # search index (disposable, rebuildable)
  INDEX.md           # table of contents your agent maintains
  wiki/
    auth/
      google-oauth-deploy-gotchas.md    # tags: auth, deploy, oauth
    contracts/
      liability-cap-types.md            # tags: contracts, liability
    backend/
      supabase-rls-service-role.md      # tags: supabase, rls, auth
```

Real articles with tables, exact values, commands, reasoning. Not chat logs.

## Temporal facts

corvid extracts structured facts from articles during indexing. When a fact changes, the old one gets marked as superseded — not deleted.

```
$ corvid facts Backend
  Backend → uses → Postgres 16
  Backend → uses → Postgres 15 [superseded 2025-11-03]
```

No more contradicting articles sitting side by side. You know what's current and what's history.

## Under the hood

One Python file. [SQLite FTS5](https://www.sqlite.org/fts5.html) for keyword search. [sqlite-vec](https://github.com/asg017/sqlite-vec) for vector search. [fastembed](https://github.com/qdrant/fastembed) for embeddings (ONNX, CPU-only, 33MB). Results ranked by [Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf). Tag-based pre-filtering narrows the search space before computing similarity. Temporal facts table tracks when knowledge gets superseded. Everything local. Database is disposable, rebuild anytime with `corvid index-all`.

## Commands

| Command | What it does |
|---|---|
| `corvid install` | Detect agents, install `/remember` skill, init database |
| `corvid search <query>` | Search (human-readable) |
| `corvid search <query> --json` | Search (JSON for agents) |
| `corvid search <q> --tags x,y` | Filter by tags before searching |
| `corvid facts [subject]` | Show extracted facts (current + superseded) |
| `corvid index <file>` | Index one markdown file |
| `corvid index-all` | Re-index everything |
| `corvid stats` | Show article counts |

## License

MIT
