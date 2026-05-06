# WAF Classifier — API Reference

Base URL: `http://localhost:8080`

If `APPLICATION_ROOT` is set in `.env` (e.g. `/h591-wafui`), all URLs are served under that prefix: `http://localhost:8080/h591-wafui/api/...`

All endpoints return JSON unless otherwise noted. Error responses always return a generic message — full details are logged server-side only.

---

## Error Responses

```json
{ "error": "Human-readable message" }
```

| HTTP Code | Meaning |
|-----------|---------|
| 400 | Bad request (missing file, invalid format, missing required parameter) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

---

## System

### GET /api/status

Returns current system state.

**Response:**
```json
{
  "api_key_configured": true,
  "ai_backend": "anthropic",
  "ai_model": "claude-sonnet-4-6",
  "waf_loaded": true,
  "waf_categories": ["KTLO", "Business Maintenance", "..."],
  "ground_truth_loaded": true,
  "ground_truth_count": 18,
  "chat_history_length": 4
}
```

`ai_backend` is `"anthropic"` when an API key is configured, `"bedrock"` when falling back to AWS Bedrock.

### GET /api/waf-definitions

Returns structured WAF framework definitions for the reference page.

**Response:**
```json
{
  "loaded": true,
  "definitions": [
    {
      "run_change": "Run",
      "color": "GRAY",
      "category": "KTLO (Keep the Lights On)",
      "description": "Non-discretionary, recurring work...",
      "decision_rule": "Required to meet SLAs, legal...",
      "examples": "Emergency break-fix; Prod outages; ..."
    }
  ]
}
```

### PUT /api/waf-definitions

Apply inline edits to WAF definitions. Updates the in-memory store immediately — no file write. Changes take effect on the next classification.

**Request:**
```json
{
  "definitions": [
    {
      "category": "KTLO (Keep the Lights On)",
      "color": "GRAY",
      "run_change": "Run",
      "description": "Non-discretionary, recurring work...",
      "decision_rule": "Required to meet SLAs...",
      "examples": "Emergency break-fix; Prod outages; ..."
    }
  ]
}
```

**Response:**
```json
{ "success": true, "count": 8 }
```

---

## Search

### GET /api/search

Full-text search across all saved classifications using SQLite FTS5.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `q` | string | Search query (minimum 2 characters). Prefix match on last token. |
| `upload_id` | int | Optional. Filter to a specific upload batch. |
| `limit` | int | Max results (default: 25, max: 100). |

**Response:**
```json
{
  "results": [
    {
      "id": 42,
      "title": "Fix production DB connection pool exhaustion",
      "team": "Platform",
      "epic": "Platform Reliability",
      "parent_feature": "Database Health",
      "waf_category": "KTLO",
      "waf_color": "GRAY",
      "confidence": "HIGH",
      "is_mismatch": false,
      "story_id": "PROJ-123",
      "upload_id": 3,
      "filename": "sprint-backlog.csv",
      "uploaded_at": "2026-03-20T14:30:00",
      "timestamp": "2026-03-20T14:30:00"
    }
  ],
  "total": 1,
  "query": "db connection"
}
```

Results are ranked by BM25 relevance. The last token in `q` is matched as a prefix (e.g. `"conn"` matches `"connection"`).

---

## Classification

### POST /api/classify

Classify a single story via chat.

**Request:**
```json
{
  "message": "Classify: Fix production DB connection pool exhaustion causing 504 errors",
  "session_id": "optional-session-id",
  "epic": "Platform Reliability",
  "parent_feature": "Database Health",
  "story_id": "PROJ-123",
  "story_points": "5",
  "waf_version_id": 3,
  "gt_version_id": 2
}
```

All context fields (`epic`, `parent_feature`, `story_id`, `story_points`) are optional. When provided, they are saved alongside the AI classification in the database.

| Field | Type | Description |
|-------|------|-------------|
| `message` | string | **Required.** The story text or classify prompt. |
| `session_id` | string | Optional. Conversation session identifier. |
| `epic` | string | Optional. Epic name for context. |
| `parent_feature` | string | Optional. Parent feature name for context. |
| `story_id` | string | Optional. Issue/ticket ID. |
| `story_points` | string | Optional. Story point estimate. |
| `waf_version_id` | int | Optional. Override the active WAF version for this call only. Omit to use the globally active version. |
| `gt_version_id` | int | Optional. Override the active GT version for this call only. Omit to use the globally active version. |

**Response:**
```json
{
  "response": "Based on the description...",
  "classification": {
    "category": "KTLO",
    "sub_category": "Production Support",
    "color": "GRAY",
    "confidence": "High",
    "reasoning": "This is operational work...",
    "is_mismatch": false
  },
  "session_id": "abc123",
  "classification_id": 42
}
```

### POST /api/batch-classify

Classify multiple stories at once.

**Request:**
```json
{
  "stories": "Story 1 | Description 1 | Current Tag\nStory 2 | Description 2 | Current Tag"
}
```

### POST /api/approve-classification

