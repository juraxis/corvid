#!/usr/bin/env python3
"""
corvid -- Permanent memory layer for AI coding agents.

Commands:
    corvid install               Detect agents, install skill, init database
    corvid init                  Create database and wiki directory
    corvid index <file>          Index one file
    corvid index-all             Re-index entire wiki/ directory
    corvid search <query>        Search (human-readable)
    corvid search <query> --json Search (machine-readable)
    corvid search <q> --tags x,y Filter by tags before searching
    corvid facts [subject]       Show extracted facts (temporal)
    corvid stats                 Show article counts

Search modes:
    Hybrid: keyword (FTS5/BM25) + semantic (fastembed/sqlite-vec),
    merged via Reciprocal Rank Fusion. Falls back to keyword-only
    if fastembed/sqlite-vec are not installed. No config needed.
"""

import sqlite3
import sys
import os
import json
import hashlib
import re
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
    # Auto-migrate: add tags column if missing
    cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
    if "tags" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN tags TEXT DEFAULT '[]'")
    # Auto-migrate: add facts table if missing
    facts_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='facts'"
    ).fetchone()
    if not facts_exists:
        conn.executescript("""
            CREATE TABLE facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT NOT NULL,
                confidence REAL DEFAULT 0.6,
                article_id INTEGER REFERENCES articles(id),
                valid_from TEXT NOT NULL, valid_to TEXT,
                extracted_at TEXT NOT NULL
            );
            CREATE INDEX idx_facts_subj ON facts(subject);
            CREATE INDEX idx_facts_pred ON facts(subject, predicate);
        """)
    else:
        # Auto-migrate: add confidence column if missing
        fact_cols = {r[1] for r in conn.execute("PRAGMA table_info(facts)").fetchall()}
        if "confidence" not in fact_cols:
            conn.execute("ALTER TABLE facts ADD COLUMN confidence REAL DEFAULT 0.6")
    # Auto-migrate: add search_hits table for memory feedback loop
    hits_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='search_hits'"
    ).fetchone()
    if not hits_exists:
        conn.executescript("""
            CREATE TABLE search_hits (
                article_id INTEGER REFERENCES articles(id),
                query TEXT NOT NULL,
                hit_at TEXT NOT NULL
            );
            CREATE INDEX idx_hits_article ON search_hits(article_id);
        """)
    # Auto-migrate: add links table for article relations
    links_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='links'"
    ).fetchone()
    if not links_exists:
        conn.execute("""
            CREATE TABLE links (
                source_id INTEGER REFERENCES articles(id),
                target_id INTEGER REFERENCES articles(id),
                relation TEXT DEFAULT 'references',
                PRIMARY KEY (source_id, target_id)
            )
        """)
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
            tags TEXT DEFAULT '[]',
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
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            confidence REAL DEFAULT 0.6,
            article_id INTEGER REFERENCES articles(id),
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            extracted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_facts_subj ON facts(subject);
        CREATE INDEX IF NOT EXISTS idx_facts_pred ON facts(subject, predicate);

        CREATE TABLE IF NOT EXISTS search_hits (
            article_id INTEGER REFERENCES articles(id),
            query TEXT NOT NULL,
            hit_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hits_article ON search_hits(article_id);

        CREATE TABLE IF NOT EXISTS links (
            source_id INTEGER REFERENCES articles(id),
            target_id INTEGER REFERENCES articles(id),
            relation TEXT DEFAULT 'references',
            PRIMARY KEY (source_id, target_id)
        );
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
    tags = []
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
        tag_match = re.match(r'^tags:\s*(.+)', line, re.IGNORECASE)
        if tag_match:
            tags = [t.strip().lower() for t in tag_match.group(1).split(",") if t.strip()]
        if title != os.path.basename(filepath) and tags:
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
            tags_json = json.dumps(tags)
            conn.execute(
                """UPDATE articles
                   SET filehash=?, title=?, category=?, tags=?, content=?,
                       source_project=?, updated_at=?
                   WHERE filepath=?""",
                (filehash, title, category, tags_json, content, source_project, now, filepath),
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
            _upsert_facts(conn, article_id, _extract_facts(content), now)
            _extract_links(conn, article_id, content, filepath)
            print(f"UPDATED: {title} [{category}]")
            return True
        else:
            tags_json = json.dumps(tags)
            conn.execute(
                """INSERT INTO articles
                   (filepath, filehash, title, category, tags, content, source_project, indexed_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (filepath, filehash, title, category, tags_json, content, source_project, now, now),
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
            _upsert_facts(conn, article_id, _extract_facts(content), now)
            _extract_links(conn, article_id, content, filepath)
            print(f"INDEXED: {title} [{category}]")
            return True
    except sqlite3.Error as e:
        print(f"ERROR: {e}")
        return False
    finally:
        conn.close()


# ── Facts ─────────────────────────────────────────────────────
_FACT_PATTERNS = [
    # "X uses Y", "X runs Y", "X requires Y"
    re.compile(r'^[-*]?\s*(?:the\s+)?(.+?)\s+(?:uses?|runs?|requires?|needs?)\s+(.+?)\.?\s*$', re.IGNORECASE),
    # "X is Y", "X was Y"
    re.compile(r'^[-*]?\s*(?:the\s+)?(.+?)\s+(?:is|was|are)\s+(.+?)\.?\s*$', re.IGNORECASE),
    # "X: Y" (key-value style in bullet points)
    re.compile(r'^[-*]\s*([^:]{3,40}):\s+(.+?)\.?\s*$'),
    # "X version Y" / "X v1.2.3"
    re.compile(r'^[-*]?\s*(?:the\s+)?(.+?)\s+(?:version|v)\s*([\d][\d.]+\S*)\.?\s*$', re.IGNORECASE),
    # "deploy to X", "hosted on X"
    re.compile(r'^[-*]?\s*(?:deploy(?:ed)?\s+to|hosted\s+on|running\s+on)\s+(.+?)\.?\s*$', re.IGNORECASE),
]


def _extract_facts(content):
    """Extract structured facts from article content. Returns list of (subject, predicate, object)."""
    facts = []
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        for pattern in _FACT_PATTERNS:
            m = pattern.match(line)
            if m:
                groups = m.groups()
                if len(groups) == 2:
                    subj, obj = groups
                    # Infer predicate from the matched verb
                    pred = "relates_to"
                    for verb in ["uses", "use", "runs", "run", "requires", "require", "needs", "need"]:
                        if verb in line.lower():
                            pred = "uses"
                            break
                    for verb in ["is", "was", "are"]:
                        if f" {verb} " in line.lower():
                            pred = "is"
                            break
                    if ":" in line and pattern == _FACT_PATTERNS[2]:
                        pred = "has"
                    if "version" in line.lower() or re.search(r'v\d', line):
                        pred = "version"
                    facts.append((subj.strip(), pred, obj.strip()))
                break
    return facts


def _upsert_facts(conn, article_id, facts, now, confidence=0.6):
    """Insert facts, invalidating contradictions (same subject+predicate, different object)."""
    for subj, pred, obj in facts:
        existing = conn.execute(
            """SELECT id, object FROM facts
               WHERE subject = ? AND predicate = ? AND valid_to IS NULL""",
            (subj, pred),
        ).fetchone()
        if existing:
            if existing["object"] == obj:
                continue
            conn.execute(
                "UPDATE facts SET valid_to = ? WHERE id = ?",
                (now, existing["id"]),
            )
        conn.execute(
            """INSERT INTO facts (subject, predicate, object, confidence, article_id, valid_from, valid_to, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?)""",
            (subj, pred, obj, confidence, article_id, now, now),
        )
    conn.commit()


def cmd_facts(subject=None):
    """Show facts, optionally filtered by subject."""
    conn = get_db()
    try:
        if subject:
            rows = conn.execute(
                """SELECT subject, predicate, object, confidence, valid_from, valid_to, article_id
                   FROM facts WHERE subject LIKE ? ORDER BY valid_from DESC""",
                (f"%{subject}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT subject, predicate, object, confidence, valid_from, valid_to, article_id
                   FROM facts WHERE valid_to IS NULL ORDER BY extracted_at DESC LIMIT 50"""
            ).fetchall()
    finally:
        conn.close()

    if not rows:
        print(f"No facts found{f' for: {subject}' if subject else ''}")
        return

    print(f"\n{'─' * 60}")
    print(f" Facts{f' matching: {subject}' if subject else ' (active)'}")
    print(f"{'─' * 60}\n")
    for r in rows:
        status = "" if r["valid_to"] is None else f" [superseded {r['valid_to'][:10]}]"
        conf = r["confidence"] or 0.6
        conf_label = "high" if conf >= 0.9 else "med" if conf >= 0.7 else "low"
        print(f"  {r['subject']} → {r['predicate']} → {r['object']} ({conf_label}){status}")
    print(f"\n{'─' * 60}")
    print(f" {len(rows)} fact(s)")


# ── Links ─────────────────────────────────────────────────────
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+\.md)\)')


