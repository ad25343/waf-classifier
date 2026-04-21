# WAF Classifier — API Reference

Base URL: `http://localhost:8080`

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

## Story Quality

### GET /api/quality/rubric

Return the Definition of Ready rubric for a given domain.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `domain` | string | Optional. Default: `data_reporting`. |

**Response:**
```json
{
  "rubric": {
    "id": "data_reporting",
    "name": "Data & Reporting",
    "full_name": "Data, Reporting & Analytics — Definition of Ready",
    "source": "GSE-MF Story Excellence Playbook v1.0",
    "criteria": [
      {
        "id": "narrative",
        "name": "Narrative Format",
        "description": "Story uses 'As a / I need / So that' format",
        "why": "Anchors work to a stakeholder need and measurable outcome.",
        "good_example": "As a Senior Risk Analyst / I need a portfolio delinquency dashboard / So that ...",
        "fix": "Rewrite as: As a [role] / I need [capability] / So that [outcome]"
      }
    ]
  },
  "domains": [{ "id": "data_reporting", "name": "Data & Reporting" }]
}
```

### GET /api/quality/uploads

List uploads eligible for quality scoring (must have at least one saved classification).

**Response:**
```json
{
  "uploads": [
    {
      "upload_id": 3,
      "filename": "sprint-backlog.csv",
      "uploaded_at": "2026-04-03T10:00:00",
      "story_count": 99,
      "team_count": 5
    }
  ]
}
```

### GET /api/quality/teams

List teams and story counts for a specific upload.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `upload_id` | int | **Required.** |

**Response:**
```json
{ "teams": [{ "name": "Data Services", "count": 5 }] }
```

### POST /api/quality/score

Start a background scoring job for the given upload and teams.

**Request:**
```json
{
  "upload_id": 3,
  "teams": ["Data Services"],
  "domain": "data_reporting"
}
```

`teams` — optional array; omit or pass `[]` to score all teams.

**Response:**
```json
{ "job_id": "a3f2c1b4", "job_number": 1, "total": 5 }
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
  "results": [...],
  "error": null
}
```

`status` values: `pending`, `running`, `complete`, `error`

### GET /api/quality/results

Fetch scored story results. Use either `upload_id` (latest scores for that upload) or `run_id` (exact run).

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `upload_id` | int | Filter by upload (required unless `run_id` provided) |
| `run_id` | string | Load results from a specific run |
| `domain` | string | Default: `data_reporting` |
| `teams` | string | Comma-separated team names (optional filter) |

**Response:**
```json
{
  "results": [
    {
      "classification_id": 42,
      "story_title": "Build delinquency dashboard",
      "team": "Data Services",
      "story_id": "STR-001",
      "overall_score": 66.7,
      "passed_count": 6,
      "total_count": 9,
      "criteria": {
        "narrative": { "pass": true },
        "source_data": { "pass": false, "fix": "Add the source table name and owning system" }
      },
      "scored_at": "2026-04-03T10:15:00",
      "description_empty": false
    }
  ],
  "count": 1
}
```

### GET /api/quality/export

Download scored results as CSV.

**Query Parameters:** Same as `/api/quality/results` (requires `upload_id`).

Returns `text/csv` with columns: Story ID, Story Title, Team, Score %, Passed, Total, one column per criterion (PASS or FAIL: fix text), Scored At.

### GET /api/quality/history

List all scoring runs in reverse chronological order.

**Response:**
```json
{
  "runs": [
    {
      "run_id": "a3f2c1b4",
      "job_number": 1,
      "scored_at": "2026-04-03T10:15:00",
      "upload_id": 3,
      "upload_filename": "sprint-backlog.csv",
      "domain": "data_reporting",
      "teams": ["Data Services"],
      "story_count": 5,
      "avg_score": 44.4,
      "ready_count": 0,
      "needs_work_count": 2,
      "not_ready_count": 3
    }
  ]
}
```

### DELETE /api/quality/history/\<run_id\>

Delete a scoring run and all its associated story scores.

**Response:** `{ "ok": true }`

### POST /api/quality/rewrite

Generate an initial AI story rewrite addressing failing DoR criteria. Only uses information present in the original story; missing information is marked with `[REQUIRED: ...]` placeholders.

**Request:**
```json
{
  "classification_id": 42,
  "domain": "data_reporting"
}
```

**Response:**
```json
{
  "rewritten": "**As a** Senior Risk Analyst\n**I need** ...",
  "title": "Build delinquency dashboard"
}
```

### POST /api/quality/chat

Continue an iterative story rewrite session. Sends the full conversation history to the AI with the original story as fixed context.

**Request:**
```json
{
  "classification_id": 42,
  "domain": "data_reporting",
  "messages": [
    { "role": "assistant", "content": "**As a** Senior Risk Analyst..." },
    { "role": "user", "content": "The source table is dw.loan_performance in EDW" }
  ]
}
```

`messages` — full conversation array in `[{role, content}]` format. The original story is provided via system prompt, not in messages.

**Response:**
```json
{ "reply": "**As a** Senior Risk Analyst\n**I need** ...\n\n**Source Data**\ndw.loan_performance, EDW, nightly refresh..." }
```
