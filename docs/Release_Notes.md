# WAF Classifier — Release Notes

---

## v3.1 — March 2026

Architecture refactor, new features, and UX improvements.

### Architecture

- **Modular codebase** — Split the 2,834-line `app.py` monolith into focused modules using Flask Blueprints:
  - `config.py` — Constants, AI backend detection, paths
  - `database.py` — SQLite schema, queries, settings cache
  - `state.py` — Shared in-memory stores
  - `waf_core.py` — WAF categories, normalization, AI client, prompt building
  - `routes/pages.py` — Page routes
  - `routes/classify.py` — Classification API
  - `routes/settings_api.py` — Settings, ground truth, baselines API
  - `routes/analytics.py` — Dashboard, history, export API
  - `routes/verify.py` — Bulk verify API and worker threads
  - `routes/lineage.py` — Epic lineage API
  - `routes/teams.py` — Team report API (new)

### New Features

- **Team Report page** — New `/teams` page with team-focused analytics: KPI cards (total teams, stories, avg mismatch rate, most active team), team cards grid with WAF category distribution bars and epic pill badges, team detail view with Chart.js charts, and a cross-team epic matrix showing shared epics.
- **Per-column search** — All data tables (verify, drilldown, recent, uploads, epic lineage) now have filter inputs below each column header. Type to filter in real-time with 200ms debounce. Works alongside existing sort.
- **Dark/Light mode toggle** — Sun/moon toggle button in the header on every page. Preference saved in localStorage and persists across navigation.

### API Changes

- `GET /api/teams/summary` — Team-level analytics with category/color/confidence breakdowns and cross-team epic matrix
- `GET /api/teams/detail?team=X` — Full story list for a specific team

### UX Improvements

- Teams link added to hamburger nav and home page card grid on all pages
- Column filter inputs styled to match dark and light themes

---

## v3.0 — March 2026

Major feature release: upload management, admin settings, field mapping, and UX overhaul.

### New Features

- **Delete uploaded jobs** — Trash icon on each upload in the History tab. Deletes the upload and all associated classifications with confirmation dialog.
- **Story detail modal** — Click any story row in the verify table or drilldown to see full details in a read-only modal (title, description, file vs AI category, color, confidence, reasoning, team, epic).
- **Admin settings page** — New `/settings` page with 2x2 card layout: WAF Definitions, Ground Truth, Baselines, and Configuration.
- **WAF Definitions management** — View, upload, and replace WAF definitions from Settings. Moved from the Classifier page sidebar.
- **Ground Truth management** — View, edit, add, delete individual ground truth examples from Settings. Upload new ground truth files. Moved from the Classifier page sidebar.
- **Baseline snapshots** — Save current WAF definitions and ground truth as a named baseline. Restore any baseline anytime. A default baseline (from sample-data) is auto-saved on first startup and always available.
- **Configurable batch size** — Sync and async batch sizes stored in SQLite settings table. Configurable from Settings > Configuration.
- **Field mapping on upload** — After uploading a file, a mapping step shows detected columns with auto-suggested mappings. User confirms or adjusts before AI classification begins. Title and Description are required.
- **Fuzzy WAF category matching** — Input categories like "KTLO", "Tech Maintenance", or "reg mandated" are normalized to official WAF category names via substring matching and alias lookup. Ambiguous matches are left for AI to resolve. Normalized values shown with indicator icon.
- **History tab** — Upload history moved from the bottom of Upload Data into its own dedicated tab with a full table (filename, rows, status, date, actions).
- **Missing description flagging** — Stories with no description are still classified but forced to LOW confidence with a note and warning icon.

### UX Improvements

