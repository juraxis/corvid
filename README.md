# corvid

A permanent memory layer for AI coding agents.

Save what matters with `/remember`. Retrieve it from any project with search. Stop re-solving the same problem twice.

Works with Claude Code, Codex, Gemini CLI, or any agent that can run a shell command. One Python file, zero required dependencies.

## Why

The expensive part of working with AI is not writing things down. It is re-learning the same thing three months later in a different project.

Built-in AI memory is per-project, short, and has no search. You solve a hard problem on Monday, start a new project on Friday, and your agent has no idea it ever happened.

corvid fixes that. Every project feeds one shared knowledge base. Search finds things by meaning, not just keywords. A 33MB local model runs the semantic search on your CPU in milliseconds. No server, no API calls, no GPU.

## Who this is for

### The full-stack vibe-coder

You just spent an hour figuring out why Google OAuth works locally but fails after deploy. The callback URL is case-sensitive, `localhost` vs `127.0.0.1` matters, and the consent screen needs the exact redirect URI or it silently 400s.

```
You: /remember the Google OAuth deploy gotchas

corvid writes:
  ~/corvid/wiki/auth/google-oauth-deploy-gotchas.md

  # Google OAuth Deploy Issues
  Three things break after deploy that work locally:
  1. Callback URL must match EXACT casing in Google Console
     (localhost:3000 != 127.0.0.1:3000)
  2. Consent screen redirect URI must include the production
     domain with https, not just the path
  3. Cookie SameSite=None + Secure required behind reverse proxy
  Symptoms: silent 400 on redirect, no error in server logs.
```

Next project, same auth setup. Your agent finds the article before you even hit the bug.

### The lawyer vibe-coding a legal tool

You are building a contract review feature and just learned that limitation-of-liability clauses come in five flavors that your parser needs to handle differently: hard caps, consequential damages waivers, exclusive remedies, limitations periods, and super-caps with carve-outs.

```
You: /remember the five types of liability caps we found during testing

corvid writes:
  ~/corvid/wiki/contracts/liability-cap-types.md

  # Five Types of Liability Caps
  | Type | Pattern | Example |
  |------|---------|---------|
  | Hard cap | "shall not exceed $X" | Fixed dollar amount |
  | Consequential waiver | "no indirect damages" | Excludes lost profits |
  | Exclusive remedy | "sole remedy shall be..." | Limits recourse type |
  | Limitations period | "no action after X months" | Time-based bar |
  | Super-cap with carve-outs | Cap + exceptions for IP/breach | Hybrid structure |
  Parser must check for ALL five, not just the explicit "cap" keyword.
```

Next time you build anything that touches contracts, your agent already knows the taxonomy.

### The solo builder shipping across side projects

One month it is a Next.js app with Supabase auth. Then a Python CLI with Stripe billing. Then a mobile app with push notifications. Each stack has quirks that took real time to figure out.

```
You: /remember how we got Supabase row-level security working with the service role key

corvid writes:
  ~/corvid/wiki/backend/supabase-rls-service-role.md

  # Supabase RLS with Service Role Key
  RLS policies block the service role by default in edge functions.
  Fix: use supabase.auth.admin methods, not the regular client.
  The service_role key bypasses RLS only when using the admin API.
  Regular supabaseClient.from('table') still respects RLS policies
  even with the service key in headers. This is by design.
```

Six months later, different project, same stack. You do not re-learn it. You do not re-Google it. Your agent searches corvid and gets the answer in seconds.

## What people actually save

- The auth fix that works locally but breaks after deploy
- The database query that needed a specific index to stop timing out
- The CSS layout trick that finally worked after three Stack Overflow answers
- The contract clause taxonomy the parser needs to handle
- The API rate limit workaround that is not in the docs
- The architecture decision and why you made it
- The config that makes CI pass after it randomly started failing

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
pip install corvid-remember
corvid install
```

That is it. Two commands. `pip install` gets the CLI and all dependencies (semantic search included). `corvid install` auto-detects your agents (Claude Code, Codex CLI) and installs the `/remember` skill for each.

```
$ corvid install

  ✓ Claude Code      → ~/.claude/skills/remember/SKILL.md
  ✓ Codex CLI        → ~/.codex/skills/remember/SKILL.md

  Wiki: ~/corvid
  Semantic search: enabled (BAAI/bge-small-en-v1.5)

  Done. Use /remember in your next session.
```

Open any project. Say `/remember`. Done.

### Alternative: install via npx skills

```bash
npx skills add juraxis/corvid
pip install fastembed sqlite-vec   # for semantic search
corvid init                        # or: python3 ~/.claude/skills/remember/corvid.py init
```

### Keyword-only mode (no heavy dependencies)

```bash
pip install corvid-remember[lite]
corvid install
```

Keyword search works out of the box via SQLite FTS5. Semantic search requires the full install.

## Search

Keyword search works out of the box via SQLite FTS5 with Porter stemming and BM25 ranking. "Finetuning" matches "fine-tuned."

With `fastembed` + `sqlite-vec` installed, semantic search activates automatically. Searching "concurrent writes deadlock" finds your article about a "race condition" even though it never uses those words. The embedding model ([bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)) is 33MB, runs on CPU in ~50ms per article, and needs no GPU, no PyTorch, no server.

Both modes run together. Falls back to keyword-only silently if the packages are not installed.

```bash
corvid search "oauth redirect"
corvid search "supabase row level security" --json
corvid stats
```

## What gets saved

Your agent writes markdown articles organized by category. You never touch the structure.

```
~/corvid/
  corvid.py          # one file, Python stdlib + optional fastembed/sqlite-vec
  corvid.db          # search index (disposable, rebuildable from articles)
  INDEX.md           # table of contents your agent maintains
  wiki/
    auth/
      google-oauth-deploy-gotchas.md
    backend/
      supabase-rls-service-role.md
    contracts/
      liability-cap-types.md
```

Real articles. Tables, exact values, specific commands, reasoning. Not chat logs.

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

corvid is one Python file. The search index is [SQLite FTS5](https://www.sqlite.org/fts5.html) for keyword search and [sqlite-vec](https://github.com/asg017/sqlite-vec) for vector search, both inside the same SQLite database. Embeddings come from [fastembed](https://github.com/qdrant/fastembed) (ONNX Runtime, CPU-only, 33MB model). No external services. Everything runs locally.

The database is disposable. Delete it and run `corvid index-all` to rebuild from the markdown files. The articles are always the source of truth.

## Commands

| Command | What it does |
|---|---|
| `corvid install` | Detect agents, install skill, init database |
| `corvid init` | Create the database and wiki directory |
| `corvid index <file>` | Index one markdown file |
| `corvid index-all` | Re-index all files in wiki/ |
| `corvid search <query>` | Search (human-readable) |
| `corvid search <query> --json` | Search (JSON for agents) |
| `corvid stats` | Show article counts |

## License

MIT
