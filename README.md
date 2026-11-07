# AI-Powered Waste Sorting & Recycling Assistant

Photo-based household waste classification with region-specific disposal rules and recycling-rate analytics.

Capstone project, Compact Programming Course (Python), FH Dortmund, WS 2026/27.

**Problem:** people don't know which bin an item belongs in, and municipalities don't know their recycling rates.

## Team

| Member | Subsystem | Files |
|---|---|---|
| Oluwatimilehin Ogunme | A · AI Services | `ai_services.py`, `ai_prompts.py` |
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
    direction TB
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
    BaseRepository <|-- ScanRepository
    BaseRepository <|-- RuleRepository
    BaseRepository o-- Database : uses
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
    class ScanRepository {
        +get_scans(...) list~Scan~
    }
    StatsCalculator ..> ScanRepository : reads scans only
    StatsCalculator ..> RecyclingStats : builds
    ChartRenderer ..> RecyclingStats : plots
```

### Subsystem D (Web App & Integration)

Subsystem D's five implemented classes are shown below. Solid hollow-triangle
arrows show inheritance; the solid arrow from `AppFactory` to `AppConfig` shows
a stored-object association; dashed arrows show registration dependencies.
Notes beside the blueprints identify **planned**, not implemented, connections
to A, B and C. In HT1, the web routes only display styled preview pages;
live AI/database integration starts in HT3.

```mermaid
classDiagram
    direction TB
    class AppConfig {
        -_upload_limit: int
        -_allowed_types: set
        -_database_host: str
        -_database_name: str
        -_database_user: str
        -_database_password: str
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
    AppFactory --> AppConfig : holds
    AppFactory ..> ScanBlueprint : registers
    AppFactory ..> DashboardBlueprint : registers
    note for ScanBlueprint "Planned: A AIService; B ScanRepository and RuleRepository"
    note for DashboardBlueprint "Planned: C StatsCalculator and ChartRenderer"
```

`create_app()` calls `AppFactory.create()`, which registers the two route
groups. Configuration lives in an `AppConfig` object; the web layer does not
yet store scan data. The dashed arrows represent registration dependencies,
not inheritance or implemented cross-subsystem calls.

**Where D's state lives:** `AppConfig` owns private configuration attributes;
`AppFactory.config` holds that configuration object; `BaseBlueprint._blueprint`
holds the Flask route group inherited by each concrete subclass. Properties
provide controlled access. Flask calls `scan()` or `dashboard()` after matching
the request URL. The shared templates and local CSS/JavaScript provide the
green-and-white interface; preview actions are explicitly disabled on HT1.

**Subsystem D — Web Application & Integration.** D provides the Flask user
interface and application structure for the Waste Sorting Assistant:

- `AppFactory` initializes Flask and registers the web routes.
- `ScanBlueprint` provides the scanning preview. It is **designed** to use A's
  `AIService` for classification and B's `ScanRepository` and `RuleRepository`
  for saving scans and retrieving regional disposal rules.
- `DashboardBlueprint` provides the dashboard preview. It is **designed** to
  display statistics from C's `StatsCalculator` and `ChartRenderer`.

For Homework Assignment 1, D demonstrates encapsulation, inheritance,
abstraction and initialization. These A/B/C connections are **planned
architecture only**: no scan or dashboard route calls those subsystems yet,
so the diagram intentionally has no dependency arrows to their classes.
`AppConfig` still shows its actual server-oriented settings; a future switch
to SQLite's `database_path` must change the Python class and UML together.

## Team video

[Watch the Hometask 1 team video](https://github.com/Timmyy3000/waste-sorting-assistant/releases/download/hometask-videos/Hometask1.mp4)
