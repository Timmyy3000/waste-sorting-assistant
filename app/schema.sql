-- Subsystem B – Data & Rules (owner: Caleb)
-- Database schema. Database.create_tables() runs this file.
-- "IF NOT EXISTS" means running it twice does no harm.

-- One row per photo the app has classified.
CREATE TABLE IF NOT EXISTS scans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,              -- ISO format, e.g. 2026-11-05T14:30:00
    region      TEXT    NOT NULL,
    category    TEXT    NOT NULL
                CHECK (category IN ('recyclable', 'compostable', 'landfill', 'unknown')),
    material    TEXT    NOT NULL,
    confidence  REAL    NOT NULL
                CHECK (confidence BETWEEN 0 AND 1),
    corrected   INTEGER NOT NULL DEFAULT 0     -- 0 = False, 1 = True (user fixed the category)
                CHECK (corrected IN (0, 1))
);

-- One disposal rule per (region, category) pair.
CREATE TABLE IF NOT EXISTS rules (
    region        TEXT NOT NULL,
    category      TEXT NOT NULL
                  CHECK (category IN ('recyclable', 'compostable', 'landfill', 'unknown')),
    bin           TEXT NOT NULL,               -- e.g. "Gelbe Tonne"
    instructions  TEXT NOT NULL,               -- short how-to for the user
    PRIMARY KEY (region, category)
);

-- Additive tables preserve existing scans and category-based rules.
CREATE TABLE IF NOT EXISTS scan_reviews (
    scan_id INTEGER PRIMARY KEY,
    owner_hash TEXT NOT NULL,
    stream TEXT NOT NULL,
    status TEXT NOT NULL,
    ai_category TEXT NOT NULL,
    ai_material TEXT NOT NULL,
    ai_confidence REAL NOT NULL,
    match_score REAL DEFAULT NULL,        -- optional raw image/text similarity, not confidence
    version INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (scan_id) REFERENCES scans(id)
);

CREATE TABLE IF NOT EXISTS scan_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    changed_at TEXT NOT NULL,
    old_stream TEXT NOT NULL,
    new_stream TEXT NOT NULL,
    old_material TEXT NOT NULL,
    new_material TEXT NOT NULL,
    FOREIGN KEY (scan_id) REFERENCES scans(id)
);

-- No photos stored: exact upload fingerprints are browser- and city-scoped.
CREATE TABLE IF NOT EXISTS photo_uploads (
    owner_hash TEXT NOT NULL,
    region TEXT NOT NULL,
    image_hash TEXT NOT NULL,
    scan_id INTEGER NOT NULL PRIMARY KEY,
    FOREIGN KEY (scan_id) REFERENCES scans(id)
);

CREATE INDEX IF NOT EXISTS photo_uploads_lookup ON photo_uploads(owner_hash, region, image_hash);
