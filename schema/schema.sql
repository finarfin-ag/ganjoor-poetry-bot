PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poets (
    id INTEGER PRIMARY KEY,
    nickname TEXT NOT NULL,
    name TEXT,
    description TEXT,
    source_path TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    poet_id INTEGER NOT NULL REFERENCES poets(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    source_path TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS poems (
    id INTEGER PRIMARY KEY,
    poet_id INTEGER NOT NULL REFERENCES poets(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    title TEXT,
    title_normalized TEXT NOT NULL DEFAULT '',
    metre_id INTEGER,
    metre TEXT,
    rhyme TEXT,
    source_path TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS verses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poem_id INTEGER NOT NULL REFERENCES poems(id) ON DELETE CASCADE,
    verse_order INTEGER NOT NULL,
    position TEXT,
    couplet_index INTEGER,
    section_index INTEGER,
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    UNIQUE(poem_id, verse_order)
);

CREATE INDEX IF NOT EXISTS idx_categories_poet ON categories(poet_id);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id);
CREATE INDEX IF NOT EXISTS idx_poems_poet ON poems(poet_id);
CREATE INDEX IF NOT EXISTS idx_poems_category ON poems(category_id);
CREATE INDEX IF NOT EXISTS idx_verses_poem_order ON verses(poem_id, verse_order);

CREATE VIRTUAL TABLE IF NOT EXISTS verse_fts USING fts5(
    text,
    normalized_text,
    poem_id UNINDEXED,
    verse_order UNINDEXED,
    tokenize='unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS poem_fts USING fts5(
    title,
    title_normalized,
    poem_id UNINDEXED,
    tokenize='unicode61'
);