def _extract_links(conn, article_id, content, source_filepath=None):
    """Extract markdown links to other wiki articles and create edges."""
    conn.execute("DELETE FROM links WHERE source_id = ?", (article_id,))
    source_dir = os.path.dirname(source_filepath) if source_filepath else ARTICLES_DIR
    for _, href in _MD_LINK_RE.findall(content):
        # Try resolving relative to source article's directory first, then wiki root
        for base in [source_dir, ARTICLES_DIR]:
            target_path = os.path.normpath(os.path.join(base, href))
            target = conn.execute(
                "SELECT id FROM articles WHERE filepath = ?", (target_path,)
            ).fetchone()
            if target and target["id"] != article_id:
                conn.execute(
                    "INSERT OR IGNORE INTO links (source_id, target_id, relation) VALUES (?, ?, 'references')",
                    (article_id, target["id"]),
                )
                break
    conn.commit()


# ── Search ─────────────────────────────────────────────────────
def _keyword_search(conn, query, limit, tags=None):
    """FTS5 keyword search with BM25 ranking, optional tag pre-filter."""
    try:
        if tags:
            tag_clauses = " AND ".join(
                f"a.tags LIKE '%\"{t}\"%'" for t in tags
            )
            return conn.execute(
                f"""
                SELECT
                    a.id, a.title, a.category, a.tags, a.filepath, a.source_project,
                    a.indexed_at, a.updated_at,
                    snippet(articles_fts, 2, '>>>', '<<<', '...', 64) AS snippet,
                    rank
                FROM articles_fts
                JOIN articles a ON a.id = articles_fts.rowid
                WHERE articles_fts MATCH ? AND {tag_clauses}
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return conn.execute(
            """
            SELECT
                a.id, a.title, a.category, a.tags, a.filepath, a.source_project,
                a.indexed_at, a.updated_at,
                snippet(articles_fts, 2, '>>>', '<<<', '...', 64) AS snippet,
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


def _semantic_search(conn, query, limit, tags=None):
    """Vector similarity search using fastembed + sqlite-vec, optional tag pre-filter."""
    if not _SEMANTIC_AVAILABLE:
        return []
    vec = _embed(query)
    if not vec:
        return []
    # Fetch more candidates if filtering by tags (pre-filter narrows post-query)
    fetch_k = limit * 3 if tags else limit
    rows = conn.execute(
        """
        SELECT
            v.rowid AS id, v.distance,
            a.title, a.category, a.tags, a.filepath, a.source_project,
            a.indexed_at, a.updated_at, a.content
        FROM articles_vec v
        JOIN articles a ON a.id = v.rowid
        WHERE embedding MATCH ?
            AND k = ?
        """,
        (json.dumps(vec), fetch_k),
    ).fetchall()
    if tags:
        filtered = []
        for r in rows:
            article_tags = json.loads(r["tags"] or "[]")
            if any(t in article_tags for t in tags):
                filtered.append(r)
            if len(filtered) >= limit:
                break
        return filtered
    return rows


def _best_paragraph(content, query, max_len=300):
    """Extract the most relevant paragraph from content for a query.
    Scores paragraphs by word overlap with query terms."""
    if not content:
        return ""
    query_words = set(query.lower().split())
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content) if p.strip()]
    if not paragraphs:
        return content[:max_len].replace("\n", " ").strip()
    best, best_score = paragraphs[0], -1
    for p in paragraphs:
        words = set(p.lower().split())
        score = len(query_words & words)
        if score > best_score:
            best, best_score = p, score
    snippet = best[:max_len].replace("\n", " ").strip()
    if len(best) > max_len:
        snippet += "..."
    return snippet


