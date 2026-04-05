# claude-wiki

A cross-project knowledge base for Claude Code. One slash command, one Python script, zero dependencies.

Say `/remember` and Claude distills what you just learned into a searchable wiki. Next session, next project, next month, it is still there.

## Why not just use Claude's built-in memory?

Claude Code already has memory at `~/.claude/projects/*/memory/`. It is fine for a single project. But if you work across many projects, you will hit these walls:

| | Built-in memory | claude-wiki |
|---|---|---|
| Scope | Per-project | Cross-project, one wiki for everything |
| Limit | Truncates at 200 lines | Unlimited articles |
| Search | None, loads files in order | Full-text search with ranking (SQLite FTS5) |
| Trigger | Claude decides automatically | You decide with `/remember` |
| Access | Only in that project | Searchable from any project |

One project? Built-in memory works. Five projects? Ten? You need knowledge that travels with you.

## How it works

### A lawyer reviewing an M&A deal

You are three sessions deep into diligence. You just discovered that the target's key customer contract has a change-of-control termination right covering 38% of ARR.

```
You: /remember

Claude writes:
  ~/claude-wiki/wiki/contracts/acme-coc-termination-risk.md

  # Acme Acquisition - Change of Control Risk
  Key customer contract (38% of ARR, $4.2M) contains change-of-control
  termination right in Section 12.3. No consent obtained. Must be
  closing condition or renegotiated pre-sign...
```

Two weeks later, different project, different client. Similar deal structure.

```
You: "Review this target's customer contracts for COC risk"

Claude searches the wiki automatically
  -> finds the Acme article
  -> already knows the pattern, the risk, and what to look for
```

You never re-explained. You never re-discovered. The lesson carried over.

### A developer shipping across repos

You spent an hour figuring out that the Gemini Flex tier needs `google-genai` v1.70+ and that batch API jobs on preview models can stall indefinitely.

```
You: /remember

Claude writes:
  ~/claude-wiki/wiki/infrastructure/gemini-flex-tier.md
```

Next month, different repo, you need Gemini again. Claude finds the article, skips the hour of debugging, and uses Flex from the start.

## Setup (2 minutes)

### 1. Copy the files

```bash
mkdir -p ~/claude-wiki/wiki
mkdir -p ~/.claude/skills/remember
cp wiki.py ~/claude-wiki/wiki.py
cp SKILL.md ~/.claude/skills/remember/SKILL.md
```

### 2. Initialize

```bash
python3 ~/claude-wiki/wiki.py init
```

That creates the SQLite database. Done.

### 3. Use it

Open Claude Code in any project and say `/remember`. Claude distills the current insight, writes an article, indexes it, and updates the table of contents.

To search manually:

```bash
python3 ~/claude-wiki/wiki.py search "change of control"
python3 ~/claude-wiki/wiki.py search "indemnity cap" --json
python3 ~/claude-wiki/wiki.py stats
```

## What gets saved

Claude writes markdown articles organized by category. You never touch the structure. Claude picks the category, names the file, writes the content, and maintains the index.

```
~/claude-wiki/
  wiki.py              # search engine (~300 lines, Python stdlib only)
  wiki.db              # search index (auto-created, disposable, rebuildable)
  INDEX.md             # table of contents Claude maintains
  wiki/
    contracts/
      indemnity-cap-carveouts.md
      termination-for-convenience.md
    litigation/
      discovery-scope-preservation.md
      fmla-retaliation-risk.md
    compliance/
      multi-state-breach-notification.md
    infrastructure/
      gemini-flex-tier.md
```

These are real articles with tables, exact numbers, specific commands, and the reasoning behind decisions. Not chat logs. Not raw dumps. Written so that a future Claude session, or you, can read them and act immediately.

## Use cases

### Legal work

- Diligence findings that carry across deals: indemnity structures, IP ownership gaps, regulatory exposure patterns
- Clause review history: what the counterparty pushed back on, what the partner approved, what language worked
- Jurisdictional research that applies to future matters in the same state
- Settlement positions across rounds with exact dollar figures, deadlines, and carrier status

### Technical work

- Model evaluation results with exact scores, not just "it did well"
- Training strategy decisions: why this approach, what the mix ratio should be, what to avoid
- Infrastructure gotchas: which API version supports which feature, rate limit workarounds, deployment quirks
- Architecture decisions: why you chose this pattern, what you considered, what failed

### Any multi-project workflow

You learn something in Project A. Months later in Project B, you need it. Without a cross-project wiki, it is gone. With `/remember`, Claude finds it.

## Inspired by Karpathy's LLM Wiki

Karpathy's [llm-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) describes building persistent knowledge bases with LLMs: ingest sources into a `raw/` directory, have the LLM compile them into a structured markdown wiki, then query and refine over time. The LLM does the tedious bookkeeping. The human directs and reads. Knowledge compounds.

We borrowed that core idea. But our entry point is different.

| | Karpathy's LLM Wiki | claude-wiki |
|---|---|---|
| Source material | External docs (papers, articles, repos) | Your conversation with Claude |
| Ingest step | Copy files to `raw/`, LLM compiles | `/remember` distills in real-time |
| Wiki compilation | LLM reads raw, writes summaries | Claude writes directly from context |
| Search | qmd (BM25 + vector + re-ranking) | SQLite FTS5 (BM25 + Porter stemming) |
| Frontend | Obsidian | Any editor, or just let Claude read it |
| Best for | Research knowledge (papers, datasets) | Working knowledge (decisions, findings, gotchas) |

Karpathy's system is a research librarian. This system is a working notebook.

If you want both, they compose. Use his approach for ingesting papers and articles. Use this for capturing what you learn while working. They write to different directories and do not conflict.

## Technical details

- **wiki.py** is one Python file. Zero dependencies beyond the standard library. SQLite FTS5 handles full-text search with Porter stemming (so "finetuning" matches "fine-tuned") and BM25 relevance ranking.
- **SKILL.md** is a Claude Code skill file. Drop it in `~/.claude/skills/remember/` and it shows up in every session. The description tells Claude the wiki exists and how to search it, so recall is automatic.
- The database is a disposable cache. Delete `wiki.db` and run `wiki.py index-all` to rebuild from the markdown files. The articles are the source of truth, not the database.
- Articles are plain markdown. Read them in any editor, grep them, point Obsidian at them, or just let Claude handle everything.

## Commands

| Command | What it does |
|---|---|
| `wiki.py init` | Create the database |
| `wiki.py index <file>` | Index one markdown file |
| `wiki.py index-all` | Re-index all files in wiki/ |
| `wiki.py search <query>` | Search (human-readable output) |
| `wiki.py search <query> --json` | Search (JSON output for Claude) |
| `wiki.py stats` | Show article count by category |

## License

MIT. Use it however you want.
