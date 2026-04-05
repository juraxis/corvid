#!/usr/bin/env python3
"""
wiki.py — Personal knowledge wiki with FTS5 search.

Commands:
    python wiki.py init                  Create database
    python wiki.py index <file>          Index one file
    python wiki.py index-all             Re-index entire wiki/ directory
    python wiki.py search <query>        Search (human-readable)
    python wiki.py search <query> --json Search (machine-readable)
    python wiki.py stats                 Show article counts
"""

import sqlite3
import sys
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────
WIKI_DIR = os.environ.get("CLAUDE_WIKI", os.path.expanduser("~/claude-wiki"))
DB_PATH = os.path.join(WIKI_DIR, "wiki.db")
ARTICLES_DIR = os.path.join(WIKI_DIR, "wiki")


def get_db():
    """Get database connection, auto-init if needed."""
    os.makedirs(WIKI_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Auto-create schema if missing
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"
    ).fetchone()
    if not tables:
        _init_schema(conn)
    return conn


def _init_schema(conn):
    """Create tables and FTS5 index."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT UNIQUE,
            filehash TEXT,
            title TEXT,
            category TEXT DEFAULT 'general',
            content TEXT,
            source_project TEXT,
            indexed_at TEXT,
            updated_at TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            title,
            category,
            content,
            content=articles,
            content_rowid=id,
            tokenize='porter unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
            INSERT INTO articles_fts(rowid, title, category, content)
            VALUES (new.id, new.title, new.category, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, title, category, content)
            VALUES ('delete', old.id, old.title, old.category, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, title, category, content)
            VALUES ('delete', old.id, old.title, old.category, old.content);
            INSERT INTO articles_fts(rowid, title, category, content)
            VALUES (new.id, new.title, new.category, new.content);
        END;
    """)


# ── Index ──────────────────────────────────────────────────────
def cmd_index(filepath, category=None):
    """Index or re-index a single file. Upserts by filepath."""
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if not content.strip():
        print(f"SKIP: Empty file: {filepath}")
        return False

    filehash = hashlib.sha256(content.encode()).hexdigest()

    # Extract title from first heading
    title = os.path.basename(filepath)
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Detect category from path: wiki/<category>/file.md
    if category is None:
        rel = os.path.relpath(filepath, ARTICLES_DIR)
        parts = Path(rel).parts
        category = parts[0] if len(parts) > 1 else "general"

    # Detect source project from cwd
    source_project = os.path.basename(os.getcwd())

    now = datetime.now().isoformat()

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id, filehash FROM articles WHERE filepath = ?", (filepath,)
        ).fetchone()

        if existing:
            if existing["filehash"] == filehash:
                print(f"UNCHANGED: {title}")
                return False
            conn.execute(
                """UPDATE articles
                   SET filehash=?, title=?, category=?, content=?,
                       source_project=?, updated_at=?
                   WHERE filepath=?""",
                (filehash, title, category, content, source_project, now, filepath),
            )
            conn.commit()
            print(f"UPDATED: {title} [{category}]")
            return True
        else:
            conn.execute(
                """INSERT INTO articles
                   (filepath, filehash, title, category, content, source_project, indexed_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (filepath, filehash, title, category, content, source_project, now, now),
            )
            conn.commit()
            print(f"INDEXED: {title} [{category}]")
            return True
    except sqlite3.Error as e:
        print(f"ERROR: {e}")
        return False
    finally:
        conn.close()


# ── Search ─────────────────────────────────────────────────────
def cmd_search(query, limit=10, as_json=False):
    """Full-text search with BM25 ranking."""
    conn = get_db()
    try:
        results = conn.execute(
            """
            SELECT
                a.id, a.title, a.category, a.filepath, a.source_project,
                a.indexed_at, a.updated_at,
                snippet(articles_fts, 2, '>>>', '<<<', '...', 40) AS snippet,
                rank
            FROM articles_fts
            JOIN articles a ON a.id = articles_fts.rowid
            WHERE articles_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError as e:
        if as_json:
            print(json.dumps({"error": str(e), "results": []}))
        else:
            print(f"Search error: {e}")
            print("Tip: wrap phrases in quotes, avoid special characters like ( ) *")
        return []
    finally:
        conn.close()

    if as_json:
        out = []
        for r in results:
            out.append({
                "id": r["id"],
                "title": r["title"],
                "category": r["category"],
                "filepath": r["filepath"],
                "source_project": r["source_project"],
                "snippet": r["snippet"],
                "updated_at": r["updated_at"],
            })
        print(json.dumps({"query": query, "count": len(out), "results": out}, indent=2))
        return results

    if not results:
        print(f"No results for: {query}")
        return []

    print(f"\n{'─' * 60}")
    print(f" Results for: {query}")
    print(f"{'─' * 60}\n")
    for r in results:
        date = (r["updated_at"] or r["indexed_at"] or "")[:10]
        print(f"  [{r['category']}] {r['title']}")
        print(f"  Date: {date}  |  Project: {r['source_project'] or 'n/a'}")
        print(f"  {r['snippet']}\n")
    print(f"{'─' * 60}")
    print(f" {len(results)} result(s)")
    return results


# ── Index All ──────────────────────────────────────────────────
def cmd_index_all():
    """Re-index every .md file in the wiki directory."""
    if not os.path.exists(ARTICLES_DIR):
        print(f"No wiki directory at {ARTICLES_DIR}")
        return

    count = 0
    for root, _, files in os.walk(ARTICLES_DIR):
        for fname in sorted(files):
            if fname.endswith(".md"):
                fpath = os.path.join(root, fname)
                if cmd_index(fpath):
                    count += 1

    print(f"\nRe-indexed {count} article(s)")


# ── Stats ──────────────────────────────────────────────────────
def cmd_stats():
    """Show article counts by category."""
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        cats = conn.execute(
            "SELECT category, COUNT(*) as c FROM articles GROUP BY category ORDER BY c DESC"
        ).fetchall()
    finally:
        conn.close()

    print(f"\n  Wiki: {WIKI_DIR}")
    print(f"  Database: {DB_PATH}")
    print(f"  Total articles: {total}\n")
    for row in cats:
        print(f"    {row['category']:>16}: {row['c']}")
    print()


# ── CLI ────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "init":
        conn = get_db()
        conn.close()
        print(f"Wiki ready at {WIKI_DIR}")

    elif cmd == "index":
        if len(sys.argv) < 3:
            print("Usage: wiki.py index <file> [category]")
            return
        filepath = sys.argv[2]
        category = sys.argv[3] if len(sys.argv) > 3 else None
        cmd_index(filepath, category)

    elif cmd == "index-all":
        cmd_index_all()

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: wiki.py search <query> [--json]")
            return
        as_json = "--json" in sys.argv
        args = [a for a in sys.argv[2:] if a != "--json"]
        query = " ".join(args)
        cmd_search(query, as_json=as_json)

    elif cmd == "stats":
        cmd_stats()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
