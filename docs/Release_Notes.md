# WAF Classifier — Release Notes

---

## v3.7.0 — May 2026

Real Story Excellence playbook adopted, composite rubrics with optional domain extensions, in-app domain editor, inline dispute flagging on three more pages, merge feature overhaul, and a Team-of-Teams filter bugfix.

### Story Quality scoring — major rewrite

- **Real playbook in repo.** The fictional `"GSE-MF Story Excellence Playbook v1.0"` attribution that shipped in v3.4.0 has been replaced with the actual *Story Excellence Playbook v2*, now stored at `docs/playbook/story-excellence-v2.docx` (canonical), `docs/playbook/story-excellence-v2.md` (extracted text for diff-friendly PR review), and `docs/playbook/story-excellence-v2.pptx` (18-slide companion deck — Epic / Feature / Story end-to-end). All scoring now traces back to a verifiable source document.

- **MF Story Excellence deck — moved to archive.** An older Multifamily / Data & Reporting variant of the playbook is preserved at `docs/playbook/archive/story-excellence-mf-v1.pptx` for historical reference. It uses an earlier 9-criterion Story DoR with a 2-checkpoint flow (Story-level only — does not cover Epic or Feature). **It is superseded by v2** — slide 1 carries a banner noting this, and the MF deck should not be used as the rubric source for new scoring. MF-specific criteria belong in the **MF Servicing domain extension** (editable via Admin → Domain Editor); the v2 base provides the universal Story / Feature / Epic / Defect rubrics that all stewards build on. The `docs/playbook/` directory now cleanly separates active artifacts (top level) from archived ones (`archive/` subdirectory).
- **Rubrics as data, not code.** The hardcoded `RUBRICS` dict in `routes/quality.py` is gone. Rubrics now live as JSON files under `rubrics/` so editing a criterion no longer requires a code change. Each criterion carries `id`, `name`, `description`, `why`, `fix`, `good_example`, `required`, `weight`, and `scored_by` (`ai` | `system`).
- **Four base level rubrics** (universal across domains):
  - `rubrics/base/story-dor.json` — 7 criteria from playbook §8.3 (replaces the old 9-criterion rubric)
  - `rubrics/base/feature-dor.json` — 7 criteria from §7.2 (new)
  - `rubrics/base/epic-dor.json` — 7 criteria from §6.2 (new)
  - `rubrics/base/defect-dor.json` — 7 criteria, companion rubric (the playbook does not define one)
- **Optional domain extensions.** Stories aren't one-size-fits-all — a Capital Markets story has different DoR concerns than a Data story. New `rubrics/domains/{id}/` layer adds criteria specific to a line of business:
  - `data/` — real content for Data & Reporting (output artifact, DQ checks, lineage)
  - `capmkts/` — starter content for Capital Markets (settlement window, pricing source, counterparty, risk impact)
  - `sf-origination/` — starter content for SF Origination (AUS rule version, TILA/RESPA, lender integration)
  - `mf-servicing/` — starter content for MF Servicing (sub-servicer reach, investor reporting, property type)
  - `risk/` — starter content for Risk & Compliance (regulatory citation, audit log, sign-off chain, effective date)
  - All four non-Data extensions are explicitly marked `is_placeholder: true`. The UI shows an amber **"⚠ Starter content"** banner so reviewers know to customize before relying on scores in production decisions.