RRF_K = 60  # Standard RRF constant


def cmd_search(query, limit=10, as_json=False, tags=None):
    """Hybrid search: keyword + semantic with Reciprocal Rank Fusion."""
    conn = get_db()
    try:
        kw_results = _keyword_search(conn, query, limit, tags=tags)
        sem_results = _semantic_search(conn, query, limit, tags=tags) if _SEMANTIC_AVAILABLE else []
        # Memory feedback: load hit counts for boost
        hit_counts = {}
        try:
            for row in conn.execute(
                "SELECT article_id, COUNT(*) as c FROM search_hits GROUP BY article_id"
            ).fetchall():
                hit_counts[row["article_id"]] = row["c"]
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()

    # Reciprocal Rank Fusion: score = sum of 1/(k+rank) across methods
    scores = {}   # id -> rrf_score
    entries = {}   # id -> result dict

    for rank, r in enumerate(kw_results):
        rid = r["id"]
        scores[rid] = scores.get(rid, 0) + 1.0 / (RRF_K + rank + 1)
        if rid not in entries:
            entries[rid] = {
                "id": rid,
                "title": r["title"],
                "category": r["category"],
                "tags": json.loads(r["tags"] or "[]"),
                "filepath": r["filepath"],
                "source_project": r["source_project"],
                "snippet": r["snippet"],
                "updated_at": r["updated_at"] or r["indexed_at"] or "",
                "match": "keyword",
            }

    for rank, r in enumerate(sem_results):
        rid = r["id"]
        scores[rid] = scores.get(rid, 0) + 1.0 / (RRF_K + rank + 1)
        if rid not in entries:
            entries[rid] = {
                "id": rid,
                "title": r["title"],
                "category": r["category"],
                "tags": json.loads(r["tags"] or "[]"),
                "filepath": r["filepath"],
                "source_project": r["source_project"],
                "snippet": _best_paragraph(r["content"], query),
                "updated_at": r["updated_at"] or r["indexed_at"] or "",
                "match": "semantic",
            }
        else:
            entries[rid]["match"] = "hybrid"

    # Apply memory feedback boost: +5% per previous hit, capped at +25%
    for rid in scores:
        hits = hit_counts.get(rid, 0)
        if hits > 0:
            boost = min(hits * 0.05, 0.25)
            scores[rid] *= (1.0 + boost)

    merged = sorted(entries.values(), key=lambda e: scores[e["id"]], reverse=True)[:limit]

    # Record search hits for feedback loop
    if merged:
        now = datetime.now().isoformat()
        conn = get_db()
        try:
            for r in merged:
                conn.execute(
                    "INSERT INTO search_hits (article_id, query, hit_at) VALUES (?, ?, ?)",
                    (r["id"], query, now),
                )
            conn.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    if as_json:
        # Enrich with related articles via links table
        if merged:
            conn = get_db()
            try:
                result_ids = {r["id"] for r in merged}
                for r in merged:
                    related = conn.execute(
                        """SELECT a.title, a.filepath FROM links l
                           JOIN articles a ON a.id = l.target_id
                           WHERE l.source_id = ?
                           UNION
                           SELECT a.title, a.filepath FROM links l
                           JOIN articles a ON a.id = l.source_id
                           WHERE l.target_id = ?""",
                        (r["id"], r["id"]),
                    ).fetchall()
                    r["related"] = [{"title": x["title"], "filepath": x["filepath"]} for x in related]
            finally:
                conn.close()
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
        tag_str = f"  Tags: {', '.join(r['tags'])}" if r["tags"] else ""
        print(f"  [{r['category']}] {r['title']}{match_tag}")
        print(f"  Date: {date}  |  Project: {r['source_project'] or 'n/a'}{tag_str}")
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


