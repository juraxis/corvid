#!/usr/bin/env python3
"""
corvid -- Permanent memory layer for AI coding agents.

Commands:
    corvid init                  Create database and wiki directory
    corvid index <file>          Index one file
    corvid index-all             Re-index entire wiki/ directory
    corvid search <query>        Search (human-readable)
    corvid search <query> --json Search (machine-readable)
    corvid stats                 Show article counts

Search modes:
    Default: hybrid (keyword + semantic). Falls back to keyword-only if
    fastembed/sqlite-vec are not installed. No config needed.
"""

import sqlite3
import sys
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path

# ── Optional: semantic search dependencies ────────────────────
_SEMANTIC_AVAILABLE = False
_embedding_model = None

try:
    import sqlite_vec

    _VEC_AVAILABLE = True
except ImportError:
    _VEC_AVAILABLE = False

try:
    from fastembed import TextEmbedding

    _FASTEMBED_AVAILABLE = True
except ImportError:
    _FASTEMBED_AVAILABLE = False

_SEMANTIC_AVAILABLE = _VEC_AVAILABLE and _FASTEMBED_AVAILABLE
EMBED_DIM = 384  # bge-small-en-v1.5
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# ── Configuration ──────────────────────────────────────────────
WIKI_DIR = os.environ.get("CORVID_HOME", os.path.expanduser("~/corvid"))
DB_PATH = os.path.join(WIKI_DIR, "corvid.db")
ARTICLES_DIR = os.path.join(WIKI_DIR, "wiki")


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None and _FASTEMBED_AVAILABLE:
        _embedding_model = TextEmbedding(EMBED_MODEL)
    return _embedding_model


def _embed(text):
    """Embed a single text string. Returns list of floats."""
    model = _get_embedding_model()
    if model is None:
        return None
    results = list(model.embed([text[:8000]]))
    return results[0].tolist()


