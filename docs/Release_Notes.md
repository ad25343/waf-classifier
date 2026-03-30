# WAF Classifier — Release Notes

---

## v3.2.2 — March 2026

Auto-load WAF/GT on startup, status bar on all pages, upload screen UX fixes, Story ID hint fix.

### Bug Fixes

- **WAF and GT reset on server restart** — Both were stored in memory only. Server restart wiped them. Now the active file path is persisted to the `settings` table on upload and auto-reloaded on every startup. No manual re-upload needed after restart.
- **Auto-load pointed at deleted `sample-data/` folder** — `auto_load_sample_data()` in `app.py` referenced `sample-data/` which was removed when files were consolidated into `test-data/`. Updated to check DB for user-uploaded paths first, fall back to `test-data/`.
- **Story ID hint showed incorrect example** — Hint incorrectly suggested `12345` (numeric) as a valid Story ID format. Story ID follows the same `PROJ-123` alphanumeric format as Issue Key. Fixed hint to `e.g. Story ID, Issue Key, Ticket (e.g. PROJ-123)`.
- **"Continue to AI Classification" and "Re-upload" buttons buried** — These action buttons appeared below the column mapping grid and sample preview, requiring users to scroll. Moved to the top-right of the mapping step header, always visible.

### New Features

- **Status bar on all pages** — System health pills (API Connected, WAF, GT, History record count) previously only appeared on the Home page. Now shown on all pages below the nav bar. Each pill is a clickable link — WAF and GT link to Settings, History links to Analytics.
- **`set_setting()` added to `database.py`** — Companion to `get_setting()`. Writes a key/value to the `settings` table and updates the in-memory cache.

---

## v3.2.1 — March 2026

Bug fixes, upload filter reliability, and test data expansion.

### Bug Fixes

- **Teams upload filter date bug** — Data Source dropdown was using `created_at` (non-existent field) instead of `uploaded_at`. All dates showed "(Invalid Date)", making multiple uploads of the same file indistinguishable and causing users to stay on "All Uploads (combined)" view without realising it. Fixed to `uploaded_at`.
- **DB migration not applied** — `story_id`, `feature_id`, `epic_id` columns were defined in `database.py` but not yet present in existing databases. Migration now applied on server start; also applied retroactively via direct SQL for running instances.
- **Teams detail endpoint returning unfiltered data** — When the server hadn't been restarted after code changes, the old `teams_detail` handler (without `upload_id` filter) remained active. Resolved by restarting the server to pick up all route changes from v3.2.

### New Features

- **Story Key input on single-story classifier** — `Story Key (e.g. PROJ-123)` input field added to the chat input area alongside Epic and Parent Feature. Saved to `story_id` in the database. Wired through `POST /api/classify`.
- **Expected File Format table updated** — History page upload section now lists `Story ID / Issue Key`, `Feature ID`, and `Epic ID` as optional columns with descriptions.

### Test Data

- **3 new synthetic datasets** added to `test-data/`:
  - `compliance-focus-60.csv` — 60 stories, 5 teams, financial compliance/regulatory focus, 30% mismatch rate
  - `platform-engineering-80.csv` — 80 stories, 5 teams, cloud/DevOps/SRE focus, 15% mismatch rate, cross-team epics
  - `multi-team-product-120.csv` — 120 stories, 8 teams, mixed product/tech, 20% mismatch rate, all epics cross-team, 10 empty-description edge cases
- **`sample-data/` folder merged into `test-data/`** — single location for all test files
- **Redundant files removed**: `synthetic-100-answer-key.csv`, `synthetic-5000-answer-key.csv`, `synthetic-stories-classified.csv`, `synthetic-stories-classified-clean.csv`, `synthetic-stories-raw.csv`
- **`generate_test_data.py`** saved in `test-data/` for future dataset regeneration or modification

---

## v3.2 — March 2026

UX overhaul, global search, team analytics redesign, and data model improvements.

### New Features

- **Global full-text search** — FTS5-powered search across all classifications. Search bar in the nav on Home, Classify, Dashboard, Settings, and WAF Reference pages. Results show highlighted title, breadcrumb (team › epic › feature), WAF badges, and upload source. Powered by SQLite FTS5 with BM25 relevance ranking and prefix matching on the last token.
- **Story / Feature / Epic IDs** — Three new optional ID fields (`story_id`, `feature_id`, `epic_id`) on every classification. Auto-detected from common column names in uploaded files (e.g. `Issue key`, `Epic Link`, `Feature ID`). Displayed as small tags in Teams and Lineage story views. Blank when not provided.

### Teams Page Redesign

- **Two-panel layout** — Left panel: collapsible tree nav (Team › Epic › Feature). Right panel: flat, sortable story table. Clicking any node in the tree populates the right panel. Matches the navigation model of tools like Jira/Linear.
- **Insights on demand** — KPI cards and charts are hidden by default. Revealed via "Show Insights" toggle. Keeps the story table immediately visible on load.
- **Job/upload dropdown** — Data Source selector at the top of the Teams page filters all team data to a specific upload batch.
- **Story table sort** — All 5 columns sortable (Title, Category, Color, Confidence, Status). Click to sort ascending; click again to reverse. Sort indicator shown on active column.
- **Story search** — Per-team story filter on the right panel.

### UX Improvements