- **Composite rubric loader.** Effective rubric = `base ∪ extension`, deduped by criterion id (extension wins on conflict). Stories scored against `story-dor:capmkts` see the 7 universal criteria + 4 CapMkts criteria. Generic / no-domain selection uses base-only.
- **Two-picker UI on `/history` Story Quality tab.** New "Level" dropdown (Story / Feature / Epic / Defect) and optional "Domain" dropdown (Generic / Data / CapMkts / SF / MF / Risk). Selecting a level + domain reloads the rubric reference card with the combined criteria.
- **"What good looks like" surfacing.** When a criterion fails on the expanded story row, both the prescriptive **fix** AND the playbook's **good_example** appear inline — Layer 1 surfacing. The "Suggest Rewrite" button is now labelled "✨ What good looks like for this story" and its modal title matches.
- **Rewrite endpoint cached.** `/api/quality/rewrite` results now cache in-memory by `(classification_id, rubric_id)`. Re-clicks don't re-spend on the AI within a process lifetime. Pass `force=true` to bypass.
- **Scoring strictness configurable per rubric.** New `scoring_mode` field on each rubric (`lenient` | `balanced` | `strict`) branches the AI prompt instruction. Defaults to `balanced` — pass when met or unambiguously inferable, fail when you'd have to assume.
- **Per-rubric thresholds with required-pass rule.** Each rubric carries `thresholds.ready.min_score` and `thresholds.ready.all_required_pass`. A story scoring 86 with a required criterion failing is now correctly **Needs Work**, not **Ready**.
- **Bands flow through the API.** Each scored row carries a `band` field (`ready` / `needs_work` / `not_ready`) computed from the rubric's thresholds. Frontend prefers `band` over score thresholds for filtering.

### Domain Editor (new page)

New `/quality-domains` route — a dedicated screen for domain stewards to review, edit, and reset extension JSON files without touching the filesystem or merging code.

- **Left rail** lists all domains from the manifest with a `starter` badge for placeholder ones.
- **All four level tabs.** Story, Feature, Epic, and Defect are all editable. Epic and Defect criteria are largely domain-neutral in practice but the editor doesn't gatekeep — if a team finds a real domain-specific need at those levels, they can extend.
- **Per-criterion editor cards** with id, name, description, why, fix, "what good looks like", required toggle, weight, and `scored_by` selector. Add / Delete buttons per criterion.
- **Save** writes the JSON, backs up the previous version to `<path>.bak`, and invalidates the in-process rubric cache so changes appear on the Story Quality view's next refresh.
- **Reset to previous** restores from `.bak` (only shown when a backup exists).
- **Create extension** flow scaffolds a fresh JSON shell when a domain × level doesn't have a file yet.
- **Path validation** rejects `..`, `/`, empties, and unknown levels — the editor cannot escape `rubrics/domains/`.

### Inline dispute flagging on three more pages

Until v3.6 you could only file a classification dispute from the single-story Classify page (`/`). After bulk verify or while browsing teams/lineage you had no way to flag a wrong AI classification. Big workflow gap. v3.7 adds a **🚩 Flag classification** button to:

- **History** (`/history`) — story detail overlay header
- **Teams** (`/teams`) — team / epic story detail modal
- **Lineage** (`/lineage`) — epic→feature→story drill-in

A new shared helper `static/dispute-modal.js` is auto-injected on every page by `routes/pages.py`, so any view can call `window.openDisputeModal({...})` with no per-page imports. Posts to the existing `/api/disputes` endpoint — same shape as the form on `/`.

### Merge feature overhaul

- **Per-file mapping cards.** Replaces single auto-detect with three explicit mapping panels (Epic / Feature / Story), one card per uploaded file. Required-field validation is conditional on which files are present.
- **Name-based join.** Feature → Epic and Story → Feature now join by name, not ID. The original Feature ID and Epic ID are still surfaced in the merged output.
- **Status flags + orphan handling.** Per-row status: `complete` (story + feature + epic resolved), `missing_feature`, `missing_epic`. Orphan rows are visible everywhere (preview + downloads) but always excluded from AI analysis. Two informational flags don't block analysis: `_flag_missing_waf` (epic has no WAF) and `_flag_missing_run_change` (epic has no Run/Change tag).
- **Five clickable stat cards.** Total / Complete / Orphans / Missing WAF / Missing R/C — clicking any card filters the preview table to that subset. Legend pills under the table mirror the filters for finer states.
- **Clickable preview rows** open a detail modal showing every field on the merged record + a Reject/Restore button.
- **Two-phase upload flow.** `/api/merge/preview` returns suggested column mappings + sample rows. User confirms or adjusts in the UI, then `/api/merge/process` runs the merge with confirmed mappings. Tokens are full UUIDs with a 1-hour TTL.
- **Two download buttons.** "Download All" (complete + orphans, with Status column) and "Download Orphans" (orphans only, conditionally visible).
- **"Submit Complete for Analysis"** confirmation modal surfaces what's being excluded before AI analysis is requested.
- **Sample data — restructured + completeness pass.** Consolidated all merge fixtures under `test-data/merge-samples/` (the prior `samples/` top-level folder is gone). Three sets now ship side by side, each with `epics.csv`, `features.csv`, `stories.csv`, AND a flattened `consolidated.csv` for the single-file upload path:
  - `jira-realistic/` — 9 epics × 15 features × 31 stories. Realistic Jira-export schema with **complete columns** (Description, WAF Color, Run/Change, Block, Sponsor on epics; Description + WAF Color on features; Description + Story Points on stories). Multi-LoB, with seeded orphans + the 4 alias-test wrenches.
  - `clean-simple/` — 20 epics × 31 features × 76 stories. Simpler 5-column schema with WAF Color encoded as `COLOR - Category`. All joins clean; no orphans.
  - `edge-cases-simple/` — 4 × 8 × 18. Same simple schema, but seeded with orphan stories, orphan features, and malformed rows for testing the orphan-handling UI.
  Each set has a `consolidated.csv` ready for the `/history` upload path. New `test-data/merge-samples/README.md` documents the structure and which set to use for which test scenario.

