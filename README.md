# WAF Category Classifier

AI-powered tool for classifying JIRA stories into your organization's Work Alignment Framework (WAF) categories. Built with Flask and Anthropic's Claude AI.

## The Problem

Scrum teams consistently misclassify stories against the 8-category WAF framework. Over 80% of stories lack proper WAF tags, making portfolio-level investment reporting unreliable. This tool fixes that.

## Features

| Feature | Description |
|---------|-------------|
| **AI Classifier** | Chat-based single and batch story classification with mismatch detection |
| **Real-Time Dashboard** | KPI cards, category/confidence/color charts, daily trend, recent activity |
| **Historical Analytics** | Sprint trends (2-week windows), monthly rollups, filterable timeline |
| **Bulk Verify & Import** | Upload JIRA exports, AI verifies each story, side-by-side review before saving |
| **Epic Lineage** | Map stories → features → epics with tree view and per-epic WAF dashboards |
| **Excel Export** | Formatted 3-sheet workbook (Summary, Monthly Rollups, Raw Data) |
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
| `/dashboard` | Dashboard | Real-time KPIs and charts |
| `/history` | Historical View | Sprint trends, monthly rollups, timeline, verify & import |
| `/lineage` | Epic Lineage | Epic-to-story tree view and WAF rollup analytics |

## Tech Stack

- **Backend:** Python Flask
- **AI:** Anthropic Claude API (`claude-sonnet-4-5-20250929`)
- **Frontend:** HTML/CSS/JS + Chart.js 4.4.1
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
│   ├── dashboard.html              # Real-time dashboard
│   ├── history.html                # Historical analytics (4 tabs)
│   └── lineage.html                # Epic lineage tracking
├── sample-data/
│   ├── waf-definitions.csv         # WAF framework (8 categories)
│   ├── sample-ground-truth.csv     # 18 calibration examples
│   └── synthetic-stories-classified.csv
└── docs/
    ├── PRD_WAF_Classifier.docx     # Product Requirements Document
    ├── User_Guide.docx             # User Guide
    ├── API_Reference.md            # API endpoint reference
    ├── Release_Notes.md            # Version changelog
    ├── Quick_Start.md              # Getting started guide
    └── architecture.mermaid        # System architecture diagram
```

## Documentation

- **[PRD](docs/PRD_WAF_Classifier.docx)** — Full product requirements
- **[User Guide](docs/User_Guide.docx)** — Step-by-step usage instructions
- **[API Reference](docs/API_Reference.md)** — All endpoints with request/response specs
- **[Release Notes](docs/Release_Notes.md)** — Version history and changelog
- **[Quick Start](docs/Quick_Start.md)** — 5-minute setup guide

## License

Internal use only.