def get_db():
    """Get database connection, auto-init if needed."""
    os.makedirs(WIKI_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if _VEC_AVAILABLE:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"
    ).fetchone()
    if not tables:
        _init_schema(conn)
    # Auto-add vec table if semantic became available after initial init
    if _SEMANTIC_AVAILABLE:
        vec_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='articles_vec'"
        ).fetchone()
        if not vec_exists:
            conn.execute(
                f"CREATE VIRTUAL TABLE articles_vec USING vec0(embedding float[{EMBED_DIM}])"
            )
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
    if _SEMANTIC_AVAILABLE:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS articles_vec USING vec0(embedding float[{EMBED_DIM}])"
        )


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

    title = os.path.basename(filepath)
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    if category is None:
        rel = os.path.relpath(filepath, ARTICLES_DIR)
        parts = Path(rel).parts
        category = parts[0] if len(parts) > 1 else "general"

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
            article_id = existing["id"]
            # Update embedding
            if _SEMANTIC_AVAILABLE:
                vec = _embed(f"{title}\n{content}")
                if vec:
                    conn.execute("DELETE FROM articles_vec WHERE rowid = ?", (article_id,))
                    conn.execute(
                        "INSERT INTO articles_vec(rowid, embedding) VALUES (?, ?)",
                        (article_id, json.dumps(vec)),
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
            article_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            # Store embedding
            if _SEMANTIC_AVAILABLE:
                vec = _embed(f"{title}\n{content}")
                if vec:
                    conn.execute(
                        "INSERT INTO articles_vec(rowid, embedding) VALUES (?, ?)",
                        (article_id, json.dumps(vec)),
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
def _keyword_search(conn, query, limit):
    """FTS5 keyword search with BM25 ranking."""
    try:
        return conn.execute(
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
    except sqlite3.OperationalError:
        return []


def _semantic_search(conn, query, limit):
    """Vector similarity search using fastembed + sqlite-vec."""
    if not _SEMANTIC_AVAILABLE:
        return []
    vec = _embed(query)
    if not vec:
        return []
    rows = conn.execute(
        """
        SELECT
            v.rowid AS id, v.distance,
            a.title, a.category, a.filepath, a.source_project,
            a.indexed_at, a.updated_at, a.content
        FROM articles_vec v
        JOIN articles a ON a.id = v.rowid
        WHERE embedding MATCH ?
            AND k = ?
        """,
        (json.dumps(vec), limit),
    ).fetchall()
    return rows


def cmd_search(query, limit=10, as_json=False):
    """Hybrid search: keyword + semantic, deduplicated and merged."""
    conn = get_db()
    try:
        kw_results = _keyword_search(conn, query, limit)
        sem_results = _semantic_search(conn, query, limit) if _SEMANTIC_AVAILABLE else []
    finally:
        conn.close()

    # Merge: keyword results first (ranked by BM25), then semantic results not already in keyword set
    seen_ids = set()
    merged = []

    for r in kw_results:
        rid = r["id"]
        if rid not in seen_ids:
            seen_ids.add(rid)
            merged.append({
                "id": rid,
                "title": r["title"],
                "category": r["category"],
                "filepath": r["filepath"],
                "source_project": r["source_project"],
                "snippet": r["snippet"],
                "updated_at": r["updated_at"] or r["indexed_at"] or "",
                "match": "keyword",
            })

    for r in sem_results:
        rid = r["id"]
        if rid not in seen_ids:
            seen_ids.add(rid)
            content = r["content"] or ""
            # Build a snippet from first 200 chars
            snippet = content[:200].replace("\n", " ").strip()
            if len(content) > 200:
                snippet += "..."
            merged.append({
                "id": rid,
                "title": r["title"],
                "category": r["category"],
                "filepath": r["filepath"],
                "source_project": r["source_project"],
                "snippet": snippet,
                "updated_at": r["updated_at"] or r["indexed_at"] or "",
                "match": "semantic",
            })

    merged = merged[:limit]

    if as_json:
        print(json.dumps({
            "query": query,
            "count": len(merged),
            "semantic_available": _SEMANTIC_AVAILABLE,
            "results": merged,
        }, indent=2))
        return merged

    if not merged:
        print(f"No results for: {query}")
        return []

    mode = "hybrid (keyword + semantic)" if _SEMANTIC_AVAILABLE else "keyword only"
    print(f"\n{'─' * 60}")
    print(f" Results for: {query}  [{mode}]")
    print(f"{'─' * 60}\n")
    for r in merged:
        date = r["updated_at"][:10] if r["updated_at"] else "unknown"
        match_tag = f" ({r['match']})" if _SEMANTIC_AVAILABLE else ""
        print(f"  [{r['category']}] {r['title']}{match_tag}")
        print(f"  Date: {date}  |  Project: {r['source_project'] or 'n/a'}")
        print(f"  {r['snippet']}\n")
    print(f"{'─' * 60}")
    print(f" {len(merged)} result(s)")
    return merged


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
    if _SEMANTIC_AVAILABLE:
        print(f"Semantic embeddings: enabled ({EMBED_MODEL})")
    else:
        print("Semantic embeddings: disabled (install fastembed and sqlite-vec to enable)")


# ── Stats ──────────────────────────────────────────────────────
def cmd_stats():
    """Show article counts by category."""
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        cats = conn.execute(
            "SELECT category, COUNT(*) as c FROM articles GROUP BY category ORDER BY c DESC"
        ).fetchall()
        vec_count = 0
        if _SEMANTIC_AVAILABLE:
            vec_count = conn.execute("SELECT COUNT(*) FROM articles_vec").fetchone()[0]
    finally:
        conn.close()

    print(f"\n  Wiki: {WIKI_DIR}")
    print(f"  Database: {DB_PATH}")
    print(f"  Total articles: {total}")
    if _SEMANTIC_AVAILABLE:
        print(f"  Embeddings: {vec_count}/{total} ({EMBED_MODEL})")
    else:
        print(f"  Embeddings: disabled (pip install fastembed sqlite-vec)")
    print()
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
        if _SEMANTIC_AVAILABLE:
            print(f"Semantic search: enabled ({EMBED_MODEL})")
        else:
            print("Semantic search: disabled (pip install fastembed sqlite-vec)")

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
