# AI-Powered Waste Sorting & Recycling Assistant

Photo-based household waste classification with region-specific disposal rules and recycling-rate analytics.

Capstone project, Compact Programming Course (Python), FH Dortmund, WS 2026/27.

**Problem:** people don't know which bin an item belongs in, and municipalities don't know their recycling rates.

## Team

| Member | Subsystem | Files |
|---|---|---|
| Oluwatimilehin Ogunme | A · AI Services | `ai_services.py` |
| Terkuma Caleb Lumun | B · Data & Rules | `db.py`, `schema.sql`, `data/rules_seed.csv`, `tests/test_db.py` |
| Onyedikachi Onah | C · Dashboard & Analytics | `analytics.py` |
| Moye Nyuysoni Glein Perry | D · Web App & Integration | `app.py`, `templates/`, `Dockerfile` |

## Architecture

```mermaid
flowchart LR
    User --> D["D: Web App (Flask)"]
    D -->|photo| A["A: AI Services"]
    A -->|vision and text| OpenAI[(OpenAI API)]
    D -->|save scan, get rules| B["B: Data & Rules (SQLite)"]
    D -->|show charts| C["C: Dashboard & Analytics"]
    C -->|get_scans| B
```

## Project structure

```
app/                  Flask app
  __init__.py         create_app()
  templates/          Jinja templates (D)
  ai_services.py      A · AI Services
  db.py, schema.sql   B · Data & Rules
  analytics.py        C · Dashboard & Analytics (RecyclingStats, StatsCalculator, ChartRenderer)
data/rules_seed.csv   B · recycling rules
tests/                pytest tests, one file per subsystem
requirements.txt      Python packages
```

## Getting started

Requires Python 3.12 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
flask --app app run             # http://127.0.0.1:5000
pytest                          # run the tests
```

## Branches

Each homework assignment has its own branch: `Homeworkassignment001`, `Homeworkassignment002`, …

## UML class diagrams

The diagrams follow the team presentation order A, B, C, then D.
Only classes implemented on this assignment branch are shown.

### Subsystem A (AI Services)

```mermaid
classDiagram
    class Classification {
        +category: str
        +material: str
        +confidence: float
        +needs_confirmation: bool
        +to_dict() dict
    }
    class AIClient {
        +model: str
        +connect()
        +call_vision(prompt, image_bytes, mime_type) str
        +call_text(prompt) str
    }
    class AIService {
        +client: AIClient
        +classify_image(image_bytes) Classification
        +generate_tip(category, region) str
    }
    class ScanEvent {
        +timestamp: datetime
        +region: str
        +category: str
        +material: str
        +confidence: float
    }
    class Source {
        <<abstract>>
        +__iter__() Iterator
    }
    class Processor {
        <<abstract>>
        +process(events) Iterator
    }
    Source <|-- ClassificationEventSource
    Source <|-- SimulatedScanSource
    Source ..> ScanEvent : yields
    Processor ..> ScanEvent : processes
    AIService o-- AIClient : calls
    AIService ..> Classification : returns
```

### Subsystem B (Data & Rules)

```mermaid
classDiagram
    direction TB
    class Scan {
        +id: int or None
        +timestamp: datetime
        +region: str
        +category: str
        +material: str
        +confidence: float
        +corrected: bool
    }
    class RecyclingRule {
        +region: str
        +category: str
        +bin: str
        +instructions: str
    }
    class Database {
        +path: str
        +is_connected: bool
        +connection
        +connect()
        +close()
        +create_tables()
        +__enter__() Database
        +__exit__()
    }
    class BaseRepository {
        <<abstract>>
        +database: Database
        #_execute(sql, params) int
        #_query(sql, params) list
        #_row_to_object(row)*
    }
    class ScanRepository {
        +save_scan(scan) int
        +get_scans(region, start, end) list~Scan~
        #_row_to_object(row) Scan
    }
    class RuleRepository {
        +load_from_csv(path) int
        +get_rule(region, category) RecyclingRule
        +get_regions() list~str~
        #_row_to_object(row) RecyclingRule
    }
    class Processor {
        <<abstract>>
        +process(events)* Iterator
    }
    class DbSink {
        +repository: ScanRepository
        +saved: int
        +process(events) Iterator~ScanEvent~
        #_to_scan(event) Scan
    }
    BaseRepository <|-- ScanRepository
    BaseRepository <|-- RuleRepository
    Processor <|-- DbSink
    BaseRepository o-- Database : uses
    DbSink o-- ScanRepository : saves with
    ScanRepository ..> Scan : creates
    RuleRepository ..> RecyclingRule : creates