Save a chat classification as a ground truth example. Only meaningful when the AI response includes a clear WAF category recommendation.

**Request:**
```json
{
  "title": "Fix production DB connection pool",
  "description": "Connection pool exhaustion causing 504 errors...",
  "waf_category": "KTLO",
  "waf_subcategory": "Production Support",
  "waf_color": "GRAY",
  "run_change": "Run"
}
```

**Response:**
```json
{
  "success": true,
  "example_count": 19
}
```

---

## Data Upload

### POST /api/upload-waf

Upload WAF definitions file.

**Request:** `multipart/form-data` with `file` field (CSV, XLSX, JSON, or TXT)

**Response:**
```json
{
  "success": true,
  "categories": ["KTLO", "Business Maintenance", "..."],
  "count": 8
}
```

### POST /api/upload-ground-truth

Upload ground truth examples.

**Request:** `multipart/form-data` with `file` field (CSV or XLSX)

**Response:**
```json
{
  "success": true,
  "count": 18,
  "categories": {"KTLO": 3, "Business Maintenance": 2}
}
```

---

## Dashboard

### GET /api/dashboard/summary

Returns all dashboard data: KPIs, chart data, and recent classifications.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `upload_id` | int | Optional. Filter to a specific upload batch. |

**Response:**
```json
{
  "total_classifications": 42,
  "total_approved": 15,
  "approval_rate": 35.7,
  "total_mismatches": 8,
  "ground_truth_count": 33,
  "category_distribution": {"KTLO": 12, "Business Maintenance": 8},
  "confidence_distribution": {"HIGH": 25, "MEDIUM": 12, "LOW": 5},
  "run_change": {"Run": 22, "Change": 20},
  "color_distribution": {"GRAY": 12, "BLACK": 8},
  "daily_activity": [{"date": "2026-03-01", "count": 5}],
  "recent": [{"id": 42, "title": "...", "category": "KTLO"}]
}
```

### GET /api/dashboard/stories

Paginated, filterable drill-down of individual story records.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `filter` | string | One of: `mismatches`, `approved`, `category`, `color`, `confidence`, `run_change` |
| `value` | string | Value to filter on (e.g. `KTLO`, `High`, `Run`) |
| `upload_id` | int | Optional. Restrict to a specific upload batch. |
| `page` | int | Page number (default: 1) |
| `per_page` | int | Results per page (default: 100, max: 500) |

**Response:**
```json
{
  "stories": [
    {
      "id": 42,
      "story_title": "Fix connection pool",
      "waf_category": "KTLO",
      "waf_color": "GRAY",
      "run_change": "Run",
      "confidence": "High",
      "was_mismatch": true,
      "approved": false,
      "original_tag": "New Feature",
      "epic": "Platform Reliability",
      "story_id": "PROJ-123",
      "timestamp": "2026-03-01T10:00:00"
    }
  ],
  "total": 42,
  "page": 1,
  "per_page": 100,
  "total_pages": 1
}
```

---

## Historical Analytics

### GET /api/history/sprints

Returns classification data organized into 2-week sprint windows.

### GET /api/history/monthly

Returns monthly rollup with period-over-period comparison.

### GET /api/history/timeline

Paginated, filterable timeline of all classifications.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Page number (default: 1) |
| `per_page` | int | Results per page (default: 50, max: 500) |
| `from_date` | string | Start date (YYYY-MM-DD) |
| `to_date` | string | End date (YYYY-MM-DD) |
| `category` | string | Filter by WAF category |
| `color` | string | Filter by WAF color |
| `team` | string | Filter by team |
| `confidence` | string | Filter by confidence level |
| `mismatch_only` | bool | Only show mismatches |

### GET /api/history/export

Export all classifications as CSV.

### GET /api/history/export-xlsx

Export formatted Excel workbook with 3 sheets: Summary, Monthly Rollups, Raw Data. Conditional formatting: green = approved, red = mismatch.

### GET /api/history/uploads

List all previous upload batches with saved status.

**Response:**
```json
{
  "uploads": [
    {
      "id": 1,
      "filename": "sprint-backlog.csv",
      "row_count": 120,
      "imported_count": 120,
      "uploaded_at": "2026-03-01T10:00:00",
      "saved_count": 100,
      "has_results": true,
      "waf_version_id": 3,
      "gt_version_id": 2
    }
  ]
}
```

`saved_count` — actual stories saved to the classifications table (reliable saved/unsaved indicator).
`has_results` — `true` if AI results are stored and can be recovered without re-running the AI.
`waf_version_id` — nullable int. The WAF version used when this upload was classified, if overridden.
`gt_version_id` — nullable int. The GT version used when this upload was classified, if overridden.

### POST /api/history/uploads/{upload_id}/reload

Reload a previous upload's AI results into the verify/review view.

### DELETE /api/history/uploads/{upload_id}

Delete an upload and all its associated classifications.

**Response:**
```json
{ "success": true, "deleted_classifications": 100 }
```

### GET /api/classifications/{id}

Return full details for a single saved classification.

---

## Bulk Verify

### POST /api/bulk-verify/preview

