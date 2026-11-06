# AI-Powered Waste Sorting & Recycling Assistant

Waste-sorting prototype with region-specific disposal rules and recycling-rate
analytics. Photo classification requires a separately verified vision provider;
the included KI:connect configuration currently returns unverified results.

Capstone project, Compact Programming Course (Python), FH Dortmund, WS 2026/27.

**Problem:** people don't know which bin an item belongs in, and municipalities don't know their recycling rates.

## Team

| Member | Subsystem | Files |
|---|---|---|
| Oluwatimilehin Ogunme | A - AI Services | `ai_services.py` |
| Terkuma Caleb Lumun | B - Data & Rules | `db.py`, `schema.sql`, `schema_mysql.sql`, `data/rules_seed.csv`, `tests/test_db.py` |
| Onyedikachi Onah | C - Dashboard & Analytics | `analytics.py` |
| Moye Nyuysoni Glein Perry | D - Web App & Integration | `app/__init__.py`, `app/routes/`, `app/templates/`, `Dockerfile`, `README.md` |

## Architecture

```mermaid
flowchart LR
    User --> D["D: Web App (Flask)"]
    D -->|photo| A["A: AI Services"]
    A -->|vision and text| OpenAI[(OpenAI API)]
    D -->|save scan, get rules| B["B: Data & Rules (SQLite / MySQL)"]
    D -->|show charts| C["C: Dashboard & Analytics"]
    C -->|get_scans| B
```

## Project structure

```
app/                  Flask app
  __init__.py         create_app()
  templates/          Jinja templates (D)
  ai_services.py      A - AI Services
  db.py, schema*.sql  B - Data & Rules
  analytics.py        C - Dashboard & Analytics (RecyclingStats, StatsCalculator, ChartRenderer)
data/rules_seed.csv   B - recycling rules
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

### AI configuration: one server, many browser users

The API key belongs to the **Flask server**, never to browser JavaScript.
People using the hosted site do not need a key. Someone running their own
server needs their own credential or administrator-provided secret.

1. Keep the key in a private file **outside this repository**, readable only by
   the server account. The provided Desktop key has been copied to a protected
   local application folder on the development machine; it is not in Git.
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY_FILE` to that file's
   absolute path. Configure `OPENAI_BASE_URL` and `OPENAI_MODEL` as in the example.
3. Start Flask normally. `AppConfig.configure_ai()` loads the secret server-side.
   An existing `OPENAI_API_KEY` environment variable takes precedence.

The sample KI:connect configuration uses `https://chat.kiconnect.nrw/api/v1`.
**Photo classification is not verified on this provider.** Live checks with
`mistralai-mistral-small-4` mislabeled cardboard, metal, glass and plastic with
high reported confidence; sending an image successfully did not mean the model
actually interpreted it. For this endpoint the app deliberately does not call
the model: uploads receive an `unknown` result and a prompt to consult local
guidance, not a guessed bin. A separately configured, verified vision provider
can use the normal classification workflow. Even then, model confidence is not
measured accuracy and local rules are category-level, not item-specific. Only
classification records, not photo files, are stored here.

### German disposal guidance and corrections (final `main`)

Results use conservative disposal routes: **Bioabfall, Restmüll, paper/cardboard,
lightweight packaging, Altglas, Pfand returns, electronics/batteries, hazardous
waste, bulky waste and end-of-life vehicles**. A bottle cannot be assigned a bin
from material alone: check for Pfand first. Food scraps generally belong in the
Biotonne, but local rules for meat/cooked food vary. Munich's packaging collection
is changing in 2026–27, so users must verify their address against AWM. Each
result links to the official EDG, BSR or AWM waste guide. The app is not a
complete Abfall-ABC and cannot guarantee correct disposal for every item.

Use **Sort without a photo** when no reliable vision service is available. You
choose the item and disposal route, then the server shows the local guidance.
After a scan, use **Correct or confirm this result** to identify the item and
choose the appropriate route. The database preserves the initial model response
and an append-only correction log, while the dashboard and JSON statistics use
the latest saved choice. Recent history is visible only to the browser that
created it. Older scans remain in aggregate statistics but are not editable.
Even a high-confidence model suggestion does **not** display a bin until the
user confirms or corrects it. This prevents a model confusing a whole banana
with a banana peel from immediately giving disposal instructions.
Cookies and a CSRF token protect corrections, but anonymous browser ownership
is not an account system: clearing cookies loses access to previous edits. Set
`FLASK_SECRET_KEY` to a persistent, unpredictable server secret for deployment
or access to browser-owned scans will be lost after a restart. Do not share a
single browser session among multiple people. Public deployment additionally
requires authentication, HTTPS, rate limits and privacy review.

