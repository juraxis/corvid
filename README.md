# corvid

A permanent memory layer for AI coding agents. Installs as a native skill. One command: `/remember`.

Inspired by Karpathy's [llm-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) for building knowledge bases with LLMs, but instead of ingesting external docs, corvid captures what you learn during the conversation itself.

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

Keyword search works out of the box (SQLite FTS5, Porter stemming). "Finetuning" matches "fine-tuned."

With the full install, semantic search runs on a 33MB local model. "Login callback issue" finds your article about "OAuth redirect" even though it never uses those words. No GPU. No server. No API calls.

```bash
corvid search "oauth redirect"
corvid search "liability caps" --json
corvid stats
```

## Built-in memory vs corvid

| | Built-in | corvid |
|---|---|---|
| Scope | Per-project | Cross-project |
| Limit | ~200 lines | Unlimited |
| Search | None | Keyword + semantic |
| Control | Agent decides | You decide with `/remember` |

## What people save

- The auth fix that works locally but breaks after deploy
- The contract clause taxonomy the parser needs to handle
- The database index that stopped the timeout
- The API behavior that is not in the docs
- The architecture decision and why you made it
- The deploy config that makes CI pass after it randomly started failing

## What gets saved

Your agent writes markdown articles by category. You never touch the structure.

```
~/corvid/
  corvid.db          # search index (disposable, rebuildable)
  INDEX.md           # table of contents your agent maintains
  wiki/
    auth/
      google-oauth-deploy-gotchas.md
    contracts/
      liability-cap-types.md
    backend/
      supabase-rls-service-role.md
```

Real articles with tables, exact values, commands, reasoning. Not chat logs.

## Under the hood

One Python file. [SQLite FTS5](https://www.sqlite.org/fts5.html) for keyword search. [sqlite-vec](https://github.com/asg017/sqlite-vec) for vector search. [fastembed](https://github.com/qdrant/fastembed) for embeddings (ONNX, CPU-only, 33MB). Everything local. Database is disposable, rebuild anytime with `corvid index-all`.

## Commands

| Command | What it does |
|---|---|
| `corvid install` | Detect agents, install `/remember` skill, init database |
| `corvid search <query>` | Search (human-readable) |
| `corvid search <query> --json` | Search (JSON for agents) |
| `corvid index <file>` | Index one markdown file |
| `corvid index-all` | Re-index everything |
| `corvid stats` | Show article counts |

## License

MIT