Upload a file and return column info for field mapping without starting AI classification.

**Request:** `multipart/form-data` with `file` field (CSV or XLSX)

**Response:**
```json
{
  "success": true,
  "filename": "stories.csv",
  "file_columns": ["story title", "description", "waf category", "issue key"],
  "suggested_mappings": {
    "title": "story title",
    "description": "description",
    "story_id": "issue key"
  },
  "target_fields": [{"key": "title", "label": "Story Title", "required": true}],
  "sample_rows": [{"story title": "Fix bug", "description": "..."}],
  "total_rows": 100,
  "preview_id": "uuid"
}
```

**Recognized column names for ID fields:**

| Field | Recognized headers | Notes |
|-------|-------------------|----|
| `story_id` | **Story ID** (priority), Issue Key, Key, Ticket, JIRA ID, Item ID | Both `Story ID` (e.g. STR-10001) and `Issue Key` (e.g. COMP-001) are accepted; `Story ID` takes priority when both are present |
| `feature_id` | Feature ID, Feature key, Parent ID, Parent key | e.g. F-C001 |
| `epic_id` | Epic ID, Epic key, Epic link, Initiative ID | e.g. EP-C001 |
| `story_points` | Story Points, story_points, Points, SP, Estimate | Numeric value stored as text |
| `pi_number` | **PI Number** (priority), PI, PI #, Program Increment, PI_Number | Format `PI-YY-x` (e.g. `PI-25-1`). Stored as text. |

### POST /api/bulk-verify

Upload a file and AI-classify every story. All uploads process asynchronously.

**Request:** `multipart/form-data` with `file` field (CSV or XLSX). Optionally include `preview_id` and `column_mappings` (JSON) from the preview step. Also accepts optional integer fields `waf_version_id` and `gt_version_id` to override the active WAF/GT version for this job only. Version IDs are stored in `upload_history` for traceability.

**Rate limit:** Default 5 requests per IP per minute. Returns HTTP 429 if exceeded.

**Response:**
```json
{
  "async": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_stories": 100,
  "message": "Processing started"
}
```

### GET /api/bulk-verify/status/{job_id}

Poll the status of an async bulk-verify job.

**Response (complete):**
```json
{
  "status": "done",
  "results": [...],
  "total": 5000
}
```

### POST /api/bulk-verify/save

Save selected verified classifications to the database. Only mismatch rows (`is_match: false`) are saved with `approved: true` — match rows are saved without the approved flag.

**Request:**
```json
{
  "rows": [
    {
      "title": "Fix connection pool",
      "description": "...",
      "team": "Platform",
      "epic": "Platform Reliability",
      "parent_feature": "Database Health",
      "story_id": "PROJ-123",
      "feature_id": "PROJ-100",
      "epic_id": "PROJ-50",
      "story_points": "5",
      "user_submitted_waf": "New Feature",
      "ai_suggested_waf": "KTLO",
      "ai_color": "GRAY",
      "ai_confidence": "HIGH",
      "is_match": false,
      "use_ai": true
    }
  ],
  "upload_id": 3
}
```

**Response:**
```json
{ "success": true, "saved": 15 }
```

---

## Epic Lineage

### GET /api/epics

List all epics with story and mismatch counts.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `upload_id` | int | Optional. Filter to a specific upload batch. |

### GET /api/epics/summary

Get detailed data for all epics including health scores, category breakdowns, and story tree.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `upload_id` | int | Optional. Filter to a specific upload batch. |

**Response (story object within features):**
```json
{
  "id": 1,
  "title": "Fix connection pool",
  "category": "KTLO",
  "color": "GRAY",
  "confidence": "High",
  "mismatch": true,
  "approved": false,
  "original_tag": "New Feature",
  "run_change": "Run",
  "team": "Platform",
  "story_id": "PROJ-123",
  "feature_id": "PROJ-100",
  "epic_id": "PROJ-50",
  "story_points": "5",
  "epic": "Platform Reliability"
}
```

### GET /api/epics/uploads

List uploads that have epic-tagged classifications. Used to populate the Data Source filter on the Lineage page.

### POST /api/epics/assign

Bulk assign epic and parent feature to classification IDs.

**Request:**
```json
{
  "ids": [1, 2, 3],
  "epic": "Platform Reliability",
  "parent_feature": "Database Health"
}
```

### GET /api/epics/autocomplete?q=plat

Get autocomplete suggestions for epic and feature names.

**Response:**
```json
{
  "epics": ["Platform Reliability", "Platform Migration"],
  "features": ["Platform Security", "Platform Monitoring"]
}
```

---

## Team Report

### GET /api/teams/summary

Get team-level analytics with category breakdowns, cross-team epic matrix, and totals.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `upload_id` | int | Optional. Filter to a specific upload batch. |