Dashboard figures are **counts of saved choices**, not measured real-world
recycling or validated AI accuracy. User corrections do not retrain the model.
Automated vision remains off for the included unverified KI:connect endpoint.

### Image formats and model evaluation

The upload form accepts JPG, PNG, WebP, still GIF, BMP, TIFF, AVIF and HEIC/HEIF.
Pillow (and `pillow-heif` for HEIC) checks the **actual bytes**, rejects corrupt,
animated or excessively large images, corrects camera orientation, and sends a
resized JPEG to a configured vision provider. SVG and other active formats are
not accepted. The 5 MB input limit and 20-megapixel pixel limit still apply.
The homepage illustrates each collection stream using original SVG drawings,
not photographs of local municipal containers; the city guide remains the
source of truth. A visible build label and `X-App-Version` header help detect an
old server process, and versioned asset URLs prevent stale browser CSS/JS.

[TrashPanda](https://huggingface.co/datasets/rfabrik/TrashPanda) describes six
German waste classes, but its dataset card does not declare a licence. Do not
copy, redistribute or train on its images until permission is verified. An
optional local-only evaluation script is provided for appropriately obtained
files: `python scripts/evaluate_trashpanda.py PATH_TO_TRASHPANDA`. It refuses the
known-unreliable KI:connect endpoint and reports repeated predictions without
modifying the application database. A matching broad class is not proof of
correct disposal (notably for Pfand bottles and mixed/special waste).

### Docker with MySQL

With the same local `.env` and external key file, run:

```bash
docker compose up --build
```

Open <http://localhost:5000/scan> or <http://localhost:5000/dashboard>.

Compose mounts the key as `/run/secrets/ai_api_key`; it is not baked into the
image. `.dockerignore` excludes local configuration, databases and credential
files. A Docker Compose file secret is a read-only file mount, not an encrypted
vault: the host administrator still controls it. Never commit the key or `.env`.

The supplied Flask command is a **local development server**, not a public
deployment. To share the app publicly, deploy the backend behind HTTPS with a
production WSGI server, authentication/usage limits appropriate to your provider
quota, and managed secrets. No public hosting has been provisioned by this repo.

## Branches

Each homework assignment has its own branch: `Homeworkassignment001` through `Homeworkassignment004`.
`main` is the final integrated application. The homework branches preserve their
assignment-specific versions; contributor branches are removed only after their
commits are verified as included in the matching homework branch.

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
    }
    class AIClient {
        +model: str
        +connect()
        +call_vision(prompt, image_bytes, mime_type) str
        +call_text(prompt) str
    }
    class AIService {
        +classify_image(image_bytes) Classification
        +generate_tip(category, region) str
        +classify_upload(image_bytes, region) dict
    }
    class AIServiceError
    class InvalidImageError
    class ImageTooLargeError
    class AIUnavailableError
    AIService o-- AIClient
    AIService ..> Classification : creates
    Exception <|-- AIServiceError
    AIServiceError <|-- InvalidImageError
    AIServiceError <|-- ImageTooLargeError
    AIServiceError <|-- AIUnavailableError
```

### Subsystem B (Data & Rules)

```mermaid
classDiagram
    direction TB
    class Scan
    class RecyclingRule
    class Database {
        +path: str
        +connect()
        +close()
        +create_tables()
        +execute(sql, params) int
        +query(sql, params) list~dict~
    }
    class MySQLDatabase {
        +host: str
        +name: str
        #_open_connection()
        #_convert_sql(sql) str
    }
    class BaseRepository {
        <<abstract>>
        +database: Database
        #_row_to_object(row)*
    }
    class ScanRepository {
        +save_scan(scan) int
        +get_scans(region, start, end) list~Scan~
    }
    class RuleRepository {
        +load_from_csv(path) int
        +get_rule(region, category) RecyclingRule
        +get_regions() list~str~
    }
    class Processor {
        <<abstract>>
        +process(events)* Iterator
    }
    class DbSink {
        +repository: ScanRepository
        +saved: int
        +process(events) Iterator~ScanEvent~
    }
    class DatabaseError
    class InvalidScanError
    class RuleNotFoundError
    Database <|-- MySQLDatabase
    BaseRepository <|-- ScanRepository
    BaseRepository <|-- RuleRepository
    Processor <|-- DbSink
    Exception <|-- DatabaseError
    DatabaseError <|-- InvalidScanError
    DatabaseError <|-- RuleNotFoundError
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
    class AnalyticsError
    class InvalidAnalyticsInputError
    class NoDataError
    Processor <|-- RegionFilter
    Processor <|-- CategoryTally
    Processor <|-- RunningRecyclingRateTracker
    Exception <|-- AnalyticsError
    AnalyticsError <|-- InvalidAnalyticsInputError
    AnalyticsError <|-- NoDataError
    StatsCalculator ..> ScanRepository : reads scans only
    StatsCalculator ..> RecyclingStats : builds
    ChartRenderer ..> RecyclingStats : plots
