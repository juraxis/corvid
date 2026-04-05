---
name: remember
description: Use when the user says /remember, wants to save an insight, or says "save this", "remember this". Also use PROACTIVELY at the start of complex tasks -- search the cross-project wiki at ~/claude-wiki/ via `python3 ~/claude-wiki/wiki.py search "<topic>" --json` to check for relevant past knowledge before starting work.
allowed-tools: Bash(python3:*), Bash(python:*), Bash(cat:*), Bash(mkdir:*), Read, Write, Glob, Grep
---

# /remember -- Save Knowledge to Wiki

You maintain a personal knowledge wiki at `~/claude-wiki/wiki/`. When the user says `/remember`, distill the current insight and save it.

## How It Works

```
/remember              -> You distill the key insight from conversation context
/remember "exact text" -> Save the user's exact words as the core content
```

## Steps

1. **Distill**: Extract the key insight, decision, finding, or lesson from the conversation. Write it as a concise, useful article, not a raw dump. Think: "what would be useful to know 6 months from now?"

2. **Check INDEX.md**: Read `~/claude-wiki/INDEX.md` to see if a related article already exists.
   - If yes: read that article and UPDATE it with the new information
   - If no: create a new article

3. **Write the article**: Save to `~/claude-wiki/wiki/<category>/<slug>.md`
   - Pick a category from existing ones, or create a new one if nothing fits
   - Use a descriptive slug: `auth-token-rotation.md`, not `note-001.md`
   - Format: `# Title`, then clear, scannable content with headers/bullets/tables as needed
   - Include: what, why, and any specific values/commands/gotchas worth remembering

4. **Index it**: Run `python3 ~/claude-wiki/wiki.py index <filepath>`

5. **Update INDEX.md**: Add or update the one-line entry in `~/claude-wiki/INDEX.md`

## INDEX.md Format

```markdown
# Wiki Index

## <Category>
- [Article Title](wiki/<category>/<slug>.md) -- one-line summary
```

Keep entries under 120 characters. This file is the master table of contents.

## Article Style

- Write for your future self (or a future Claude session)
- Be specific: include exact commands, model names, versions, numbers
- Do not pad with filler. Every sentence should carry information
- Use tables for comparisons, bullets for lists, code blocks for commands
- If updating an existing article, preserve what is there and add the new info

## Categories

Organic, create as needed. Examples:
- `contracts/` -- clause drafting, redlining, review patterns
- `litigation/` -- discovery, motions, settlement strategy
- `compliance/` -- regulatory analysis, audit findings
- `infrastructure/` -- pods, servers, deployment
- `debugging/` -- hard-won fixes and gotchas

## What NOT to save

- Ephemeral task state (use Claude's built-in memory for that)
- Raw session transcripts
- Code snippets without context
- Anything already in the project's CLAUDE.md