**Response:**
```json
{
  "teams": [
    {
      "name": "Treasury Tech",
      "total_stories": 45,
      "epics": ["Epic A", "Epic B"],
      "epic_count": 2,
      "mismatches": 3,
      "mismatch_rate": 6.7,
      "approved": 3,
      "categories": {"KTLO": 20, "Technical Maintenance": 15},
      "colors": {"GRAY": 10, "BLACK": 15},
      "run_change": {"Run": 30, "Change": 15},
      "dominant_category": "KTLO",
      "confidence_breakdown": {"HIGH": 30, "MEDIUM": 10, "LOW": 5}
    }
  ],
  "cross_team": {
    "teams_by_epic": {"Epic A": ["Treasury Tech", "DevOps"]},
    "epics_by_team": {"Treasury Tech": ["Epic A", "Epic B"]}
  },
  "totals": {
    "team_count": 5,
    "total_stories": 200,
    "avg_mismatch_rate": 8.5,
    "most_active_team": "Treasury Tech"
  }
}
```

### GET /api/teams/detail

Get full story list for a specific team, grouped by epic and feature.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `team` | string | **Required.** Team name. |
| `upload_id` | int | Optional. Filter to a specific upload batch. |

**Response:**
```json
{
  "team": "Treasury Tech",
  "total_stories": 45,
  "epic_count": 2,
  "mismatch_count": 3,
  "mismatch_rate": 6.7,
  "dominant_category": "KTLO",
  "epics": [
    {
      "name": "Epic A",
      "story_count": 20,
      "mismatches": 2,
      "features": [
        {
          "name": "Feature X",
          "story_count": 10,
          "stories": [
            {
              "id": 1,
              "title": "Implement API rate limiting",
              "waf_category": "KTLO",
              "waf_color": "GRAY",
              "confidence": "HIGH",
              "was_mismatch": false,
              "epic": "Epic A",
              "parent_feature": "Feature X",
              "story_id": "PROJ-123",
              "feature_id": "PROJ-100",
              "epic_id": "PROJ-50",
              "timestamp": "2026-03-20T14:30:00"
            }
          ]
        }
      ]
    }
  ]
}
```

### GET /api/teams/by-epic

Get all teams working on a specific epic.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `epic` | string | **Required.** Epic name. |
| `upload_id` | int | Optional. Filter to a specific upload batch. |

### GET /api/teams/epics-list

List all epics with team and story counts.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `upload_id` | int | Optional. Filter to a specific upload batch. |

---

## Settings

### GET /api/settings

Returns all configurable settings.

**Response:**
```json
{
  "settings": {
    "sync_batch_size": "25",
    "async_batch_size": "50",
    "max_concurrent_workers": "5",
    "rate_limit_per_minute": "5"
  }
}
```

### PUT /api/settings

Update settings. Validates ranges (batch: 1–200, workers: 1–20, rate: 1–60).

**Request:**
```json
{ "async_batch_size": 100, "max_concurrent_workers": 8 }
```

---

## Ground Truth

### GET /api/ground-truth

Returns all ground truth examples.

### PUT /api/ground-truth/{idx}

Update a ground truth example by index. Accepts partial updates.

### POST /api/ground-truth/add

Add a new ground truth example. Title is required.

### DELETE /api/ground-truth/{idx}

Delete a ground truth example by index.

---

## Baselines

### POST /api/baseline/save

Save current WAF definitions and ground truth as a timestamped baseline snapshot.

### GET /api/baseline/list

List all available baselines. Default baseline is always first.

### POST /api/baseline/restore

Restore WAF definitions and ground truth from a baseline.

**Request:**
```json
{ "timestamp": "default" }
```

---

## Version Library

Named snapshots of WAF Definitions and Ground Truth. Multiple versions can be saved independently and activated per classification run without changing what's globally loaded.

### GET /api/versions/waf

List all saved WAF definition versions.

**Response:**
```json
{
  "versions": [
    {
      "id": 1,
      "name": "Default Baseline",
      "author": "System",
      "notes": "Auto-created on first launch",
      "filename": "waf_Default_Baseline.csv",
      "created_at": "2026-04-01T10:00:00",
      "is_default": true,
      "row_count": 8
    }
  ]
}
```

`is_default: true` — the Default Baseline; cannot be deleted.

### POST /api/versions/waf

Save the current active WAF definitions as a named version.

**Request:**
```json
{
  "name": "WAF Edit — Apr 21",
  "author": "Jane Smith",
  "notes": "Added clarification to KTLO description"
}
```

**Response:**
```json
{ "success": true, "id": 3, "name": "WAF Edit — Apr 21" }
```

### DELETE /api/versions/waf/{id}

Delete a WAF version. Returns 400 if the version is the Default Baseline (`is_default: true`).

**Response:**
```json
{ "success": true }
```

### GET /api/versions/waf/{id}/preview

Preview the content of a WAF version without activating it.

**Response:**
```json
{
  "id": 3,
  "name": "WAF Edit — Apr 21",
  "definitions": [
    { "category": "KTLO (Keep the Lights On)", "color": "GRAY", "run_change": "Run", "description": "..." }
  ]
}
```

### POST /api/versions/waf/{id}/activate

Load a WAF version into the active in-memory store. All subsequent classifications use this version until changed.

