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
  "story_id": "PROJ-123"
}
```

All three context fields (`epic`, `parent_feature`, `story_id`) are optional. When provided, they are saved alongside the AI classification in the database.

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
      "has_results": true
    }
  ]
}
```

`saved_count` — actual stories saved to the classifications table (reliable saved/unsaved indicator).
`has_results` — `true` if AI results are stored and can be recovered without re-running the AI.

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
  "target_fields": [{"key": "title", "label": "Title", "required": true}],
  "sample_rows": [{"story title": "Fix bug", "description": "..."}],
  "total_rows": 100,
  "preview_id": "uuid"
}
```

**Recognized column names for ID fields:**

| Field | Recognized headers |
|-------|-------------------|
| `story_id` | Issue key, Story ID, Key, Ticket, JIRA ID, Item ID |
| `feature_id` | Feature ID, Feature key, Parent ID, Parent key |
| `epic_id` | Epic ID, Epic key, Epic link, Initiative ID |

### POST /api/bulk-verify

Upload a file and AI-classify every story. All uploads process asynchronously.

**Request:** `multipart/form-data` with `file` field (CSV or XLSX). Optionally include `preview_id` and `column_mappings` (JSON) from the preview step.

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
      "file_category": "New Feature",
      "ai_category": "KTLO",
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
  "epic_id": "PROJ-50"
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
