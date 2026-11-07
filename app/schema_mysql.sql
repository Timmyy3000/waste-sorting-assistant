-- Subsystem B – Data & Rules (owner: Caleb)
-- The same two tables as schema.sql, written for MySQL 8 (used by MySQLDatabase).
-- Differences: AUTO_INCREMENT instead of AUTOINCREMENT, VARCHAR(n) for key columns,
-- DOUBLE for decimals, TINYINT for 0/1. Do not use semicolons inside comments.

CREATE TABLE IF NOT EXISTS scans (
    id          INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    timestamp   VARCHAR(32)  NOT NULL,              -- ISO text, same as in SQLite
    region      VARCHAR(100) NOT NULL,
    category    VARCHAR(20)  NOT NULL
                CHECK (category IN ('recyclable', 'compostable', 'landfill', 'unknown')),
    material    VARCHAR(200) NOT NULL,
    confidence  DOUBLE       NOT NULL
                CHECK (confidence BETWEEN 0 AND 1),
    corrected   TINYINT      NOT NULL DEFAULT 0
                CHECK (corrected IN (0, 1))
);

CREATE TABLE IF NOT EXISTS rules (
    region        VARCHAR(100) NOT NULL,
    category      VARCHAR(20)  NOT NULL
                  CHECK (category IN ('recyclable', 'compostable', 'landfill', 'unknown')),
    bin           VARCHAR(200) NOT NULL,
    instructions  TEXT         NOT NULL,
    PRIMARY KEY (region, category)
);

CREATE TABLE IF NOT EXISTS scan_reviews (
    scan_id INT NOT NULL PRIMARY KEY,
    owner_hash VARCHAR(64) NOT NULL,
    stream VARCHAR(24) NOT NULL,
    status VARCHAR(24) NOT NULL,
    ai_category VARCHAR(20) NOT NULL,
    ai_material VARCHAR(200) NOT NULL,
    ai_confidence DOUBLE NOT NULL,
    match_score DOUBLE NULL,
    version INT NOT NULL DEFAULT 0,
    FOREIGN KEY (scan_id) REFERENCES scans(id)
);

CREATE TABLE IF NOT EXISTS scan_corrections (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    scan_id INT NOT NULL,
    changed_at VARCHAR(32) NOT NULL,
    old_stream VARCHAR(24) NOT NULL,
    new_stream VARCHAR(24) NOT NULL,
    old_material VARCHAR(200) NOT NULL,
    new_material VARCHAR(200) NOT NULL,
    FOREIGN KEY (scan_id) REFERENCES scans(id)
);

CREATE TABLE IF NOT EXISTS photo_uploads (
    owner_hash VARCHAR(64) NOT NULL,
    region VARCHAR(100) NOT NULL,
    image_hash CHAR(64) NOT NULL,
    scan_id INT NOT NULL PRIMARY KEY,
    INDEX photo_uploads_lookup (owner_hash, region, image_hash),
    FOREIGN KEY (scan_id) REFERENCES scans(id)
);