# ── Install ───────────────────────────────────────────────────
import shutil
import textwrap

# Agent skill directories (global/user-level)
AGENTS = {
    "Claude Code": os.path.expanduser("~/.claude/skills/remember"),
    "Codex CLI": os.path.expanduser("~/.codex/skills/remember"),
}

_SKILL_MD = textwrap.dedent("""\
    ---
    name: remember
    description: >-
      Use when the user says /remember, wants to save an insight, or says
      "save this", "remember this". Also use PROACTIVELY at the start of
      complex tasks -- search the cross-project wiki at ~/corvid/ via
      `corvid search "<topic>" --json` to check for relevant past knowledge
      before starting work.
    allowed-tools: Bash(corvid:*), Bash(python3:*), Bash(python:*), Bash(cat:*), Bash(mkdir:*), Read, Write, Glob, Grep
    ---

    # /remember -- Save Knowledge to Wiki

    You maintain a personal knowledge wiki at `~/corvid/wiki/`. When the user says `/remember`, distill the current insight and save it.

    ## How It Works

    ```
    /remember              -> You distill the key insight from conversation context
    /remember "exact text" -> Save the user's exact words as the core content
    ```

    ## Steps

    1. **Distill**: Extract the key insight, decision, finding, or lesson from the conversation. Write it as a concise, useful article, not a raw dump. Think: "what would be useful to know 6 months from now?"

    2. **Search first**: Run `corvid search "<topic>" --json` to check if a related article already exists.
       - Also check `~/corvid/INDEX.md` for the table of contents
       - If a related article exists: read it and UPDATE with the new information
       - If no match: create a new article

    3. **Write the article**: Save to `~/corvid/wiki/<category>/<slug>.md`
       - Pick a category from existing ones, or create a new one if nothing fits
       - Use a descriptive slug: `auth-token-rotation.md`, not `note-001.md`
       - Format:
         ```
         # Title
         tags: keyword1, keyword2, keyword3
         ```
         Then clear, scannable content with headers/bullets/tables as needed
       - **Always include a `tags:` line** after the title with 2-5 lowercase keywords for search filtering
       - Include: what, why, and any specific values/commands/gotchas worth remembering

    4. **Index it**: Run `corvid index <filepath>`

    5. **Update INDEX.md**: Add or update the one-line entry in `~/corvid/INDEX.md`

    ## Searching

    ```bash
    corvid search "<query>" --json              # hybrid keyword + semantic search
    corvid search "<query>" --tags auth,deploy   # filter by tags before searching
    corvid facts <subject>                       # check known facts and superseded ones
    ```

    Use `--tags` to narrow results when you know the domain. Use `corvid facts` to check if a fact has been superseded before relying on it.

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
""")


