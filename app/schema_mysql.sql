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
