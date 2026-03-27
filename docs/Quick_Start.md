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
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your-api-key-here
```

## Start the Server

```bash
python app.py
```

Open **http://localhost:8080** in your browser. You should see the home page with green status indicators for API, WAF, and Ground Truth.

---

## Your First Classification

1. Click **Classify Stories** from the home page
2. Optionally enter a **Story Key** (e.g. `PROJ-123`), **Epic**, and **Parent Feature** in the fields above the chat box — these are saved alongside the classification for lineage tracking
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
3. **Map Columns** — Auto-detected column mappings shown for confirmation. Adjust if needed. Title and Description are required. Optional: Team, Epic, Parent Feature, Story ID, Feature ID, Epic ID.
4. Click **Continue to AI Classification** — live progress bar tracks each batch
5. **Review & Approve** — side-by-side table shows file tag vs AI recommendation. Mismatches are highlighted and pre-selected. Match rows are included but not pre-selected.
6. Click any row to see full story details in a modal
7. Click **Save Selected** to persist to the database
8. After saving, you're taken to the **Summary** tab to explore insights

**History tab** — view, reload, or delete previous uploads at any time.

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
- **Save baselines.** Go to **Settings > Baselines** to snapshot your WAF definitions and ground truth. Restore anytime.

---

## File Formats

| Format | Extensions | Use for |
|--------|-----------|---------|
| CSV | .csv | All imports and exports |
| Excel | .xlsx | All imports; formatted export (3 sheets) |
| JSON | .json | WAF definitions only |
| Text | .txt | WAF definitions only |

**Column names recognized during bulk import:**

| Field | Recognized headers |
|-------|-------------------|
| Title | title, summary, story name, story title, name |
| Description | desc, description, detail, acceptance, body |
| WAF Category | category, waf cat, waf category |
| Team | team, squad, group |
| Epic | epic, initiative, program |
| Parent Feature | feature, parent feature, capability |
| Story ID | issue key, story id, key, ticket, jira id |
| Feature ID | feature id, feature key, parent id |
| Epic ID | epic id, epic key, epic link, initiative id |

---

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
