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

## Your First Classification

1. Click **Classify Stories** from the home page
2. Type a story in the chat box, for example:

   > Classify this story: "Fix production database connection pool exhaustion causing 504 errors on loan lookup service during peak hours"

3. The AI returns a recommendation with category, color, confidence, and reasoning
4. If it's correct, click **Approve** to save it as ground truth

## Try Mismatch Detection

Include the current WAF tag to see if it's correct:

> This story is currently tagged as "New Feature": Remediate audit finding on insufficient access control logging for admin actions

The AI will flag this as a mismatch and explain why.

## Explore the Dashboard

Click **Dashboard** to see real-time KPIs and charts. The dashboard shows classification volume, approval rates, mismatch counts, and category distributions. It auto-refreshes every 30 seconds.

## Bulk Verify Existing Data

1. Go to **Historical View** and click the **Verify & Import** tab
2. Upload a CSV or Excel file with columns: title, description, current WAF tag
3. The AI classifies every story and shows a side-by-side comparison
4. Select the rows you want to keep and click **Save Selected**

## Track Epic Lineage

1. When classifying stories, enter the **Epic** and **Parent Feature** in the fields above the chat input
2. Go to **Epic Lineage** to see how stories roll up through features to epics
3. Click any epic to see its WAF breakdown with charts and an expandable tree

## Tips for Best Results

- **More ground truth = better accuracy.** Approve correct classifications to grow your training data. Aim for 5+ examples per WAF category.
- **Include full context.** Paste story titles AND descriptions, not just titles.
- **Always include current tags.** Mismatch detection is the most valuable feature for catching errors.
- **Use bulk verify quarterly.** Upload your JIRA sprint backlog exports to catch misclassifications across the portfolio.

## File Formats for Upload

Any of these work for WAF definitions, ground truth, or bulk imports:

| Format | Extensions |
|--------|-----------|
| CSV | .csv |
| Excel | .xlsx |
| JSON | .json (WAF definitions only) |
| Text | .txt (WAF definitions only) |

For bulk imports, include columns named: `title` (or `story_title`), `description`, `waf_tag` (or `category`). Optional columns: `epic`, `parent_feature` (or `feature`).

## Need Help?

- **[User Guide](User_Guide.docx)** — Full step-by-step documentation
- **[API Reference](API_Reference.md)** — All endpoint specs
- **[PRD](PRD_WAF_Classifier.docx)** — Product requirements and architecture