_HOOK_COMMAND = 'python3 -c "import sys; sys.exit(0)" # corvid: wiki reminder active'
_HOOK_SCRIPT = textwrap.dedent("""\
    #!/usr/bin/env python3
    # corvid PreToolUse hook: remind agent to check wiki before searching
    import json, sys, os
    DB = os.path.expanduser("~/corvid/corvid.db")
    if not os.path.exists(DB):
        sys.exit(0)
    event = json.load(sys.stdin)
    tool = event.get("tool_name", "")
    if tool in ("Bash", "Glob", "Grep"):
        inp = json.dumps(event.get("tool_input", {})).lower()
        # Don't trigger on corvid's own commands
        if "corvid" not in inp:
            print(json.dumps({
                "decision": "approve",
                "reason": "Tip: corvid wiki has cross-project knowledge. "
                          "Run `corvid search \\"<topic>\\" --json` to check for relevant insights."
            }))
            sys.exit(0)
    sys.exit(0)
""")


def _install_hook():
    """Install PreToolUse hook in Claude Code settings."""
    settings_dir = os.path.expanduser("~/.claude")
    settings_path = os.path.join(settings_dir, "settings.json")

    # Write hook script
    hook_dir = os.path.join(settings_dir, "hooks")
    os.makedirs(hook_dir, exist_ok=True)
    hook_path = os.path.join(hook_dir, "corvid_remind.py")
    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(_HOOK_SCRIPT)
    os.chmod(hook_path, 0o755)

    # Read existing settings
    settings = {}
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError:
                settings = {}

    # Add hook if not already present
    hooks = settings.setdefault("hooks", {})
    pre_hooks = hooks.setdefault("PreToolUse", [])
    hook_entry = {"type": "command", "command": f"python3 {hook_path}"}
    # Check if already installed
    if not any("corvid_remind" in str(h.get("command", "")) for h in pre_hooks):
        pre_hooks.append(hook_entry)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        return True
    return False


