import sqlite3
import os

# database/rkart.db sits next to app.py — matches the existing project structure.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "rkart.db")


def get_db():
    """
    Returns a sqlite3 connection with Row factory (dict-like row access:
    row['email'] instead of row[2]). Call conn.close() when done, or use
    it in a `with` block via contextlib if you prefer — kept plain here
    to match the simple style of the rest of the project.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    Creates all RKart tables if they don't already exist. Safe to call on
    every app startup (CREATE TABLE IF NOT EXISTS — never drops/overwrites
    existing data).

    Ownership rule (requirement #17): every table that stores personal
    data carries a user_id column with ON DELETE CASCADE. Every query
    that reads/writes these tables in the auth/collections/compare routes
    MUST filter by the logged-in user's id — the schema alone does not
    enforce that, the route code does.
    """
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name     TEXT NOT NULL,
        email         TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS collections (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        name       TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS collection_products (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_id INTEGER NOT NULL,
        name          TEXT NOT NULL,
        store         TEXT NOT NULL,
        price         REAL,
        image         TEXT,
        link          TEXT,
        added_at      TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS saved_products (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        name       TEXT NOT NULL,
        store      TEXT NOT NULL,
        price      REAL,
        image      TEXT,
        link       TEXT,
        saved_at   TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS compare_list (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        name       TEXT NOT NULL,
        store      TEXT NOT NULL,
        price      REAL,
        image      TEXT,
        link       TEXT,
        added_at   TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS recently_compared (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        query        TEXT NOT NULL,
        searched_at  TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS trending_prices (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        query        TEXT NOT NULL,
        name         TEXT NOT NULL,
        store        TEXT NOT NULL,
        price        REAL NOT NULL,
        image        TEXT,
        link         TEXT,
        found_at     TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    # Run this file directly once to create the DB before first launch:
    #     python models.py
    init_db()
    print(f"RKart database ready at {DB_PATH}")