**Response:**
```json
{ "success": true, "name": "WAF Edit — Apr 21", "categories": 8 }
```

### GET /api/versions/gt

List all saved Ground Truth versions. Same response shape as `GET /api/versions/waf`.

### POST /api/versions/gt

Save the current active Ground Truth as a named version. Same request shape as `POST /api/versions/waf`.

### DELETE /api/versions/gt/{id}

Delete a GT version. Returns 400 for the Default Baseline.

### GET /api/versions/gt/{id}/preview

Preview GT version content.

**Response:**
```json
{
  "id": 2,
  "name": "GT Edit — Apr 21",
  "examples": [
    { "title": "Fix prod DB", "category": "KTLO", "color": "GRAY", "run_change": "Run", "description": "..." }
  ],
  "count": 22
}
```

### POST /api/versions/gt/{id}/activate

Load a GT version into the active store. All subsequent classifications use this version.

**Response:**
```json
{ "success": true, "name": "GT Edit — Apr 21", "count": 22 }
```

---

## File Merger

### POST /api/merge/process

Accept three JIRA export files and merge them into the canonical WAF import format.

**Request:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `epic_file` | file | Epic Attributes CSV or XLSX |
| `feature_file` | file | Feature Attributes CSV or XLSX |
| `story_file` | file | Story Attributes CSV or XLSX |

**Auto-detected columns:**

| File | Field | Recognized headers |
|------|-------|--------------------|
| Epic | Epic ID | Jira SaaS Epic#, Epic#, Epic Key, Epic ID |
| Epic | Epic Name | Summary, Epic Summary, Epic Name |
| Epic | WAF | Work Alignment Framework, Work Alignment, WAF |
| Feature | Feature ID | Jira SaaS Feature Key, Feature Key, Feature ID |
| Feature | Feature Name | Feature Summary, Feature Name, Summary |
| Feature | Parent Epic | Parent Epic Number, Parent Epic, Epic# |
| Feature | Team | Team, Team of Teams |
| Feature | WAF | Work Alignment, WAF Derived, Work Category |
| Story | Story ID | Story #, Story#, Issue Key, Key |
| Story | Story Title | Story Name, Summary, Title |
| Story | Parent Feature | Parent Feature, Feature Key |
| Story | Team | Team, Teams |
| Story | WAF | WAF Derived, Work Alignment |
| Story | Timestamp | Resolved Date, Created, Date |
| Story | Story Points | Story Points, Points, SP, Estimate |

**Join logic:** Story → Feature (via Parent Feature = Feature ID) → Epic (via Parent Epic = Epic ID). WAF priority: Story > Feature > Epic. Team priority: Story > Team.

**Response:**
```json
{
  "token": "a3f2c1b4",
  "stats": {
    "epics": 5,
    "features": 10,
    "stories": 24,
    "matched": 22,
    "unmatched_features": 0,
    "unmatched_epics": 0
  },
  "preview": [ { "Epic ID": "EP-C001", "Story Title": "...", "Story Points": "5", "_diff_waf_conflict": false, "_diff_missing_waf": false, "_diff_s_waf": "KTLO", "_diff_f_waf": "KTLO" } ],
  "columns": ["Epic ID", "Feature ID", "Story ID", "Epic", "Parent Feature", "Story Title", "Story Description", "Story Points", "Team", "WAF Category", "WAF Color", "Sub-Category", "Confidence", "Run/Change", "Timestamp", "Issue Key"],
  "column_map": { "epic": { "id_col": "Jira SaaS Epic#", "..." : "..." } },
  "issues": {
    "orphan_stories":  [ { "story_id": "STR-001", "story_title": "...", "missing_feature": "F-X99" } ],
    "orphan_features": [ { "feature_id": "F-X99", "feature_name": "...", "missing_epic": "EP-X99" } ],
    "missing_waf":     [ { "story_id": "STR-002", "story_title": "..." } ],
    "unknown_color":   [ { "story_id": "STR-003", "story_title": "...", "waf_category": "Custom Cat" } ],
    "waf_divergence":  [ { "story_id": "STR-004", "story_title": "...", "story_waf": "KTLO", "feature_waf": "New Capability", "feature_id": "F-001" } ],
    "total": 5,
    "clean": false
  }
}
```

### POST /api/merge/download/\<token\>

Download the merged CSV, excluding any rejected story IDs. Token is 8-char hex from `/api/merge/process`.

**Request:** `application/json`

| Field | Type | Description |
|-------|------|-------------|
| `rejected_ids` | array | Story IDs to exclude from output (optional, default `[]`) |
| `job_name` | string | Used to build the filename (optional) |

Returns `text/csv` as attachment. Filename: `<job-name>_YYYYMMDD_HHmm.csv`.

### POST /api/merge/send-to-classifier/\<token\>

Copy the merged file (minus rejected rows) into the upload pipeline and return full preview data, ready for the column mapping step in Analytics.

**Request:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `job_name` | string | Optional. Shown as filename in upload history. |
| `rejected_ids` | string | JSON array of story IDs to exclude (optional, default `"[]"`). |