- **Consistent page titles** — Every page now shows a title and subtitle below the header (Analytics, Classify, Epic Lineage, WAF Reference, Settings).
- **Consistent `<title>` tags** — All pages use format `WAF Classifier | Page Name`.
- **Consistent header** — All pages show the same header: W logo + "WAF Classifier" + "Work Alignment Framework — Classify, Analyze, Align".
- **Settings nav link** — Added to hamburger menu and home page card grid on all pages.
- **Classifier page cleaned up** — WAF Definition and Ground Truth upload sections removed from sidebar. Replaced with compact status display linking to Settings.
- **All uploads now async** — Removed the sync processing path (≤200 stories). All uploads go through async with real progress bar regardless of file size.
- **Progress bar on all uploads** — No more stuck 0% for small files. Progress updates as each batch completes.
- **Upload area hides during processing** — Prevents starting a second upload while one is running.
- **Scroll to top** — Page scrolls to top when transitioning between mapping, progress, and review steps.
- **macOS Apple Silicon fix** — Added `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` to prevent Python threading crash on M1/M2 Macs.

### API Changes

- `DELETE /api/history/uploads/<id>` — Delete an upload and its classifications
- `GET /api/settings` — Return all settings
- `PUT /api/settings` — Update settings with validation
- `GET /settings` — Settings page
- `POST /api/bulk-verify/preview` — Upload file and return column info for field mapping
- `POST /api/bulk-verify` — Now accepts optional `preview_id` + `column_mappings` for mapped uploads
- `GET /api/classifications/<id>` — Return full details for a single classification
- `GET /api/ground-truth` — Return all ground truth examples
- `PUT /api/ground-truth/<idx>` — Update a ground truth example
- `POST /api/ground-truth/add` — Add a new ground truth example
- `DELETE /api/ground-truth/<idx>` — Delete a ground truth example
- `POST /api/baseline/save` — Save current state as baseline
- `GET /api/baseline/list` — List all baselines
- `POST /api/baseline/restore` — Restore a baseline

### File Changes

- Renamed sample data files for clarity: `synthetic-100-clean.csv` → `synthetic-100-stories.csv`, `synthetic-100-with-epics.csv` → `synthetic-100-answer-key.csv` (same for 5000-record sets)

---

## v2.3 — March 2026

UX polish and upload history improvements.

### New Features

- **Upload history badges** — Every upload in the history panel now shows a colour-coded status badge: ✓ Saved (N) in green, ⚠ Not Saved in amber, or No Results in grey. Badge is determined by counting actual saved classifications, not the unreliable `imported_count` field.
- **Save Now button** — Uploads marked ⚠ Not Saved show a persistent "Save Now" button (always visible, no hover required) that opens the AI results review table immediately.
- **Sticky save bar** — A bar pinned to the bottom of the viewport appears whenever the review table is open, showing the selected count and Save button regardless of scroll position.
- **AWS Bedrock fallback** — When `ANTHROPIC_API_KEY` is absent from `.env`, the classifier automatically falls back to AWS Bedrock using `AnthropicBedrock`. AWS credentials are read from environment variables or `~/.aws/credentials`. Override the model ID with `BEDROCK_MODEL_ID`.
- **Results stored for recovery** — Bulk-verify results are now persisted in `upload_history.results_json` immediately after AI processing, before the user clicks Save. Uploads processed but not saved appear as ⚠ Not Saved and can be recovered by clicking "Save Now".

### Fixes & Improvements

- **Recent Classifications table** — Story, Category, and Color columns were blank due to a field name mismatch between the API (`title`, `category`, `color`) and the renderer (`story_title`, `waf_category`, `waf_color`). Fixed.
- **Summary empty state now refreshes Recent table** — Previously, when filtering to an upload with 0 classifications, the Recent table would show stale data from the previous selection. It now correctly clears and shows "0 stories".
- **Data Source dropdown — saved uploads only** — The filter dropdown now excludes uploads with no saved classifications. Each entry shows the exact saved count and time (e.g. "100 saved — 3/9/2026 2:53 PM") so duplicate filenames are distinguishable.
- **Data Source dropdown navigates to Summary** — Selecting any option automatically switches to the Summary tab.
- **Saved uploads navigate to Summary** — Clicking a ✓ Saved entry in the Upload History panel goes directly to Summary rather than the Upload tab.
- **Save-after-restore bug** — Restoring a previous upload set the wrong JavaScript variable (`currentUploadId` instead of `verifyUploadId`), causing saves to silently use the wrong upload ID. Fixed.
- **Status element ID fix** — Restore status message referenced a non-existent element (`upload-status`); corrected to `import-status`.
- **AI_MODEL global** — All hardcoded `model="claude-sonnet-4-5-20250929"` strings replaced with a single `AI_MODEL` global set at startup, making model changes a one-line edit.
- **Startup banner** — Now shows which AI backend is active: Anthropic API or AWS Bedrock with region and model ID.

