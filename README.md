# WAF Category Classifier

AI-powered tool for classifying JIRA stories into your organization's Work Alignment Framework (WAF) categories. Built with Flask and Anthropic's Claude AI.

## The Problem

Scrum teams consistently misclassify stories against the 8-category WAF framework. Over 80% of stories lack proper WAF tags, making portfolio-level investment reporting unreliable. This tool fixes that.

## Features

| Feature | Description |
|---------|-------------|
| **Classify** | Live chat or batch classification for new stories during grooming |
| **Analytics** | Upload JIRA data → map columns → AI reviews every row → flag mismatches → save → summary insights |
| **Story Quality** | Score uploaded backlog items against the **Story Excellence Playbook v2** Definition of Ready. Composite rubrics: universal base (Story / Feature / Epic / Defect) + optional domain extension (Data, CapMkts, SF Origination, MF Servicing, Risk). Per-criterion "what good looks like" examples surface inline on failure. Strictness mode is configurable per rubric (lenient / balanced / strict). |
| **Domain Editor** | (`/quality-domains`) Domain stewards review, edit, save, and revert the JSON criteria for their line of business — no code change needed. Backs up previous versions on save. |
| **File Merger** | Three-file Jira merge (Epic + Feature + Story) with name-based join. Per-file column mapping, status flags (complete / missing feature / missing epic), orphan handling, Missing-WAF and Missing-R/C surfacing, clickable stat-card filtering, two-phase upload + confirm flow. |
| **Disputes** | Flag any AI classification as wrong from the **Classify**, **History**, **Teams**, or **Lineage** view. Reviewers triage flagged disputes on `/disputes` — dismiss, accept into Ground Truth, or escalate for WAF review. |
| **Teams** | Drill-down team-of-teams pills → team pills → story detail. Two-panel team analytics with cross-team epic matrix. Data Source filter per upload. |
| **Epic Lineage** | Health scores, mismatch flags, story tree drill-down with collapsible feature sections and sort controls |
| **Global Search** | FTS5 full-text search across all classifications with context-rich results (breadcrumb, badges, upload source) |
| **Category Aliases** | (`/aliases`) Add custom shorthand → canonical mappings so the matcher accepts org-specific terminology without code changes |
| **WAF Reference** | Browse all 8 WAF categories — definitions, decision rules, color codes, and examples |
| **Version Library** | Save named snapshots of WAF Definitions and Ground Truth. Pick any version per classification run. Version IDs recorded in upload history for full traceability. |
| **Settings** | Manage WAF definitions (inline editable), ground truth (inline edit/add/delete), Version Library (named WAF + GT snapshots), and batch size configuration |
| **Dark/Light Mode** | Toggle in the nav bar; preference saved in localStorage |
| **Story/Feature/Epic IDs** | Optional ID fields imported from CSV/Excel, displayed in Teams and Lineage views |
| **Ground Truth Loop** | Approve correct mismatch classifications to continuously improve AI accuracy |

## WAF Categories

| Type | Color | Category |
|------|-------|----------|
| Run | GRAY | KTLO (Keep The Lights On) |
| Run | BLACK | Business Maintenance |
| Run | BLACK | Technical Maintenance |
| Run | RED | Regulatory (Operational) |
| Change | RED | Regulatory Mandated Change |
| Change | ORANGE | Enterprise Strategic Priority |
| Change | YELLOW | Top Divisional Priority |
| Change | GREEN | Other Block Priority |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/ad25343/waf-classifier.git
cd waf-classifier

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum

# 4. Run the server
python app.py