**Response:** Same shape as `POST /api/bulk-verify/preview` — includes `preview_id`, `suggested_mappings`, `target_fields`, `sample_rows`, `total_rows`. Frontend stores in `sessionStorage` and redirects to `/history`, which auto-triggers the column mapping step.

---

## Classification Disputes

Workflow for flagging AI classifications that the user believes are incorrect. Users flag from the Classify page; reviewers triage and resolve on the `/disputes` page.

**Dispute status lifecycle:** `pending` → `dismissed` | `accepted` | `flagged_waf`

### POST /api/disputes

Create a new classification dispute.

**Request:**
```json
{
  "story_title": "Migrate ETL pipeline to Spark",
  "story_description": "Full story text as sent to the AI classifier...",
  "ai_category": "KTLO (Keep the Lights On)",
  "ai_color": "GRAY",
  "ai_confidence": "HIGH",
  "ai_reasoning": "Framed as a migration of existing infrastructure...",
  "user_comment": "This is a net-new platform capability, not maintenance. The AI anchored on 'migrate' but the outcome is a strategic new data architecture.",
  "suggested_category": "Enterprise Strategic Priority",
  "team": "Data Platform",
  "epic": "Cloud Data Platform",
  "story_id": "PROJ-456",
  "pi_number": "PI-25-2"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `story_title` | string | **Yes** | First line of the story (capped at 120 chars). |
| `story_description` | string | No | Full story text as sent to the AI. |
| `ai_category` | string | No | AI's suggested WAF category. |
| `ai_color` | string | No | AI's suggested WAF color. |
| `ai_confidence` | string | No | AI's confidence level (HIGH/MEDIUM/LOW). |
| `ai_reasoning` | string | No | AI's reasoning text. |
| `user_comment` | string | No | User's explanation of why the classification is wrong. UI enforces minimum 30 characters. |
| `suggested_category` | string | No | User's suggested correct WAF category. |
| `team`, `epic`, `story_id`, `pi_number` | string | No | Contextual fields from the classify page sidebar. |

**Response:**
```json
{ "success": true, "id": 7 }
```

HTTP 201 on success.

### GET /api/disputes

List disputes with optional status filter and pagination.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `status` | string | `pending` (default), `dismissed`, `accepted`, `flagged_waf`, or `all` |
| `page` | int | Page number (default: 1) |
| `per_page` | int | Results per page (default: 25, max: 200) |

**Response:**
```json
{
  "disputes": [
    {
      "id": 7,
      "created_at": "2026-04-24T10:30:00",
      "story_title": "Migrate ETL pipeline to Spark",
      "story_description": "...",
      "ai_category": "KTLO (Keep the Lights On)",
      "ai_color": "GRAY",
      "ai_confidence": "HIGH",
      "ai_reasoning": "...",
      "user_comment": "This is a net-new platform capability...",
      "suggested_category": "Enterprise Strategic Priority",
      "status": "pending",
      "reviewed_at": null,
      "reviewer_notes": "",
      "resolved_category": "",
      "resolved_color": "",
      "gt_updated": 0,
      "waf_flagged": 0,
      "team": "Data Platform",
      "epic": "Cloud Data Platform",
      "story_id": "PROJ-456",
      "pi_number": "PI-25-2"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 25,
  "total_pages": 1,
  "counts": {
    "pending": 1,
    "dismissed": 3,
    "accepted": 5,
    "waf_flagged": 1
  }
}
```

Pending disputes always sort first, then by `created_at DESC`.

### POST /api/disputes/{id}/resolve

Resolve a dispute. Three actions available:

| Action | Result | Notes |
|--------|--------|-------|
| `dismiss` | Status → `dismissed` | No GT or WAF change. |
| `accept_gt` | Status → `accepted`, `gt_updated: 1` | Saves a corrected classification to the DB with `approved: true` and the resolved category/color. Requires `resolved_category`. |
| `flag_waf` | Status → `flagged_waf`, `waf_flagged: 1` | Escalates to WAF definition owners. |

**Request:**
```json
{
  "action": "accept_gt",
  "resolved_category": "Enterprise Strategic Priority",
  "resolved_color": "BLACK",
  "reviewer_notes": "Confirmed: net-new capability, not maintenance. Story description was ambiguous."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | **Yes** | `dismiss`, `accept_gt`, or `flag_waf` |
| `resolved_category` | string | For `accept_gt` | Confirmed correct WAF category. |
| `resolved_color` | string | No | Confirmed correct color. |
| `reviewer_notes` | string | No | Reviewer's notes for the record. |

**Response:**
```json
{ "success": true }
```

### DELETE /api/disputes/{id}

Hard delete a dispute record. Returns 404 if not found.

**Response:**
```json
{ "success": true }
```

---

## Backlog Quality

Backlog Quality scores backlog items against a Definition-of-Ready rubric loaded from `rubrics/`. Rubrics compose: a universal **base** for the level (`story` / `feature` / `epic` / `defect`) plus an optional **domain extension** (`data` / `capmkts` / `sf-origination` / `mf-servicing` / `risk` / …) that adds line-of-business-specific criteria.

The composite rubric id has the form `<level>-dor` or `<level>-dor:<domain>`. Examples:
- `story-dor` — universal Story DoR (7 criteria)
- `story-dor:data` — universal + Data extension (10 criteria)
- `story-dor:capmkts` — universal + CapMkts extension (11 criteria)
- `feature-dor:data`, `epic-dor`, `defect-dor`, etc.

The legacy parameter `domain=data_reporting` is still accepted and resolves to `story-dor`. New code should use `rubric_id` (composite) or `rubric_id` + `domain` (split).

### GET /api/quality/rubric

Return a rubric definition. Composes base + domain extension on the fly.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `rubric_id` | string | Composite, e.g. `story-dor`, `story-dor:data`. Optional. |
| `level` | string | One of `story`, `feature`, `epic`, `defect`. Optional. |
| `domain` | string | Optional. Layers an extension on top of the level base. |

If only `domain` is supplied and its value is a legacy alias (e.g. `data_reporting`), it is treated as a `rubric_id`.

**Response:**
```json
{
  "rubric": {
    "id": "story-dor:data",
    "level": "story",
    "phase": "ready",
    "domain": "data",
    "name": "Story — Definition of Ready (Base)",
    "extension_name": "Story DoR — Data & Reporting Extensions",
    "extension_is_placeholder": false,
    "scoring_mode": "balanced",
    "source_doc": "docs/playbook/story-excellence-v2.docx",
    "source_version": "v2",
    "source_section": "8.3",
    "thresholds": {
      "ready": { "min_score": 85, "all_required_pass": true },
      "needs_work": { "min_score": 56 }
    },
    "criteria": [
      {
        "id": "acceptance_criteria",
        "name": "Acceptance Criteria are Binary and Testable",
        "description": "...",
        "why": "...",
        "fix": "...",
        "good_example": "AC1: ... AC2: ... AC3: ...",
        "scored_by": "ai",
        "required": true,
        "weight": 1.0
      }
    ]
  },
  "available": [
    { "id": "story-dor",   "level": "story",   "phase": "ready", "name": "Story — Definition of Ready (Base)" },
    { "id": "feature-dor", "level": "feature", "phase": "ready", "name": "Feature — Definition of Ready (Base)" },
    { "id": "epic-dor",    "level": "epic",    "phase": "ready", "name": "Epic — Definition of Ready" },
    { "id": "defect-dor",  "level": "defect",  "phase": "ready", "name": "Defect — Definition of Ready" }
  ],
  "domains": [
    { "id": "data",            "name": "Data & Reporting",        "is_placeholder": false, "levels": ["story", "feature"] },
    { "id": "capmkts",         "name": "Capital Markets",         "is_placeholder": true,  "levels": ["story", "feature"] },
    { "id": "sf-origination",  "name": "Single Family Origination","is_placeholder": true, "levels": ["story", "feature"] },
    { "id": "mf-servicing",    "name": "Multifamily Servicing",   "is_placeholder": true,  "levels": ["story", "feature"] },
    { "id": "risk",            "name": "Risk & Compliance",       "is_placeholder": true,  "levels": ["story", "feature"] }
  ]
}
```

### GET /api/quality/uploads

List uploads eligible for quality scoring (must have at least one saved classification).

**Response:**
```json
{
  "uploads": [
    { "upload_id": 3, "filename": "sprint-backlog.csv", "uploaded_at": "2026-04-03T10:00:00", "story_count": 99, "team_count": 5 }
  ]
}
```

### GET /api/quality/team-of-teams?upload_id=N

Return distinct Team-of-Teams values for an upload. Strict-match only — does NOT fall back to subcategory keywords.

### GET /api/quality/teams?upload_id=N&team_of_teams=X

Return teams in an upload, optionally filtered by Team of Teams.

### POST /api/quality/score

Start a background scoring job.

**Request:**
```json
{
  "upload_id": 3,
  "teams": ["Data Services"],
  "rubric_id": "story-dor",
  "domain": "data"
}
```

| Field | Description |
|-------|-------------|
| `upload_id` | Required. Which upload to score. |
| `teams` | Optional array; omit or `[]` to score all teams. |
| `rubric_id` | Composite id, OR base id with `domain` supplied separately. |
| `domain` | Optional. Layers a domain extension on top of the rubric. |

Legacy: `domain=data_reporting` (no `rubric_id`) still works — treated as `story-dor`.

**Response:**
```json
{ "job_id": "a3f2c1b4", "job_number": 1, "total": 5, "rubric_id": "story-dor:data" }
```

### GET /api/quality/job/\<job_id\>

Poll status of a running scoring job.

**Response:**
```json
{
  "status": "running",
  "job_number": 1,
  "progress": 3,
  "total": 5,
  "results": [
    {
      "classification_id": 42,
      "story_title": "...",
      "team": "Data Services",
      "story_id": "STR-1001",
      "rubric_id": "story-dor:data",
      "rubric_level": "story",
      "rubric_phase": "ready",
      "scoring_mode": "balanced",
      "band": "needs_work",
      "overall_score": 71.4,
      "passed_count": 7,
      "total_count": 10,
      "criteria": {
        "acceptance_criteria": { "pass": true },
        "data_quality":        { "pass": false, "fix": "Add row-count tolerance and null checks." }
      }
    }
  ],
  "error": null
}
```

`status` values: `pending`, `running`, `complete`, `error`.
`band` values: `ready`, `needs_work`, `not_ready` — derived from rubric thresholds, including the `all_required_pass` rule.

### GET /api/quality/results

Return saved scoring results for an upload (or specific run).

**Query Parameters:**
| Param | Description |
|-------|-------------|
| `upload_id` | Required (or `run_id`). |
| `run_id` | Optional — fetch a specific historical run. |
| `teams` | Optional comma-separated list. |
| `rubric_id` | Composite id; defaults to `story-dor`. |
| `domain` | Optional split form. |

### GET /api/quality/export

Same parameters as `/results`. Returns a CSV download with one row per scored story plus per-criterion PASS/FAIL columns.

### GET /api/quality/history

List all completed scoring runs for the current upload (or all uploads).

### DELETE /api/quality/history/\<run_id\>

Delete a scoring run and its row-level scores.

### POST /api/quality/rewrite

Generate a "what good looks like" rewrite for a single story, addressing the criteria that failed in the most recent score. Cached in-memory by `(classification_id, rubric_id)` so re-clicks are free within a process lifetime.

**Request:**
```json
{
  "classification_id": 42,
  "rubric_id": "story-dor",
  "domain": "data",
  "force": false
}
```

`force: true` bypasses the cache and re-generates.

**Response:**
```json
{
  "rewritten": "**Acceptance Criteria are Binary and Testable**\nAC1: ...\nAC2: ...\n\n**Output Artifact Defined**\nDashboard: ...",
  "title": "Build delinquency dashboard",
  "cached": false
}
```

The output structure is rubric-driven — one section per Definition-of-Ready criterion that the rewrite addresses. Each section uses the criterion's `good_example` as guidance.

### POST /api/quality/chat

Continue an iterative rewrite session.

**Request:**
```json
{
  "classification_id": 42,
  "rubric_id": "story-dor:data",
  "messages": [
    { "role": "assistant", "content": "..." },
    { "role": "user",      "content": "The source table is dw.loan_performance in EDW" }
  ]
}
```

`messages` is the full conversation array. The original story is supplied via system prompt; do not include it in `messages`.

**Response:**
```json
{ "reply": "**As a** Senior Risk Analyst\n**I need** ...\n\n**Source Data**\ndw.loan_performance ..." }
```

---

## Domain Extension Editor

Endpoints powering the `/quality-domains` page — let domain stewards review, edit, and reset extension JSON files without touching the filesystem.

### GET /api/quality/extension

Load the raw JSON of a domain extension for editing.

**Query Parameters:**
| Param | Description |
|-------|-------------|
| `domain` | Domain id (`data`, `capmkts`, …). Required. |
| `level` | One of `story`, `feature`, `epic`, `defect`. Required. |

**Response:**
```json
{
  "domain": "capmkts",
  "level":  "story",
  "path":   "domains/capmkts/story-extension.json",
  "has_backup": false,
  "extension": {
    "id": "story-dor:capmkts",
    "level": "story",
    "domain": "capmkts",
    "name": "Story DoR — Capital Markets Extensions (Starter Draft)",
    "is_placeholder": true,
    "placeholder_note": "Starter content. Replace with real CapMkts criteria.",
    "criteria": [ /* ... */ ]
  }
}
```

`has_backup` indicates whether `<path>.bak` exists, so the UI knows whether to offer a Reset button. Returns `404` if the extension does not exist (the UI then offers a "Create extension" flow).

### PUT /api/quality/extension

Save (overwrite) a domain extension. Validates structure, backs up the previous file to `<path>.bak`, writes the new content, and invalidates the in-process rubric cache.

**Request:**
```json
{
  "domain": "capmkts",
  "level":  "story",
  "extension": {
    "name": "...",
    "description": "...",
    "is_placeholder": false,
    "criteria": [ /* full criteria array */ ]
  }
}
```

**Validation:** `extension.criteria` must be a list. Each criterion needs a non-empty `id` and `name`. Duplicate ids within an extension are rejected. The `domain` and `level` fields on the saved JSON are auto-stamped from the request.

**Response:**
```json
{ "success": true, "path": "domains/capmkts/story-extension.json" }
```

**Path safety:** the editor path resolution rejects `..`, `/` in the domain id, empty values, and any level outside `{story, feature, epic, defect}`. Edits cannot escape `rubrics/domains/`.

### POST /api/quality/extension/reset

Restore a domain extension from its `.bak` backup, if one exists.

**Request:**
```json
{ "domain": "capmkts", "level": "story" }
```

**Response:**
```json
{ "success": true }
```

Returns `404` if no backup exists for that extension.