```

### Subsystem C (Dashboard & Analytics)

```mermaid
classDiagram
    direction LR
    class RecyclingStats {
        +category_counts: dict
        +total_scans: int
        +recycling_rate: float
        +from_scans(list~Scan~) RecyclingStats
        +record_scan(scan: Scan)
    }
    class StatsCalculator {
        +repository: ScanRepository
        +get_stats(region, start, end) RecyclingStats
        +setup()
    }
    class ChartRenderer {
        +dpi: int
        +figsize: tuple
        +render_category_bar_chart(stats) bytes
        +setup()
    }
    class Processor {
        <<abstract>>
        +process(events) Iterator
    }
    class RegionFilter {
        +region: str
        +process(events) Iterator
    }
    class CategoryTally {
        +counts: dict
        +process(events) Iterator
        +setup()
    }
    class RunningRecyclingRateTracker {
        +running_rate: float
        +process(events) Iterator
        +setup()
    }
    class ScanRepository {
        +get_scans(...) list~Scan~
    }
    Processor <|-- RegionFilter
    Processor <|-- CategoryTally
    Processor <|-- RunningRecyclingRateTracker
    StatsCalculator ..> ScanRepository : reads scans only
    StatsCalculator ..> RecyclingStats : builds
    ChartRenderer ..> RecyclingStats : plots
```

### Subsystem D (Web App & Integration)

HT2 retains the HT1 blueprint hierarchy and adds Moye's Pipeline runner.
The web pages are styled previews; live integration starts in HT3.

```mermaid
classDiagram
    direction TB
    class AppConfig {
        +__init__()
        +upload_limit: int
        +allowed_types: set
        +database_host: str
        +database_name: str
        +database_user: str
        +database_password: str
    }
    class AppFactory {
        +__init__(config)
        +config: AppConfig
        +create() Flask
    }
    class BaseBlueprint {
        <<abstract>>
        -_blueprint: Blueprint
        +__init__(name, url_prefix)
        +blueprint: Blueprint
        +register_routes()
    }
    class ScanBlueprint {
        +__init__()
        +register_routes()
        +scan()
    }
    class DashboardBlueprint {
        +__init__()
        +register_routes()
        +dashboard()
    }
    BaseBlueprint <|-- ScanBlueprint
    BaseBlueprint <|-- DashboardBlueprint
    AppFactory ..> AppConfig : configures
    AppFactory ..> ScanBlueprint : registers
    AppFactory ..> DashboardBlueprint : registers
```

#### D's HT2 pipeline runner

```mermaid
classDiagram
    direction LR
    class Pipeline {
        -_source: Source
        -_processors: list~Processor~
        +__init__(source, processors)
        +run() Iterator
        +__or__(processor) Pipeline
        +__iter__() Iterator
    }
    class Source {
        <<abstract>>
        +__iter__() Iterator
    }
    class Processor {
        <<abstract>>
        +process(events) Iterator
    }
    Pipeline o-- Source : reads
    Pipeline o-- Processor : chains
```

Run `python demo_pipeline.py` for the complete simulated stream through C's
filter/counters and B's database sink. `Pipeline.__or__()` returns a new chain;
`run()` connects the lazy generators; `__iter__()` enables for loops. Source and
Processor are Timi's contracts, not classes owned by D. Configuration lives in
AppConfig, route groups in BaseBlueprint, and the processor list in Pipeline.

## Team video

_Link added with each homework assignment._
