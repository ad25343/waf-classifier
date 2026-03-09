# WAF Category Classifier

AI-powered tool for classifying JIRA stories into your organization's Work Alignment Framework (WAF) categories. Built with Flask and Anthropic's Claude AI.

## The Problem

Scrum teams consistently misclassify stories against the 8-category WAF framework. Over 80% of stories lack proper WAF tags, making portfolio-level investment reporting unreliable. This tool fixes that.

## Features

| Feature | Description |
|---------|-------------|
| **Classify** | Live chat or batch classification for new stories during grooming |
| **Analytics** | Upload JIRA data → AI reviews every row → flag mismatches → approve & save → summary insights |
| **Epic Lineage** | Health scores, mismatch flags, story tree drill-down with Table and Graph views |
| **WAF Reference** | Browse all 8 WAF categories — definitions, decision rules, color codes, and examples |
| **Ground Truth Loop** | Approve correct classifications to continuously improve AI accuracy |

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
| Change | GREEN | Other Blocked Priority |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/ad25343/waf-classifier.git
cd waf-classifier

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your API key
echo "ANTHROPIC_API_KEY=your-key-here" > .env

# 4. Run the server
python app.py

# 5. Open in browser
open http://localhost:8080
```

The app auto-loads WAF definitions and ground truth from `sample-data/` on startup — no manual upload needed.

## Pages

| Route | Page | Purpose |
|-------|------|---------|
| `/` | Home | Landing page with navigation cards and system status |
| `/classify` | Classifier | Chat-based AI classification with epic tagging |
| `/history` | Analytics | Upload → AI verify → Summary → Epic Lineage (3 tabs) |
| `/waf-reference` | WAF Reference | Browse all 8 WAF categories with definitions and decision rules |

## Analytics Workflow

1. **Upload Data** — Select a CSV or Excel file with JIRA stories
2. **AI Review** — Claude classifies every row against the WAF framework in batches of 50 (5 concurrent threads). Files over 200 stories are processed in the background with a live progress bar — the browser never times out.
3. **Review & Approve** — Sortable table shows file tags vs AI recommendations with match/mismatch status. All rows pre-selected; save to history.
4. **Summary** — Portfolio-level charts with percentages: category distribution, color breakdown, Run vs Change, confidence levels, mismatch rate. Click any KPI card to drill down into matching stories.
5. **Epic Lineage** — Health dashboard with scores (0–100), flagged epics needing review, per-epic drill-down in Table or Graph view. KPI cards are clickable to filter by correct/mismatch.

Each upload gets a unique ID. Use the Data Source filter to view analytics for a specific upload or all uploads combined. Previous uploads are listed in the history panel for easy reload.

## Epic Health Scoring

Each epic gets a health score from 0 to 100 based on:

- **Color focus (40%)** — percentage of stories with the dominant WAF color
- **Category focus (30%)** — percentage of stories in the dominant category
- **Color diversity penalty (20%)** — fewer unique colors = healthier
- **Mismatch penalty (10%)** — fewer mismatches = healthier

Epics are flagged as "mixed" if they have 3+ WAF colors or the dominant color is below 60%.

## Security

This application includes the following security controls:

- **Debug mode disabled** in production
- **XSS prevention** — all user-controlled data is HTML-escaped before rendering
- **Safe error responses** — generic messages to client, details logged server-side
- **Pagination cap** — maximum 500 results per page
- **Rate limiting** — bulk upload endpoint allows 5 requests per IP per minute (HTTP 429 on excess)
- **Secure filenames** — uploaded files processed with `werkzeug.utils.secure_filename`
- **No authentication required** — designed for trusted internal networks only. Do not expose to the public internet.

## Tech Stack

- **Backend:** Python Flask
- **AI:** Anthropic Claude API (`claude-sonnet-4-5-20250929`)
- **Frontend:** HTML/CSS/JS + Chart.js 4.4.1 + chartjs-plugin-datalabels
- **Database:** SQLite (`waf_history.db`)
- **Data:** pandas, openpyxl for CSV/Excel processing

## Project Structure

```
waf-classifier/
├── app.py                          # Flask server + all API endpoints
├── .env                            # API key (not committed)
├── requirements.txt                # Python dependencies
├── waf_history.db                  # SQLite DB (auto-created)
├── static/
│   ├── home.html                   # Home landing page
│   ├── index.html                  # Classifier chat UI
│   ├── history.html                # Analytics (3 tabs: Upload Data, Summary, Epic Lineage)
│   └── waf-reference.html          # WAF framework reference guide
├── sample-data/
│   ├── waf-definitions.csv         # WAF framework (8 categories)
│   ├── sample-ground-truth.csv     # 18 calibration examples
│   ├── synthetic-100-clean.csv     # 100-record test set (quick testing)
│   ├── synthetic-100-with-epics.csv  # 100-record answer key
│   ├── synthetic-5000-clean.csv    # 5000-record full test set
│   └── synthetic-5000-with-epics.csv # 5000-record answer key
└── docs/
    ├── PRD_WAF_Classifier.docx     # Product Requirements Document
    ├── User_Guide.docx             # User Guide
    ├── API_Reference.md            # API endpoint reference
    ├── Release_Notes.md            # Version changelog
    ├── Quick_Start.md              # Getting started guide
    └── architecture.mermaid        # System architecture diagram
```

## Sample Data

Two test datasets are included in `sample-data/`:

| File | Records | Purpose |
|------|---------|---------|
| `synthetic-100-clean.csv` | 100 | Quick testing — covers all 28 epics, 8 categories, 6 colors, 15 teams, ~15% mismatches |
| `synthetic-5000-clean.csv` | 5,000 | Full testing — same distribution at scale |

The `-with-epics.csv` variants include answer key columns (Correct WAF Category, Correct WAF Color, Correct Run/Change, Is Mismatch).

## Documentation

- **[PRD](docs/PRD_WAF_Classifier.docx)** — Full product requirements
- **[User Guide](docs/User_Guide.docx)** — Step-by-step usage instructions
- **[API Reference](docs/API_Reference.md)** — All endpoints with request/response specs
- **[Release Notes](docs/Release_Notes.md)** — Version history and changelog
- **[Quick Start](docs/Quick_Start.md)** — 5-minute setup guide

## License

Internal use only.
