# claude-wiki

A cross-project knowledge base for Claude Code. One slash command, one Python script, zero dependencies.

You say `/remember` and Claude distills what you just learned into a searchable wiki. Next session, next project, next month, it is still there.

## Why not just use Claude's built-in memory?

Claude Code has a built-in memory system at `~/.claude/projects/*/memory/`. It works, but it has limits that matter if you work across multiple projects:

| | Built-in memory | claude-wiki |
|---|---|---|
| Scope | Per-project | Cross-project, one wiki for everything |
| Limit | Truncates at 200 lines | Unlimited articles |
| Search | None, just loads files in order | Full-text search with ranking (SQLite FTS5) |
| Trigger | Claude decides automatically | You decide with `/remember` |
| Access | Only in that project's sessions | Searchable from any project |

If you only work in one project, the built-in memory is fine. If you work across five or ten projects and want knowledge to carry over between them, that is what this solves.

## How it works

```
You: "We figured out that Gemini Flex tier needs google-genai v1.70+"
You: /remember

Claude distills the insight
  -> writes ~/claude-wiki/wiki/infrastructure/gemini-flex-tier.md
  -> indexes it in SQLite FTS5
  -> updates INDEX.md

Next session, different project:
You: "Set up Gemini batch processing"

Claude sees /remember skill in skill list
  -> searches: python3 ~/claude-wiki/wiki.py search "gemini batch" --json
  -> finds the flex tier article
  -> uses it
```

## Setup (2 minutes)

### 1. Copy the files

```bash
mkdir -p ~/claude-wiki/wiki
cp wiki.py ~/claude-wiki/wiki.py
cp SKILL.md ~/.claude/skills/remember/SKILL.md
```

Make the skill directory if it does not exist:

```bash
mkdir -p ~/.claude/skills/remember
```

### 2. Initialize

```bash
python3 ~/claude-wiki/wiki.py init
```

That creates the SQLite database. Done.

### 3. Test it

Open Claude Code in any project and type `/remember`. Claude will ask what to save, or distill something from the current conversation.

To search manually:

```bash
python3 ~/claude-wiki/wiki.py search "whatever topic"
python3 ~/claude-wiki/wiki.py search "contract liability" --json
python3 ~/claude-wiki/wiki.py stats
```

## What gets saved

Claude writes markdown articles organized by category:

```
~/claude-wiki/
  wiki.py              # search engine (SQLite FTS5, ~300 lines)
  wiki.db              # search index (auto-created, rebuildable)
  INDEX.md             # table of contents, one line per article
  wiki/
    contracts/
      indemnity-cap-carveouts.md
      termination-for-convenience.md
    litigation/
      discovery-scope-preservation.md
      fmla-retaliation-risk.md
    compliance/
      multi-state-breach-notification.md
```

The articles are real knowledge, not raw dumps. They have tables, specific numbers, exact commands, and the reasoning behind decisions. Written so that a future Claude session (or you) can read them and immediately act on them.

## Use cases

### Lawyers working with Claude Code

You are reviewing a complex M&A deal across multiple sessions. Each session you learn something:

- The indemnity cap has a carve-out for IP that re-expands liability
- The change-of-control clause in the key customer contract threatens 38% of ARR
- The AGPL component in the target's codebase could force source disclosure

Say `/remember` after each finding. Next session, Claude searches the wiki before starting work and already knows the deal context. You do not re-explain. You do not re-discover.

More examples:

- Regulatory compliance gaps found during an audit, with exact deadlines and remediation priorities
- Clause review patterns: what worked, what the counterparty pushed back on, what the partner approved
- Jurisdictional quirks discovered during research that apply to future matters in the same state
- Settlement negotiation positions across multiple rounds, with exact dollar figures preserved

### Developers building legal tech

You are fine-tuning a model across evaluation runs, dataset iterations, and infrastructure changes:

- Model evaluation results with exact scores, not just "it did well"
- Training decisions: why SFT over DPO, what the anchor mix ratio should be, what not to do
- Infrastructure gotchas: which API version supports which feature, rate limit workarounds
- Pipeline decisions: Flash vs Pro cost/quality tradeoffs, batch vs flex tier

### Anyone working across multiple Claude Code projects

The pattern is the same regardless of domain. You learn something in Project A. Three months later in Project B, you need it. Without a cross-project wiki, it is gone. With `/remember`, Claude finds it.

## How it differs from Karpathy's LLM Wiki

Karpathy's approach (documented in his llm-wiki.md gist) ingests external sources (papers, articles, repos) into a `raw/` directory and compiles them into a wiki. The LLM is a librarian for external knowledge.

This system is different. The "source" is your conversation with Claude, not external documents. Claude distills insights as they happen. There is no `raw/` directory, no ingest pipeline, no compilation step.

Same philosophy: the LLM maintains the wiki, the human directs and reads. Different entry point: conversation-first instead of document-first.

If you want both, they compose. Use Karpathy's approach for research (papers, articles) and claude-wiki for working knowledge (decisions, findings, gotchas).

## Technical details

- **wiki.py** is a single Python file with zero dependencies beyond the standard library. It uses SQLite FTS5 for full-text search with Porter stemming and BM25 ranking.
- **SKILL.md** is a Claude Code skill file. When installed at `~/.claude/skills/remember/`, it appears in every Claude Code session's skill list. The description tells Claude the wiki exists and how to search it.
- The database is a disposable cache. Delete `wiki.db` and run `python3 ~/claude-wiki/wiki.py index-all` to rebuild it from the markdown files.
- Articles are plain markdown. You can read them in any editor, grep them, or point Obsidian at `~/claude-wiki/wiki/`.

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