# 5. Open in browser
open http://localhost:8080
```

The app auto-loads WAF definitions and ground truth from `test-data/` on startup — no manual upload needed.

**Environment variables** are documented in `.env.example`. The only required one is `ANTHROPIC_API_KEY` (or AWS Bedrock credentials). Set `APPLICATION_ROOT=/your-prefix` when deploying behind a reverse proxy.

**Test datasets** are in `test-data/` — use these to explore all features:

| File | Stories | Best for testing |
|------|---------|-----------------|
| `compliance-focus-60.csv` | 60 | Regulatory category, high mismatch rate |
| `platform-engineering-80.csv` | 80 | Infrastructure categories, cross-team epics |
| `multi-team-product-120.csv` | 120 | Multi-team views, By Epic tab, empty description edge cases |
| `synthetic-100-stories.csv` | 100 | General mixed dataset |
| `synthetic-5000-stories.csv` | 5000 | Performance and large-dataset testing |

## Pages

| Route | Page | Purpose |
|-------|------|---------|
| `/` | Home | Landing page with navigation cards and system status |
| `/classify` | Classifier | Chat-based AI classification with epic tagging |
| `/history` | Analytics | Upload → Map Columns → AI verify → Review → Summary → Story Quality → Lineage → History |
| `/teams` | Teams | Drill-down ToT → Team pills with cross-team epic matrix |
| `/lineage` | Epic Lineage | Epic health scores, WAF breakdowns, and story tree |
| `/dashboard` | Dashboard | Real-time KPI cards and distribution charts |
| `/disputes` | Disputes | Triage flagged AI classifications (dismiss / accept into GT / escalate to WAF review) |
| `/merge` | File Merger | Three-file Jira merge (Epic + Feature + Story) with name-based join, orphan handling, status filters |
| `/waf-reference` | WAF Reference | Browse all 8 WAF categories with definitions and decision rules |
| `/aliases` | Category Aliases | Add custom shorthand → canonical mappings for the matcher |
| `/quality-domains` | Domain Editor | Review and edit Definition-of-Ready extension JSONs per line of business |
| `/settings` | Settings | WAF definitions (inline editable), ground truth, Version Library, and processing configuration |

The top-nav groups views: **Home · Classify · Analyze ▾ · Admin ▾ · Settings**, where:
- **Analyze** = Analyze Stories · Epic Lineage · Teams · Classification Disputes
- **Admin** = File Merger · WAF Reference · Category Aliases · Domain Editor

## Analytics Workflow

1. **Upload Data** — Select a CSV or Excel file with JIRA stories
2. **Map Columns** — Confirm or adjust auto-detected column mappings. Title and Description are required. Optional: Team, Epic, Parent Feature, Story ID, Feature ID, Epic ID.
3. **AI Review** — Claude classifies every row against the WAF framework. All files process asynchronously with a live progress bar.
4. **Review & Save** — Sortable table shows file tags vs AI recommendations. Mismatch rows are pre-selected. Click any row for full story details. Save selected rows to history.
5. **Summary** — Portfolio-level charts: category distribution, color breakdown, Run vs Change, confidence levels, mismatch rate. Click any KPI card to drill down.
6. **Epic Lineage** — Per-epic WAF breakdown with health score, mismatch flags, and collapsible story tree.
7. **History** — View, reload, or delete previous uploads.

Each upload gets a unique ID. Use the Data Source selector to filter analytics to a specific upload or view all uploads combined.

The **Classification Settings** card on the Upload tab lets you select a specific WAF Version and GT Version for that run. Both default to the active baseline. Version IDs are stored with the upload record for traceability.

## Teams Workflow

1. Navigate to `/teams`
2. Select a **Data Source** (upload) or leave as "All Uploads"
3. **Team tab**: Left panel shows Team › Epic › Feature tree. Click any node to load stories in the right panel. Sort by any column. Click **Show Insights** for KPI cards and charts.
4. **By Epic tab**: Shows all teams contributing to each epic, with story tables per team.

## Approval Behavior

The `approved` flag is only set to `true` for **mismatch rows** — stories where the file's WAF tag differed from the AI recommendation. Match rows are saved without the approved flag. This ensures the "Approved" count represents stories that were actively reviewed and corrected, not just everything that passed through.

## Epic Health Scoring

Each epic gets a health score from 0 to 100 based on:

- **Color focus (40%)** — percentage of stories with the dominant WAF color
- **Category focus (30%)** — percentage of stories in the dominant category
- **Color diversity penalty (20%)** — fewer unique colors = healthier
- **Mismatch penalty (10%)** — fewer mismatches = healthier

Epics are flagged as "mixed" if they have 3+ WAF colors or the dominant color is below 60%.

## Security

- **Debug mode disabled** in production
- **XSS prevention** — all user-controlled data HTML-escaped before rendering
- **Safe error responses** — generic messages to client; details logged server-side only
- **Pagination cap** — maximum 500 results per page
- **Rate limiting** — bulk upload allows 5 requests per IP per minute (HTTP 429 on excess)
- **Secure filenames** — uploaded files processed with `werkzeug.utils.secure_filename`
- **No authentication** — designed for trusted internal networks only; do not expose to the public internet

## Tech Stack

- **Backend:** Python Flask with Blueprint-based modular architecture
- **AI:** Anthropic Claude API (`claude-sonnet-4-6`) or AWS Bedrock fallback
- **Frontend:** HTML/CSS/JS + Chart.js 4.4.1 + chartjs-plugin-datalabels
- **Database:** SQLite with FTS5 full-text search
- **Data:** pandas, openpyxl for CSV/Excel processing

## Project Structure

```
waf-classifier/
├── app.py                          # Flask init, blueprint registration, startup
├── config.py                       # Constants, AI backend detection, paths
├── database.py                     # SQLite schema, queries, FTS5 index, settings cache
├── state.py                        # Shared in-memory stores
├── waf_core.py                     # WAF categories, normalization, AI client, prompts
├── routes/
│   ├── pages.py                    # Page-serving routes
│   ├── classify.py                 # Classification API endpoints
│   ├── settings_api.py             # Settings, ground truth, baselines API
│   ├── analytics.py                # Dashboard, history, export, search API
│   ├── verify.py                   # Bulk verify API + worker threads
│   ├── lineage.py                  # Epic lineage API
│   └── teams.py                    # Team report API
├── .env                            # Local config — API key, port, prefix (not committed)
├── .env.example                    # Template — copy to .env and fill in values
├── requirements.txt                # Python dependencies
├── waf_history.db                  # SQLite DB (auto-created)
├── baselines/                      # Saved baseline snapshots (auto-created)
│   ├── waf/                        # Named WAF definition versions
│   └── gt/                         # Named Ground Truth versions
├── static/
│   ├── home.html                   # Home landing page
│   ├── index.html                  # Classifier chat UI
│   ├── history.html                # Analytics (Upload, Summary, Lineage, History tabs)
│   ├── teams.html                  # Team report with two-panel layout and cross-team matrix
│   ├── lineage.html                # Epic Lineage with story tree and sort controls
│   ├── dashboard.html              # Real-time dashboard
│   ├── settings.html               # Admin settings (WAF defs, ground truth, baselines, config)
│   └── waf-reference.html          # WAF framework reference guide
├── sample-data/
│   ├── waf-definitions.csv         # WAF framework (8 categories)
│   ├── sample-ground-truth.csv     # 18 calibration examples
│   ├── synthetic-100-stories.csv   # 100-record test set (quick testing)
│   ├── synthetic-100-answer-key.csv  # 100-record answer key
│   ├── synthetic-5000-stories.csv  # 5000-record full test set
│   └── synthetic-5000-answer-key.csv # 5000-record answer key
└── docs/
    ├── API_Reference.md            # API endpoint reference
    ├── Release_Notes.md            # Version changelog
    └── Quick_Start.md              # Getting started guide
```

## Sample Data

| File | Records | Purpose |
|------|---------|---------|
| `synthetic-100-stories.csv` | 100 | Quick testing — 28 epics, 8 categories, 6 colors, 15 teams, ~15% mismatches |
| `synthetic-5000-stories.csv` | 5,000 | Full testing — same distribution at scale |

The `-answer-key.csv` variants include correct WAF Category, Color, Run/Change, and Is Mismatch columns.

## Documentation

- **[API Reference](docs/API_Reference.md)** — All endpoints with request/response specs
- **[Release Notes](docs/Release_Notes.md)** — Version history and changelog
- **[Quick Start](docs/Quick_Start.md)** — 5-minute setup guide

## License

Internal use only.
