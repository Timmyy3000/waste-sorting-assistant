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