### Team of Teams — filter bugfix + drill-down UX

- **Bugfix.** The Team-of-Teams filter on the Teams view was occasionally showing data from a "Subcategory" or similar column. Root cause: legacy fallback keywords (`sub-category`, `subcategory`, `waf sub`, `sub_cat`) on the `team_of_teams` field auto-mapper. After the v3.4-era column rename `waf_subcategory → team_of_teams` they should have been removed but weren't. Now strict-match only: `["team of teams", "team_of_teams"]` everywhere (verify, analytics, merge, waf_core).
- **Drill-down UX.** The Teams view used to show ToT dropdown + Team pills side-by-side — crowded. Now a single hierarchical drill: **Step 1** ToT pills (with "All Teams of Teams" option), **Step 2** Team pills filtered to the chosen ToT (with "← All Teams of Teams" back link). When a file has no ToT data, Step 1 is skipped automatically.

### Navigation — Tools → Admin

- The top-nav **Tools** dropdown is renamed to **Admin** to better reflect what lives there: File Merger, WAF Reference, Category Aliases, and the new **Domain Editor**. Settings stays separate (it's actual app configuration). Renamed across all 11 page templates.

### Test data — WAF Sub ghost cleanup

- The synthetic test CSVs (`compliance-focus-60.csv`, `multi-team-product-120.csv`, etc.) emitted a meaningless `Sub-Category` column that previously got auto-mapped into the `team_of_teams` DB column via the now-removed fallback keywords. The generator script no longer outputs that column. Existing CSVs in `test-data/` still have the stale column; they'll regenerate clean next time the script runs.

### API Changes

- `GET  /api/quality/rubric` — accepts `rubric_id` (composite, e.g. `story-dor:data`) OR `level` + `domain`. Legacy `domain=data_reporting` still resolves to `story-dor`. Response includes `rubric` (composed), `available` (level rubrics on disk), and `domains` (manifest entries).
- `POST /api/quality/score`, `GET /api/quality/results`, `GET /api/quality/export`, `POST /api/quality/chat`, `POST /api/quality/rewrite` — all accept `rubric_id` (preferred) or `rubric_id` + `domain` split. Old `domain` field still accepted as a legacy alias.
- `POST /api/quality/rewrite` — new `force: true` flag bypasses the in-memory cache.
- `GET  /api/quality/extension?domain=&level=` — load the JSON of a domain extension for editing.
- `PUT  /api/quality/extension` — save (overwrite) a domain extension. Body: `{ domain, level, extension }`. Backs up the previous file to `<path>.bak`.
- `POST /api/quality/extension/reset` — restore an extension from its `.bak` backup.
- `POST /api/merge/preview` — first phase of the new merge flow. Returns `{token, files: {epic, feature, story: each with uploaded/columns/sample_rows/target_fields/suggested_mappings}, required: {...}}`.
- `POST /api/merge/process` — second phase. Body includes `token` + per-file confirmed mappings.
- `GET  /api/merge/download/<token>` — supports `only_complete` and `only_orphans` query flags.

### Database

No schema changes in v3.7.0. The existing `story_quality_scores.domain` column continues to store rubric ids (now composite, e.g. `story-dor:data`); old rows under `data_reporting` map to `story-dor` via the legacy alias. Future commit may rename the column to `rubric_id` for clarity.

---

## v3.6.0 — April 2026

Classification Disputes workflow, PI Number field, ephemeral Classify page, and expanded trend data.

### New Features

- **Classification Disputes** — Full workflow for flagging AI classifications the user believes are wrong. When the AI returns a classification, a **🚩 Flag as Incorrect** button appears alongside "New Story". Clicking opens an inline form requiring:
  - *Why is this classification incorrect?* — Free-text explanation (minimum 30 characters, required). Guidance text prompts users to be specific about what the AI got wrong and why the evidence points elsewhere.
  - *What should the correct WAF category be?* — Required dropdown populated from the current active WAF definitions (fetched from `/api/status`). Falls back to default categories if the API is unavailable.
  - Validation is inline — submission is blocked until both fields are complete. Error messages appear under each field.
  - On submit, a dispute record is created in the DB with the full AI classification context (category, color, confidence, reasoning) and the user's story text — no re-entry needed.

- **Classification Disputes review page (`/disputes`)** — Dedicated page for reviewers to triage flagged disputes:
  - 4 KPI cards: Pending, Accepted→GT, Dismissed, WAF Flagged
  - Status filter tabs (Pending / All / Accepted / Dismissed / WAF Flagged)
  - Table view: Date, Story, AI Classification, User Explanation, Status, Actions
  - **Resolve modal** — three resolution actions:
    - **Dismiss** — marks dispute resolved, no change to GT or WAF
    - **Accept into GT** — confirm/adjust category and color, saves corrected classification to DB with `approved: true`
    - **Flag for WAF Review** — escalates to WAF definition owners with reviewer notes; marks `waf_flagged: true`
  - Navigation: "Classification Disputes" added to Analyze dropdown on all 9 pages; Disputes card added to home page grid (🚩 red theme, "Reviewers" badge)

- **PI Number field** — Program Increment tag added to the full data stack:
  - New `pi_number TEXT DEFAULT ''` column in `classifications` and `disputes` tables
  - Auto-detected from CSV/Excel columns matching `pi number`, `pi_number`, `pi #`, `program increment`, `pi`
  - Input field on the single-story Classify page (between Story Points and Epic)
  - Displayed as a teal chip in: verify table, story detail modal, all stories table (History), epic lineage tree, Teams story view, and Disputes table
  - Included in FTS5 full-text search index
  - Format: `PI-YY-x` (e.g. `PI-25-1`, `PI-25-2`, `PI-25-3`, `PI-25-4`)

- **Classify page — ephemeral by design** — The "Approve & Save" and "Correct this" buttons have been removed from the Classify page. Classification is now a pure exploration tool — no story is saved to the DB from chat. The only path to saving classifications is through the bulk verify workflow (Analytics → Upload). This preserves data integrity: Ground Truth and WAF Definitions are managed exclusively through the Settings governance screen.

### Test Data

- **All team-specific files expanded to 8 PIs** — `multi-team-product-120.csv`, `platform-engineering-80.csv`, and `compliance-focus-60.csv` rebuilt with 8 PI spans (PI-23-3 → PI-25-2) for meaningful trend analysis.
- **New `trend-analysis-480.csv`** — 480 stories, 5 consistent teams, 60 stories/PI, 8 PIs. Built-in trends: KTLO decreasing 35% → 19%, Strategic increasing 12% → 30%, mismatch rate improving 42% → 13%. Suitable for demonstrating PI-over-PI WAF shift analysis.
- **PI Number format corrected** — All test data files updated from `PI-YYQx` format to `PI-YY-x` (e.g. `PI-25-1`).

### API Changes

- `POST /api/disputes` — Create a new classification dispute
- `GET /api/disputes` — List disputes with status filter and pagination; returns per-status counts
- `POST /api/disputes/<id>/resolve` — Resolve a dispute: `dismiss`, `accept_gt`, or `flag_waf`
- `DELETE /api/disputes/<id>` — Hard delete a dispute record

### Database

- New table `disputes` — 21 columns: `id`, `created_at`, `story_title`, `story_description`, `ai_category`, `ai_color`, `ai_confidence`, `ai_reasoning`, `user_comment`, `suggested_category`, `status` (`pending`/`dismissed`/`accepted`/`flagged_waf`), `reviewed_at`, `reviewer_notes`, `resolved_category`, `resolved_color`, `gt_updated`, `waf_flagged`, `team`, `epic`, `story_id`, `pi_number`
- New column `pi_number TEXT DEFAULT ''` on `classifications` table
- FTS5 `classifications_fts` virtual table updated to include `pi_number`
- Schema migration runs automatically on startup — no action needed for existing databases

---

## v3.5.0 — April 2026

Version Library, WAF Definition inline editing, and UX clickability fixes.

### New Features

- **Version Library (Settings)** — Save named snapshots of WAF Definitions and Ground Truth. Each version stores a Name, Author, and Notes field. Versions are listed in a two-column panel (WAF | GT) and can be previewed, activated, or deleted independently. The Default Baseline is auto-created on first launch and is protected from deletion.
- **Per-run version selection** — Classify page and Analytics Upload tab both show "Using:" dropdowns for WAF Version and GT Version. Pick any saved version per run without changing what's globally loaded. Omit to use the active/default. Version IDs are stored in `upload_history` for full traceability.
- **WAF Definitions inline editing** — The WAF Definitions table in Settings is now fully editable: Category (text input), Color (dropdown), Run/Change (dropdown), Description (resizable textarea). Editing any cell shows an amber **Unsaved Changes** banner with three actions:
  - **Apply Changes** — writes edits to the in-memory store immediately (takes effect on next classification)
  - **Save as New Version** — applies edits then opens the Version Library modal pre-named with today's date (e.g. "WAF Edit — Apr 21")
  - **Discard** — reloads definitions from server, rolling back all changes
- **Ground Truth save-as-version nudge** — After saving any inline GT row, a green banner appears offering "Save as New Version". Clicking opens the Version Library modal pre-named "GT Edit — Apr 21". Dismissible without saving.
- **Story detail modal on Teams and Lineage pages** — Click any story row or story item to open a full-detail modal (title, description, WAF category, color, confidence, status, epic/feature/team, IDs). Dismiss with the × button, click outside, or press Escape.
- **KPI card click-to-filter on Teams and Lineage pages** — Clickable KPI cards (styled with hover highlight) filter the story list: Total Stories → show all, Mismatch Rate / Mismatches → show mismatched stories only, WAF Aligned → show matched stories.

### Deployment

- **`APPLICATION_ROOT` — reverse-proxy sub-path support** — Set `APPLICATION_ROOT=/your-prefix` in `.env` to serve the app under a URL prefix (e.g. `/h591-wafui`). Leave blank for root-path / local development (zero-change behaviour). Implemented via a `PrefixMiddleware` WSGI wrapper that strips the prefix before Flask routing and injects `window.APP_ROOT` into every page so all `fetch()` calls and nav links are automatically prefixed at runtime.
- **`.env.example`** — New file in the repo root documents all 6 environment variables (`ANTHROPIC_API_KEY`, `PORT`, `APPLICATION_ROOT`, and the three Bedrock options) with usage notes. Copy to `.env` and fill in values to get started.

### Bug Fixes

- **WAF Definitions description truncation** — Description column had `white-space:nowrap; overflow:hidden; text-overflow:ellipsis` which silently cut off long descriptions and made text unselectable. Now wraps naturally with `word-break:break-word` and is fully selectable.
- **Story rows not clickable after filter/sort on Teams page** — `renderStoryRows` and `renderEpicStoryRows` re-render the tbody on every sort/filter call. onclick attributes referencing stale indices broke after re-render. Fixed using `window._renderedStories[idx]` / `window._renderedEpicStories[idx]` pattern — onclick index always maps to the currently-rendered array.
- **Story items not clickable after filter on Lineage page** — `.story-item` divs use DOM show/hide for the mismatch filter, but onclick was missing entirely. Fixed with `window._linStoriesFlat[flatIdx]` pattern — the flat index is assigned at render time and survives show/hide.

### API Changes

- `PUT /api/waf-definitions` — Apply inline edits to WAF definitions (in-memory only, instant effect)
- `GET /api/versions/waf` — List saved WAF definition versions
- `POST /api/versions/waf` — Save current WAF definitions as a named version
- `DELETE /api/versions/waf/<id>` — Delete a WAF version (protected for Default Baseline)
- `GET /api/versions/waf/<id>/preview` — Preview version content without activating
- `POST /api/versions/waf/<id>/activate` — Activate a WAF version as the global default
- Same 5 endpoints for GT: `/api/versions/gt` and `/api/versions/gt/<id>/*`
- `POST /api/classify` — now accepts optional `waf_version_id` and `gt_version_id`
- `POST /api/bulk-verify` — now accepts optional `waf_version_id` and `gt_version_id` form fields

### Database

- New table `waf_versions` — `id`, `name`, `author`, `notes`, `filename`, `filepath`, `created_at`, `is_default`, `row_count`
- New table `gt_versions` — same schema as `waf_versions`
- New columns on `upload_history`: `waf_version_id INTEGER DEFAULT NULL`, `gt_version_id INTEGER DEFAULT NULL`
- Schema migration runs automatically on startup — no action needed for existing databases

---

## v3.4.0 — April 2026

Story Quality scoring, iterative rewrite chat, and data source unification.

### New Features

- **Story Quality tab** — New tab in Analytics (`/history`) for scoring uploaded stories against the Definition of Ready rubric from the GSE-MF Story Excellence Playbook v1.0. Select a data source and teams, click Score Stories, and the app AI-scores every story across 9 criteria in the background.
- **9-criterion DoR rubric — Data & Reporting domain:**
  1. Narrative Format (As a / I need / So that)
  2. Source Data Identified (table, system, refresh schedule)
  3. Business Rules Documented (calculations, definitions, edge cases)
  4. Output Artifact Defined (dashboard/report/table/file with schema)
  5. Acceptance Criteria (binary, independently testable AC1, AC2…)
  6. Data Quality Checks (row count tolerance, null checks, ref integrity)
  7. Traceability Tag (Source → Transform → Output → Consumer)
  8. Story Pointed (estimated in story points)
  9. Dependencies Flagged (upstream data, downstream consumers)
- **Collapsible rubric reference** — Inline rubric table in the tab: criterion, what it checks, good example, fix if missing.
- **Scoring thresholds:** Ready ≥ 8/9 (≥89%), Needs Work 5–7/9 (56–88%), Not Ready < 5/9 (< 56%).
- **Per-story detail** — Expand any story row to see pass/fail per criterion with prescriptive one-line fix suggestions for each failure.
- **Story Points scored locally** — Checked directly from the `story_points` DB field; does not consume an AI call.
- **Background job with progress bar** — Scoring runs as a background thread. Job # assigned sequentially. Progress bar tracks batch progress with label `Job #N — Scoring stories… X / Y`.
- **Scoring Run History** — Sub-section at the bottom of the Story Quality tab. Every completed run is recorded: Job #, timestamp, upload, teams, story count, avg score, Ready / Needs Work / Not Ready counts. **Load** replays any run's results; **Delete** removes the run and its scores.
- **Suggest Rewrite + Chat** — Each scored story has a "✍ Suggest Rewrite" button that opens a chat modal. The AI drafts a full story rewrite based only on what the original story contained; missing information is marked with `[REQUIRED: ...]` placeholders. The user can then iterate in the chat (e.g. "The source table is dw.loan_performance" or "Make AC2 more specific") and the AI responds with a full updated story each turn. **Copy latest** button captures the most recent AI response for pasting into JIRA.
- **CSV export** — Export all scored stories for the current selection as a flat CSV with pass/fail and fix text per criterion.

### UX Improvements

- **Unified Data Source** — Story Quality tab removed its own Upload/Data Source picker. It now reads from the global Data Source selector at the top of the Analytics page. Changing the data source while on the Story Quality tab reloads quality state rather than navigating away.
- **Teams always start fresh** — Team selections are never persisted across tab visits. The dropdown always opens with all teams checked, preventing stale team filters from carrying into new runs.
- **Results gated on history** — Saved results only auto-display on tab load if a corresponding Scoring Run History entry exists. Orphaned scores (from before a restart) are not surfaced.

### API Changes

- `GET /api/quality/rubric` — Return DoR rubric definition and available domains
- `GET /api/quality/uploads` — List uploads with story and team counts (used to populate quality filters)
- `GET /api/quality/teams?upload_id=N` — List teams for a given upload with story counts
- `POST /api/quality/score` — Start a background scoring job; returns `job_id` and `job_number`
- `GET /api/quality/job/<job_id>` — Poll job status, progress, and live results
- `GET /api/quality/results` — Fetch scored results; accepts `upload_id`+`domain`+`teams` or `run_id`
- `GET /api/quality/export` — Download scores as CSV
- `GET /api/quality/history` — List all scoring runs ordered by date
- `DELETE /api/quality/history/<run_id>` — Delete a scoring run and all its story scores
- `POST /api/quality/rewrite` — Generate initial AI story rewrite (uses original story + failing criteria context)
- `POST /api/quality/chat` — Continue an iterative rewrite session; accepts full `messages` array + original story context

### Database

- New table `story_quality_scores` — per-story scores per run: `run_id`, `job_number`, `overall_score`, `passed_count`, `total_count`, `criteria_json`, `story_title`, `team`, `story_id`
- New table `quality_runs` — run-level summaries: `run_id`, `job_number`, `upload_filename`, `teams_json`, `story_count`, `avg_score`, `ready_count`, `needs_work_count`, `not_ready_count`
- Schema migration runs automatically on startup

---

## v3.3.1 — March 2026

File Merger validation panel, per-story reject, Start Over button, timestamp in filenames, Job Name with time.

### New Features

- **Data Quality panel (Step 3)** — Always shows all 5 check categories after processing, each with a count badge. Green "✓ None found" inside zero-count cards. Cards with issues auto-expand. Categories: Orphan Stories (red), Orphan Features (orange), Missing WAF Category (yellow), Unknown WAF Color (yellow), WAF Divergence (blue).
- **Per-row reject** — Each issue card shows checkboxes per story plus "Reject All / Clear All". The preview table also has a Reject column so any story can be excluded without requiring an issue. Rejected rows are tracked in a shared set and excluded from both Download and Submit for Analysis.
- **Rejection banner** — A yellow warning banner in Step 3 and a "−N rejected" badge in the action row show how many rows are currently marked for exclusion.
- **← Start Over button** — Resets all file inputs, clears results sections, and scrolls back to the top. Available in the Step 4 action row.
- **Timestamp in merged filenames** — All downloaded and submitted files now include `_YYYYMMDD_HHmm` (e.g. `SOX-Compliance-PI-3_20260330_1423.csv`).
- **Job Name includes time** — Auto-filled default is now `Merged Import - Mar 30, 2026 14:23` (date + time) for uniqueness.

### API Changes

- `POST /api/merge/download/<token>` — Changed from GET to POST; accepts `rejected_ids` JSON array and `job_name` in request body.
- `POST /api/merge/send-to-classifier/<token>` — Accepts `rejected_ids` as FormData field; excludes rejected rows before writing the file.

---

## v3.3.0 — March 2026

File Merger, global search wired, column ordering, Story Title / Story Description rename, WAF category rename.

### New Features

- **File Merger page (`/merge`)** — New screen that accepts three JIRA export files (Epic Attributes, Feature Attributes, Story Attributes) and merges them into the canonical WAF import format. Auto-detects columns by keyword priority. Joins Story → Feature → Epic to populate the full hierarchy. WAF and Team resolved from Story first, falling back to Feature then Epic. Job Name field (auto-filled with today's date, editable) used as the filename in Analytics upload history.
- **Submit for Analysis** — "Submit for Analysis" button on the Merge page sends the merged file directly into the Analytics upload pipeline without requiring a manual re-upload. Redirects to `/history` and auto-triggers the column mapping step via `sessionStorage`.
- **Sample merge files** — Three sample JIRA export files added to `test-data/merge-samples/`: `sample-epic-attributes.csv`, `sample-feature-attributes.csv`, `sample-story-attributes.csv`. 5 epics · 10 features · 24 stories, all hierarchy links verified clean.
- **Global search wired** — Search bar was UI-only in previous releases. Now fully functional: debounced fetch to `/api/search`, results card with highlighted matches, breadcrumb (Epic ID → Feature ID → Story ID), WAF badges, mismatch indicator, and upload source. Present on all pages.
- **IDs in search results** — `/api/search` now returns and displays `story_id`, `feature_id`, `epic_id` in results.

### Column & Field Changes

- **Column order standardised** — All three new test CSVs and the Expected File Format table now follow: `Epic ID · Feature ID · Story ID · Epic · Parent Feature · Story Title · Story Description · Team · WAF Category · WAF Color · Sub-Category · Confidence · Run/Change · Timestamp · Issue Key`
- **"Title" → "Story Title", "Description" → "Story Description"** — Renamed in all test CSV headers, `generate_test_data.py`, column mapping labels (`verify.py`), `find_col` keyword lists, `history.html` Expected File Format table and field hints, and docs.
- **"Other Blocked Priority" → "Other Block Priority"** — Renamed across WAF definitions, all test CSVs, ground truth, baselines, `state.py`, generator script, settings page, and README.

### UX

- **Expected File Format table** — Reordered with section dividers (Hierarchy IDs / Hierarchy Names / Organisation / WAF Classification / Metadata). Added Confidence and Run/Change rows that were previously missing.
- **Story ID and Issue Key as separate rows** — Previously shown as one combined row; now documented separately with individual examples and descriptions.
- **File Merger nav link** — Added to all 9 pages and Home menu grid (🔀, "Data Prep" badge).

### API Changes

- `POST /api/merge/process` — Merge three JIRA export files into WAF import format
- `GET /api/merge/download/<token>` — Download merged CSV
- `POST /api/merge/send-to-classifier/<token>` — Send merged file directly to classify pipeline; returns full preview JSON for seamless handoff to `/history`
- `GET /api/search` — Now returns `story_id`, `feature_id`, `epic_id` in results

### Docs

- API Reference — File Merger section added
- Quick Start — Recommended column order added, recognition table updated for `Story Title` / `Story Description` priority
- All docs updated for `Other Block Priority` rename

---

## v3.2.3 — March 2026

Global search wired up, IDs in search results, dual Story ID / Issue Key column support documented.

### New Features

- **Global search now functional** — The search bar in the nav was previously UI-only. Now wired up with debounced fetch to `/api/search`, results card with highlighted matches, breadcrumb trail (Epic ID → Feature ID → Story ID), WAF category/color badges, mismatch indicator, and upload source. Present on all pages.
- **IDs in search results** — Search results now display Story ID, Feature ID, and Epic ID tags inline. All three ID fields are also returned by the `/api/search` endpoint.
- **Dual Story ID / Issue Key columns** — Both `Story ID` (e.g. STR-10001) and `Issue Key` (e.g. COMP-001) are retained in all test data files and supported in uploads. `Story ID` takes priority when both are present; `Issue Key` is the fallback. Documented in Expected File Format, API Reference, and Quick Start.

### Bug Fixes

- **`/api/search` missing ID fields** — `story_id`, `feature_id`, `epic_id` were not included in the SELECT or response JSON. Added to both.

### Docs

- **Expected File Format** — Split `Story ID / Issue Key` row into two separate rows: `Story ID` and `Issue Key`, each with correct description and example format.
- **API Reference** — Updated `story_id` column recognition table to note `Story ID` has priority over `Issue Key`.
- **Quick Start** — Column auto-detection table updated to reflect `Story ID` priority.

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
- **Global search scoped** — Global search bar not shown on History, Teams, or Lineage pages, which have their own per-table filters. *(Planned — currently shown on all pages, pending removal from those three pages.)*

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
- **Mismatch visibility improved** — Mismatched rows highlighted; tree view shows User Submitted WAF (strikethrough) → AI Suggested WAF

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