---

## v2.2 — March 2026

Security hardening release. No breaking changes.

### Security Fixes

- **Debug mode disabled** — Flask debug mode was turned off, closing the interactive code execution endpoint
- **XSS prevention** — Added `esc()` HTML-escaping helper applied to all user-controlled data rendered into the page (story titles, epic names, feature names, filenames, categories, AI reasoning, WAF colors). Prevents injection via JIRA story content.
- **Safe error responses** — All API error messages now return generic user-friendly text. Full exception details are logged server-side only, no longer exposed to the browser.
- **per_page cap** — Pagination endpoints now enforce a maximum of 500 results per page, preventing memory exhaustion from oversized requests.
- **Bulk-verify rate limiting** — `/api/bulk-verify` now enforces a limit of 5 upload jobs per IP address per minute, returning HTTP 429 if exceeded. Protects against Claude API cost abuse.

---

## v2.1 — March 2026

Consolidation release. Clarifies the three pillars: Classify, Analytics, Lineage.

### New Features

- **Async bulk processing with progress bar** — Files with more than 200 stories are now processed asynchronously in the background. A live progress bar with rotating status messages keeps users informed. The browser polls every 2 seconds and never times out.
- **Faster bulk classification** — Batch size increased from 25 to 50 stories per batch, with 5 concurrent API threads. Processing time for 5,000 stories reduced from ~15 minutes to ~3–4 minutes.
- **Chart percentages** — Category distribution and doughnut charts now display percentages directly on the chart (not just on hover). Built with chartjs-plugin-datalabels.
- **Clickable Summary KPI cards** — Mismatches, Correct, Categories, Colors, Confidence, and Run/Change cards open a drill-down table showing individual matching stories. Sortable columns, with pagination at the top.
- **Clickable Epic Lineage KPI cards** — Stories, Correct, and Mismatches KPI cards in epic detail mode now filter the story list in-place.
- **Epic Lineage Table and Graph views** — Two view modes for the story list: Table View (sortable data grid) and Graph View (expandable tree: Epic → Feature → Story).
- **Mismatch visibility improved** — Mismatched rows use a stronger red background tint. Tree view shows File Tag with red strikethrough → AI Category in green.
- **Data source dropdown resets lineage** — Changing the upload filter now resets Epic Lineage to the overview panel.
- **Upload history panel** — Previous uploads listed with row counts and timestamps; click any entry to reload its data without re-uploading.

### Changes

- **Analytics is now upload-first** — The Upload Data tab is the default entry point.
- **Merged Dashboard into Analytics** — KPI cards, distribution charts, daily trend, and recent table are now the "Summary" tab.
- **Analytics page has 5 tabs** — Upload Data (default), Summary, Sprint Trends, Monthly Rollups, Timeline
- **Post-save flow** — After saving verified data, insights auto-refresh and the page navigates to Summary.
- **Existing data indicator** — Upload tab shows count of verified records already in the database.
- **WAF Reference page** — New `/waf-reference` page shows all 8 categories with definitions, decision rules, color codes, and examples.
- **New API endpoint** — `GET /api/waf-definitions` returns structured WAF framework data.
- **New API endpoint** — `GET /api/dashboard/stories` supports filtered, paginated drill-down of story records.
- **New API endpoints** — `POST /api/bulk-verify/status/<job_id>` for async job polling; `GET /api/history/uploads` and related reload endpoints.

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
- AI classifies every story in batches
- Side-by-side review: original tag vs AI recommendation
- Select all / deselect all / select mismatches only
- Save selected classifications to history database
- Auto-detects epic and parent feature columns

**Epic Lineage Tracking**
- Searchable epic list with story counts
- Overview mode: epic summary table sorted by mismatch count
- Detail mode: 5 KPIs, category bar chart, Run/Change doughnut, expandable tree
- Table View and Graph View for story-level detail
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