```

HT3: ``DashboardBlueprint`` (subsystem D's routes file) calls ``build_dashboard_payload()`` from ``analytics.py``, which uses only ``ScanRepository.get_scans()`` and returns JSON-friendly fields plus a base64 PNG. Endpoints: ``GET /dashboard`` (HTML + chart) and ``GET /dashboard/data`` (JSON).

### Subsystem D (Web App & Integration)

Moye's classes are shown last, matching the presentation order. Solid triangle
arrows mean inheritance; dashed arrows mean dependencies.

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
        +configure_ai()
    }
    class AppFactory {
        +__init__(config)
        +config: AppConfig
        +create() Flask
        #_register_error_handlers(app)
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
    class ScanWorkflow {
        -_service: AIService
        +__init__(service)
        +get_regions() list~str~
        +submit(upload, region) dict
    }
    class DashboardBlueprint {
        +__init__()
        +register_routes()
        +dashboard()
        +dashboard_data()
    }
    class ApiBlueprint {
        +__init__()
        +register_routes()
        +stats()
        +classify()
    }
    class WebAppError
    class UploadError
    BaseBlueprint <|-- ScanBlueprint
    BaseBlueprint <|-- DashboardBlueprint
    BaseBlueprint <|-- ApiBlueprint
    Exception <|-- WebAppError
    WebAppError <|-- UploadError
    AppFactory ..> AppConfig : configures
    AppFactory ..> ScanBlueprint : registers
    AppFactory ..> DashboardBlueprint : registers
    AppFactory ..> ApiBlueprint : registers
    ScanBlueprint ..> ScanWorkflow : submits upload
    ApiBlueprint ..> ScanWorkflow : same workflow
    ScanWorkflow ..> AIService : classifies and tips
    ScanWorkflow ..> ScanRepository : saves
    ScanWorkflow ..> RuleRepository : checks local rules
    ScanWorkflow ..> UploadError : rejects invalid input
```

#### D's pipeline runner

```mermaid
classDiagram
    direction LR
    class Pipeline {
        -_source: Source
        -_processors: list~Processor~
        +__init__(source, processors)
        +__or__(processor) Pipeline
        +run() Iterator~ScanEvent~
        +__iter__() Iterator~ScanEvent~
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

**D data flow:** `create_app()` calls `AppFactory.create()` to configure the app,
load rules, register blueprints and install error handlers. Flask calls `scan()`
for an upload; `ScanWorkflow.submit()` validates it, calls A, reads B's rule, and
saves through B's repository. HTML and JSON routes share this workflow.
`dashboard_payload()` calls C's `build_dashboard_payload()` and adapts its counts
to exclude unknown items from the recycling-rate denominator. Connections are
opened and closed per request. Source and Processor belong to Timi; Pipeline
belongs to Moye. Run `python demo_pipeline.py` for the complete simulated chain.

Shared Jinja templates, local CSS and small JavaScript enhancements provide the
interface. Credentials are read by the server, never by the browser. HT1/HT2
contain styled previews; live integration starts in HT3.

## Testing and coverage

Run `pytest` for the team tests. The original 15-test target is retained and
expanded with regression cases for the new web workflow: real SQLite saves,
mocked classification, invalid regions/files, provider failures, rate handling,
JSON errors, date filters and static assets. Live-provider smoke checks are run
separately and do not make automated tests depend on the network or a real key.
Run `pytest --cov=app --cov-branch` for statement and branch coverage. Coverage
shows exercised code, not proof that every behaviour is correct.

The preserved HT4 assignment branch previously passed 35 tests. Final `main`
adds city-specific guidance, correction and ownership tests. Earlier live tests
revealed severe KI:connect misidentification, so sending images to that endpoint
is disabled. Live samples use an isolated SQLite database and do not alter the
normal dashboard. Passing route tests does not prove photo recognition accuracy.

## Team video

_Link added with each homework assignment._