- **Right-aligned nav** — Top navigation links right-aligned on all pages. Dark/light mode toggle moved into the nav bar.
- **Approval scoped to mismatches** — `approved` flag is now only set to `true` for mismatch rows when saving from the bulk verify table. Match rows are saved without the approved flag. Verify table pre-selects only mismatch rows by default.
- **Lineage story sort** — Sort controls (Title, Category, Color, Confidence, Status) added to the Story Lineage tree. Sort preserves the open/closed state of feature sections — clicking sort does not collapse the tree.
- **Upload dropdown search removed** — Data Source dropdowns on Analytics and Lineage pages now show the dropdown directly. The "Search uploads..." input above the dropdown was removed.
- **Global search scoped** — Global search bar not shown on History, Teams, or Lineage pages, which have their own per-table filters.

### API Changes

- `GET /api/search` — Full-text search across all classifications. Supports `q`, `upload_id`, and `limit` parameters. Returns context-rich results with team, epic, feature, category, color, confidence, and upload source.
- `/api/bulk-verify/save` — Request rows now carry `story_id`, `feature_id`, `epic_id` fields. These are persisted to the database when provided.
- `/api/teams/detail` — Story objects in response now include `story_id`, `feature_id`, `epic_id`.
- `/api/epics/summary` — Story objects now include `story_id`, `feature_id`, `epic_id`.

### Database

- New columns on `classifications` table: `story_id TEXT DEFAULT ''`, `feature_id TEXT DEFAULT ''`, `epic_id TEXT DEFAULT ''`
- Schema migration runs automatically on startup — no action needed for existing databases

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
- **Dark/Light mode toggle** — Sun/moon toggle button in the nav bar on every page. Preference saved in localStorage and persists across navigation.

### API Changes

- `GET /api/teams/summary` — Team-level analytics with category/color/confidence breakdowns and cross-team epic matrix
- `GET /api/teams/detail?team=X` — Full story list for a specific team
- `GET /api/teams/by-epic?epic=X` — All teams working on a specific epic
- `GET /api/teams/epics-list` — All epics with team and story counts

### UX Improvements

- Teams link added to nav on all pages
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

- Consistent page titles, `<title>` tags, and header on every page
- Settings nav link added to hamburger menu and home page card grid on all pages
- Classifier page WAF Definition and Ground Truth upload sections removed from sidebar; replaced with compact status display linking to Settings
- All uploads now async — removed sync processing path; all uploads go through async with real progress bar regardless of file size
- Progress bar on all uploads — no stuck 0% for small files; updates as each batch completes
- Upload area hides during processing
- Scroll to top when transitioning between mapping, progress, and review steps
- macOS Apple Silicon fix — added `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` to prevent Python threading crash on M1/M2 Macs

### API Changes

- `DELETE /api/history/uploads/<id>` — Delete an upload and its classifications
- `GET /api/settings` — Return all settings
- `PUT /api/settings` — Update settings with validation
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

- Renamed sample data files: `synthetic-100-clean.csv` → `synthetic-100-stories.csv`, `synthetic-100-with-epics.csv` → `synthetic-100-answer-key.csv` (same for 5000-record sets)

---

## v2.3 — March 2026

UX polish and upload history improvements.

### New Features

- **Upload history badges** — Every upload in the history panel now shows a colour-coded status badge: ✓ Saved (N) in green, ⚠ Not Saved in amber, or No Results in grey.
- **Save Now button** — Uploads marked ⚠ Not Saved show a persistent "Save Now" button that opens the AI results review table immediately.
- **Sticky save bar** — A bar pinned to the bottom of the viewport appears whenever the review table is open, showing the selected count and Save button regardless of scroll position.
- **AWS Bedrock fallback** — When `ANTHROPIC_API_KEY` is absent, the classifier automatically falls back to AWS Bedrock using `AnthropicBedrock`. Override the model ID with `BEDROCK_MODEL_ID`.
- **Results stored for recovery** — Bulk-verify results are persisted in `upload_history.results_json` immediately after AI processing, before the user clicks Save.

### Fixes

- Recent Classifications table field name mismatch fixed
- Summary empty state now refreshes Recent table correctly
- Data Source dropdown now excludes uploads with no saved classifications
- Save-after-restore bug fixed (wrong `currentUploadId` variable)
- `AI_MODEL` global replaces all hardcoded model strings

---

## v2.2 — March 2026

Security hardening release. No breaking changes.

### Security Fixes

- **Debug mode disabled** — Flask debug mode turned off
- **XSS prevention** — `esc()` HTML-escaping applied to all user-controlled data
- **Safe error responses** — Generic messages to client; full details logged server-side only
- **Pagination cap** — Maximum 500 results per page
- **Rate limiting** — 5 upload jobs per IP per minute; HTTP 429 on excess

---

## v2.1 — March 2026

Consolidation release: async processing, clickable KPI cards, and Epic Lineage improvements.

### New Features

- **Async bulk processing with progress bar** — Files processed asynchronously in background with live progress updates
- **Faster bulk classification** — 50 stories per batch, 5 concurrent API threads; 5,000 stories in ~3–4 minutes
- **Chart percentages** — Category and doughnut charts display percentages directly on chart
- **Clickable Summary KPI cards** — Open drill-down table of individual matching stories
- **Epic Lineage Table and Graph views** — Sortable table or expandable tree (Epic → Feature → Story)
- **Mismatch visibility improved** — Mismatched rows highlighted; tree view shows File Tag (strikethrough) → AI Category

---

## v2.0 — March 2026

Major release expanding from single-page classifier to full WAF management suite.

### New Features

- Home landing page with system status bar
- Real-time Dashboard with KPI cards, distribution charts, and daily trend
- Historical Analytics: Sprint Trends, Monthly Rollups, Filterable Timeline
- Bulk Verify & Import from JIRA CSV/Excel exports
- Epic Lineage Tracking with health scores and story tree
- SQLite persistence with schema migration support
- CSV and formatted Excel export (3 sheets, conditional formatting)

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
