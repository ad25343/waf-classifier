# WAF Classifier — Quick Start Guide

Get up and running in under 5 minutes.

---

## Prerequisites

- Python 3.9+
- An Anthropic API key ([get one here](https://console.anthropic.com/))

## Setup

```bash
git clone https://github.com/ad25343/waf-classifier.git
cd waf-classifier
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` — at minimum set your API key:

```
ANTHROPIC_API_KEY=your-api-key-here
```

All supported environment variables are documented in `.env.example`.

## Start the Server

```bash
python app.py
```

Open **http://localhost:8080** in your browser. You should see the home page with green status indicators for API, WAF, and Ground Truth.

---

## Your First Classification

1. Click **Classify Stories** from the home page
2. Optionally enter a **Story Key** (e.g. `PROJ-123`), **Points**, **Epic**, and **Parent Feature** in the fields above the chat box — these are saved alongside the classification for lineage tracking
3. Type a story in the chat box, for example:

   > Classify this story: "Fix production database connection pool exhaustion causing 504 errors on loan lookup service during peak hours"

4. The AI returns a recommendation with category, color, confidence, and reasoning
5. To flag a mismatch, include the current tag in your message:

   > This story is currently tagged as "New Feature": Remediate audit finding on insufficient access control logging for admin actions

6. If you see a mismatch and the AI recommendation is correct, click **Approve & Save to Ground Truth**

---

## Analyze Historical JIRA Data

1. Click **Analytics** from the home page
2. **Upload Data tab** (default) — Upload a CSV or Excel file with story data
3. **Map Columns** — Auto-detected column mappings shown for confirmation. Adjust if needed. Title and Description are required. Optional: Team, Epic, Parent Feature, Story ID, Feature ID, Epic ID, Story Points.
4. Click **Continue to AI Classification** — live progress bar tracks each batch
5. **Review & Approve** — side-by-side table shows file tag vs AI recommendation. Mismatches are highlighted and pre-selected. Match rows are included but not pre-selected.
6. Click any row to see full story details in a modal
7. Click **Save Selected** to persist to the database
8. After saving, you're taken to the **Summary** tab to explore insights

**History tab** — view, reload, or delete previous uploads at any time.

---

## Merge JIRA Export Files

If your JIRA data comes as separate Epic, Feature, and Story export files:

1. Go to **File Merger** from the nav or home page
2. Upload your three files:
   - **Epic Attributes** — must contain Epic ID (e.g. `Jira SaaS Epic#`) and Summary
   - **Feature Attributes** — must contain Feature ID, Feature Summary, and Parent Epic Number
   - **Story Attributes** — must contain Story #, Story Name, and Parent Feature. Optional: Story Points (auto-detected as "Story Points", "Points", "SP", or "Estimate")
3. Enter a **Job Name** (auto-filled with today's date — edit to something meaningful like `SOX Compliance PI-3`)
4. Click **Process Files** — the app joins the three files and shows a stats summary and 50-row preview. Rows with WAF conflicts (story WAF ≠ feature WAF) are highlighted yellow; rows missing WAF are highlighted red.
5. Click **Submit for Analysis** to send the merged file directly to the AI classifier — you'll land on the column mapping step automatically
6. Alternatively click **Download Merged CSV** to save locally and upload manually later

Sample files for testing are in `test-data/merge-samples/`.

---

## Explore the Teams Page

1. Click **Teams** in the nav bar
2. Select a **Data Source** at the top to filter to a specific upload (or leave as "All Uploads")
3. The left panel shows a tree: Team › Epic › Feature — click any node to load stories on the right
4. The right panel shows a flat, sortable story table. Sort by Title, Category, Color, Confidence, or Status
5. Click **Show Insights** to reveal KPI cards and WAF distribution charts for the selected team
6. Switch to the **By Epic** tab to see which teams share the same epics

---

## Track Epic Lineage

1. Go to **Epic Lineage** from the nav
2. Select a **Data Source** to filter by upload, or view all uploads combined
3. Click any epic in the left panel to see its WAF breakdown — KPI cards, category chart, Run/Change chart
4. The **Story Lineage** section shows stories grouped by feature with expand/collapse
5. Use the **Sort** buttons (Title, Category, Color, Confidence, Status) to reorder stories within each feature section
6. Use the **Search** box to filter stories by title, category, or confidence

---

## Search Across All Classifications

Use the **search bar in the nav** (on Home, Classify, Dashboard, Settings, and WAF Reference pages) to find any story across all uploads. Results show:
- Highlighted matching title
- Breadcrumb: team › epic › feature
- WAF category, color, confidence, and mismatch/match status
- Source upload filename and date

Click any result to navigate to that team's detail view.

---

## Score Story Quality

The Story Quality tab in Analytics scores your uploaded stories against the Definition of Ready (DoR) rubric from the GSE-MF Story Excellence Playbook.

1. Go to **Analytics** and select a specific upload from the **Data Source** dropdown at the top
2. Click the **Story Quality** tab
3. Optionally filter to specific teams using the Teams dropdown (all teams selected by default)
4. Click **Score Stories** — the app AI-scores every story in the background
5. Results appear with KPI cards (Ready / Needs Work / Not Ready) and a per-story table
6. Click any story row to expand it and see pass/fail for all 9 criteria with fix suggestions
7. Click **✍ Suggest Rewrite** on any story to open the rewrite chat:
   - The AI drafts a complete rewrite using only the original story content
   - `[REQUIRED: ...]` placeholders mark information the team must supply
   - Type follow-up messages to iterate: *"The source table is dw.loan_performance"* or *"Tighten AC2"*
   - Click **Copy latest** to paste the current version into JIRA
   - Keep iterating until the story is sprint-ready
8. Click **⬇ Export CSV** to download scores for all stories in the current view

**Scoring Run History** (bottom of the tab) lists every past run. Click **Load** to replay any run's results, or **Delete** to remove it.

**Scoring thresholds:**
| Status | Criteria met |
|--------|-------------|
| Ready | 8–9 of 9 (≥ 89%) |
| Needs Work | 5–7 of 9 (56–88%) |
| Not Ready | < 5 of 9 (< 56%) |

> **Note:** Restart the app (`python app.py`) after first install to ensure the quality scoring tables are created. New scoring runs will not appear in history until after a restart.

---

## Manage WAF Definitions and Ground Truth Versions

The **Version Library** in Settings lets you save named snapshots of your WAF Definitions and Ground Truth so you can experiment without losing your calibrated baselines.

**Saving a version:**
1. Go to **Settings** and click **Save WAF Version** or **Save GT Version**
2. Enter a **Version Name** (e.g. `Q2 Calibration`), your **Author** name, and optional **Notes**
3. Click **Save** — the version is stored in `baselines/waf/` or `baselines/gt/`

**Editing WAF Definitions inline:**
1. Click **View / Edit** on the WAF Definitions card
2. Edit any cell directly — Category (text), Color (dropdown), Run/Change (dropdown), Description (textarea)
3. An amber **Unsaved Changes** banner appears on first edit:
   - **Apply Changes** — updates the in-memory store immediately; takes effect on next classification
   - **Save as New Version** — applies edits and opens the Version Library modal (pre-named with today's date)
   - **Discard** — reloads from server, rolling back all changes

**After editing Ground Truth rows** a green nudge banner appears offering "Save as New Version" — click it to snapshot the current GT state before the changes get buried.

**Selecting a version per run:**
- On the **Classify** page: "Using:" dropdowns above the chat box let you pick a WAF Version and GT Version for that session
- On the **Analytics Upload** tab: "Classification Settings" card has the same dropdowns — pick a version before clicking "Continue to AI Classification"
- Both default to the active/Default Baseline; omit to use whatever is globally loaded

## Dark / Light Mode

Click the **moon/sun icon** in the top-right nav bar to toggle between dark and light mode. Your preference is saved across page navigation and browser sessions.

---

## Test Data

The `test-data/` folder contains synthetic datasets for testing and exploration:

| File | Stories | Focus | Mismatch Rate |
|------|---------|-------|---------------|
| `compliance-focus-60.csv` | 60 | Regulatory, audit, compliance — 5 teams | 30% |
| `platform-engineering-80.csv` | 80 | Cloud, DevOps, SRE — 5 teams, cross-team epics | 15% |
| `multi-team-product-120.csv` | 120 | Mixed product + tech — 8 teams, all epics cross-team | 20% |
| `synthetic-100-stories.csv` | 100 | General mixed — original test file | varies |
| `synthetic-5000-stories.csv` | 5000 | Large dataset for performance testing | varies |
| `sample-ground-truth.csv` | — | Load via Settings → Ground Truth | — |
| `ground-truth-maintenance.csv` | — | Extended ground truth set | — |
| `waf-definitions.csv` | — | Load via Settings → WAF Definitions | — |

Re-generate or modify test datasets using `test-data/generate_test_data.py`.

---

## Tips for Best Results

- **More ground truth = better accuracy.** Approve correct classifications to grow your training data. Aim for 5+ examples per WAF category.
- **Include full context.** Paste story titles AND descriptions, not just titles.
- **Always include current tags.** Mismatch detection is the most valuable feature for catching errors.
- **Use bulk verify quarterly.** Upload your JIRA sprint backlog exports to catch misclassifications across the portfolio.
- **Include ID columns.** Add `Issue key`, `Epic Link`, or `Feature ID` columns to your CSV/Excel file to track story IDs through the app.
- **Select a specific upload.** Use the Data Source dropdown on Teams and Lineage pages to scope all views to a single upload batch. Dates shown in the dropdown (e.g. 3/27/2026) help distinguish multiple uploads of the same file.
- **Use the Teams page for portfolio reviews.** Filter to a specific upload, then drill into each team's story table to review classifications before sharing.
- **Save versions.** After calibrating WAF Definitions or Ground Truth, use **Settings > Save WAF Version / Save GT Version** to snapshot the state. You can restore any version by activating it, or pick a specific version per upload run without changing the global active.

---

## File Formats

| Format | Extensions | Use for |
|--------|-----------|---------|
| CSV | .csv | All imports and exports |
| Excel | .xlsx | All imports; formatted export (3 sheets) |
| JSON | .json | WAF definitions only |
| Text | .txt | WAF definitions only |

**Recommended column order** (matches test data files):

```
Epic ID · Feature ID · Story ID · Epic · Parent Feature · Story Title · Story Description · Story Points · Team · WAF Category · WAF Color · Sub-Category · Confidence · Run/Change · Timestamp · Issue Key
```

**Column names recognized during bulk import:**

| Field | Recognized headers | Notes |
|-------|--------------------|-------|
| Epic ID | epic id, epic key, epic link, initiative id | e.g. EP-C001 |
| Feature ID | feature id, feature key, parent id | e.g. F-C001 |
| Story ID | **Story ID** (priority), issue key, key, ticket, jira id | `Story ID` wins when both present |
| Epic | epic, initiative, program | Epic name |
| Parent Feature | feature, parent feature, capability | Feature name |
| Story Title | **Story Title** (priority), title, summary, story, name | **Required** |
| Story Description | **Story Description** (priority), description, desc, detail, body, acceptance | |
| Team | team, squad, group | |
| WAF Category | category, waf cat, waf category | |
| Story Points | story points, points, sp, estimate | Numeric; shown in verify table and lineage |
| Issue Key | — (fallback for Story ID only) | e.g. PROJ-123 |

---

## Deploying Under a Sub-Path

If the app is served behind a reverse proxy at a URL prefix (e.g. `https://yourserver.com/h591-wafui/`), set one variable in `.env`:

```
APPLICATION_ROOT=/h591-wafui
```

Leave it blank (or omit it) for root-path / local development. No other changes are needed — the app patches all internal links and API calls at runtime.

## AWS Bedrock (Alternative AI Backend)

If you don't have an Anthropic API key, the app automatically falls back to AWS Bedrock:

```
# No ANTHROPIC_API_KEY needed — uses ~/.aws/credentials or environment variables
BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-6-v1  # optional override
```

---

## Rate Limits

The bulk upload endpoint allows 5 uploads per IP address per minute. For large-scale testing, space out your uploads or adjust the limit in **Settings > Configuration**.

---

## Need Help?

- **[API Reference](API_Reference.md)** — All endpoint specs with request/response examples
- **[Release Notes](Release_Notes.md)** — What's new in each version