def cmd_install():
    """Detect agents, install skill, initialize database."""
    print()

    # 1. Detect and install to agents
    installed = []
    for agent_name, skill_dir in AGENTS.items():
        agent_base = os.path.dirname(os.path.dirname(skill_dir))  # e.g. ~/.claude
        if os.path.isdir(agent_base):
            os.makedirs(skill_dir, exist_ok=True)
            skill_path = os.path.join(skill_dir, "SKILL.md")
            with open(skill_path, "w", encoding="utf-8") as f:
                f.write(_SKILL_MD)
            installed.append((agent_name, skill_path))
            print(f"  \u2713 {agent_name:16s} \u2192 {skill_path}")
        else:
            print(f"  - {agent_name:16s} \u2192 not found, skipping")

    if not installed:
        skill_dir = AGENTS["Claude Code"]
        os.makedirs(skill_dir, exist_ok=True)
        skill_path = os.path.join(skill_dir, "SKILL.md")
        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(_SKILL_MD)
        installed.append(("Claude Code", skill_path))
        print(f"  \u2713 Claude Code      \u2192 {skill_path} (created)")

    # 2. Install PreToolUse hook for Claude Code
    if os.path.isdir(os.path.expanduser("~/.claude")):
        if _install_hook():
            print(f"  \u2713 PreToolUse hook  \u2192 wiki reminder before Bash/Glob/Grep")
        else:
            print(f"  - PreToolUse hook  \u2192 already installed")

    # 3. Init wiki + database
    print()
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    conn = get_db()
    conn.close()
    print(f"  Wiki: {WIKI_DIR}")
    print(f"  Database: {DB_PATH}")

    # 4. Report semantic search status
    print()
    if _SEMANTIC_AVAILABLE:
        print(f"  Semantic search: enabled ({EMBED_MODEL})")
    else:
        print("  Semantic search: disabled")
        print("  Run: pip install fastembed sqlite-vec")

    print()
    print("  Done. Use /remember in your next session.")
    print()


# ── CLI ────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "install":
        cmd_install()

    elif cmd == "init":
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
            print("Usage: corvid search <query> [--json] [--tags tag1,tag2]")
            return
        as_json = "--json" in sys.argv
        tags = None
        remaining = []
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--json":
                i += 1
            elif sys.argv[i] == "--tags" and i + 1 < len(sys.argv):
                tags = [t.strip().lower() for t in sys.argv[i + 1].split(",")]
                i += 2
            else:
                remaining.append(sys.argv[i])
                i += 1
        query = " ".join(remaining)
        cmd_search(query, as_json=as_json, tags=tags)

    elif cmd == "facts":
        subject = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        cmd_facts(subject)

    elif cmd == "stats":
        cmd_stats()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
