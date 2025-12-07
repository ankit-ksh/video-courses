import os
import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime
from multiprocessing import Pool, cpu_count

INPUT_DIR = Path("./collections")
DB_PATH = Path("./content.db")

# SQLite setup
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    source TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    languages TEXT,
    created_at TEXT,
    UNIQUE(provider, collection_id)
);

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS instructors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS collection_domains (
    collection_id INTEGER,
    domain_id INTEGER,
    PRIMARY KEY (collection_id, domain_id)
);

CREATE TABLE IF NOT EXISTS collection_topics (
    collection_id INTEGER,
    topic_id INTEGER,
    PRIMARY KEY (collection_id, topic_id)
);

CREATE TABLE IF NOT EXISTS collection_tags (
    collection_id INTEGER,
    tag_id INTEGER,
    PRIMARY KEY (collection_id, tag_id)
);

CREATE TABLE IF NOT EXISTS collection_instructors (
    collection_id INTEGER,
    instructor_id INTEGER,
    PRIMARY KEY (collection_id, instructor_id)
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER,
    video_id TEXT,
    title TEXT,
    position INTEGER
);
""")

conn.commit()

# --------------------------------
# Helpers
# --------------------------------

def yt_fetch_flat(collection_id):
    """FAST: flat playlist only."""
    result = subprocess.run(
        ["yt-dlp", "-J", "--flat-playlist", f"https://www.youtube.com/playlist?list={collection_id}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        print("ERROR fetching:", result.stderr)
        return None
    return json.loads(result.stdout)


def get_or_create(table, name):
    cur.execute(f"SELECT id FROM {table} WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(f"INSERT INTO {table}(name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


# --------------------------------
# Load collections JSON
# --------------------------------

all_entries = []
for file in INPUT_DIR.glob("*.json"):
    data = json.loads(file.read_text())
    all_entries.extend(data)

print(f"Found {len(all_entries)} collections.")

# --------------------------------
# Parallel fetch playlist metadata
# --------------------------------

def fetch_worker(entry):
    cid = entry["collection_id"]
    meta = yt_fetch_flat(cid)
    return (entry, meta)

PARALLEL = min(cpu_count() * 2, 16)

with Pool(PARALLEL) as p:
    results = p.map(fetch_worker, all_entries)

# --------------------------------
# Insert into DB
# --------------------------------

for entry, meta in results:

    if not meta:
        print("Skipping due to failed metadata.")
        continue

    provider = entry["provider"]
    source = entry["source"]
    cid = entry["collection_id"]
    title = entry["title"]
    domains = entry.get("domains", [])
    topics = entry.get("topics", [])
    tags = entry.get("tags", [])
    languages = entry.get("languages", ["en"])
    instructors = entry.get("instructors", [])
    created_at = datetime.now().strftime("%Y-%m-%d")

    description = meta.get("description", "")
    videos_raw = meta.get("entries", [])

    print(f"Inserting into DB: {title} ({cid})")

    # Insert collection
    try:
        cur.execute("""
            INSERT INTO collections(provider, source, collection_id, title, description, languages, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (provider, source, cid, title, description, json.dumps(languages), created_at))
        conn.commit()
        col_id = cur.lastrowid
    except sqlite3.IntegrityError:
        cur.execute("SELECT id FROM collections WHERE provider=? AND collection_id=?", (provider, cid))
        col_id = cur.fetchone()[0]

    # Domains
    for d in domains:
        did = get_or_create("domains", d)
        cur.execute("INSERT OR IGNORE INTO collection_domains VALUES (?,?)", (col_id, did))

    # Topics
    for t in topics:
        tid = get_or_create("topics", t)
        cur.execute("INSERT OR IGNORE INTO collection_topics VALUES (?,?)", (col_id, tid))

    # Tags
    for t in tags:
        tid = get_or_create("tags", t)
        cur.execute("INSERT OR IGNORE INTO collection_tags VALUES (?,?)", (col_id, tid))

    # Instructors
    for inst in instructors:
        iid = get_or_create("instructors", inst)
        cur.execute("INSERT OR IGNORE INTO collection_instructors VALUES (?,?)", (col_id, iid))

    # Videos
    pos = 1
    for v in videos_raw:
        cur.execute("""
            INSERT INTO videos(collection_id, video_id, title, position)
            VALUES (?, ?, ?, ?)
        """, (col_id, v.get("id"), v.get("title", ""), pos))
        pos += 1

    conn.commit()

print("\n✔ DONE — fast DB built!")
conn.close()

