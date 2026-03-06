# WAF Classifier — Release Notes

---

## v2.1 — March 2026

Consolidation release merging Dashboard and Historical View into a single Analytics page.

### Changes

- **Merged Dashboard into Analytics**: The standalone Dashboard page is retired. Its KPI cards, distribution charts (category, confidence, Run/Change, color), daily trend line, and recent classifications table are now the default "Summary" tab in the Analytics page.
- **Analytics page now has 5 tabs**: Summary, Sprint Trends, Monthly Rollups, Timeline, Verify & Import
- **Home page updated**: 4 menu cards (Classify, Analytics, Epic Lineage, Verify & Import) in a 2x2 grid
- **Navigation simplified**: "Dashboard" and "History" links replaced with single "Analytics" link across all pages
- `/dashboard` route now redirects to `/history` for backward compatibility

---

## v2.0 — March 2026

Major release expanding the platform from a single-page classifier into a full WAF management suite.

### New Features

**Home Landing Page**
- Central navigation hub with 5 feature cards
- System status bar showing API, WAF, Ground Truth, and History DB status

**Real-Time Dashboard**
- 4 KPI cards: Total Classifications, Approved (with rate), Mismatches, Ground Truth count
- WAF Category Distribution horizontal bar chart
- Confidence, Run/Change, and Color distribution doughnut charts
- Daily classification activity trend line
- Recent classifications table with auto-refresh (30s)

**Historical Analytics — Sprint Trends**
- 2-week sprint windows aligned to Mondays
- Sprint pill selector for navigation
- KPI cards with delta indicators vs previous sprint
- Volume, mismatch, category, and Run/Change charts per sprint

**Historical Analytics — Monthly Rollups**
- Dual-axis overview chart (volume bars + mismatch trend line)
- Expandable month cards with category distribution
- Period-over-period comparison
- CSV and Excel export

**Historical Analytics — Filterable Timeline**
- Filter by date range, category, color, team, confidence, mismatch-only
- Paginated results table
- CSV export and formatted Excel export (3 sheets with conditional formatting)

**Bulk Verify & Import**
- Upload JIRA exports (CSV or Excel)
- AI classifies every story in batches of 10
- Side-by-side review: original tag vs AI recommendation
- Select all / deselect all / select mismatches only
- Save selected classifications to history database
- Auto-detects epic and parent feature columns

**Epic Lineage Tracking**
- Searchable epic list with story counts
- Overview mode: epic summary cards with WAF rollup stats
- Detail mode: 5 KPIs, category bar chart, Run/Change doughnut, expandable tree
- Tree view: Epic → Parent Features → Stories with color dots and badges
- Autocomplete epic/feature tagging from the classifier
- Bulk epic assignment API
- File import auto-detects epic/feature columns

**Data Persistence**
- SQLite database for all classification history
- Schema migration for seamless upgrades
- Approve-to-ground-truth feedback loop

### Enhancements

- Navigation bar across all pages (Home, Classifier, Dashboard, History, Lineage)
- Epic and parent feature fields added to classifier with autocomplete
- Formatted Excel export with Summary, Monthly Rollups, and Raw Data sheets
- Conditional formatting in exports (green = approved, red = mismatch)

---

## v1.0 — March 2026

Initial release.

### Features

- Chat-based AI story classifier using Anthropic Claude API
- Single story and batch classification modes
- WAF definitions upload (CSV, Excel, JSON, text)
- Ground truth calibration with file upload
- Mismatch detection when current WAF tag differs from AI recommendation
- Auto-load WAF definitions and ground truth from sample-data/ on startup
- Approve button to save correct classifications as ground truth
- 18 bundled ground truth examples
- Flask web server on port 8080
