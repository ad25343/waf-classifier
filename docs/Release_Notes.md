# WAF Classifier — Release Notes

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
