# Map Zone Storage

Last updated: 2026-05-13

## Overview

`map_zones` is the single source of truth for all spatial data in LawnBerry.  Every
zone — whether it defines the outer boundary, an obstacle to avoid, or a specific mow
area — is a row in this table differentiated by the `zone_kind` column.  Non-spatial
configuration (tile provider, API key, named markers) lives in a separate `map_config`
table.

---

## Table: `map_zones`

| Column | Type | Description |
|---|---|---|
| `id` | TEXT (UUID) | Primary key |
| `name` | TEXT | Human-readable label |
| `polygon_json` | TEXT | GeoJSON-encoded polygon (coordinates array) |
| `priority` | INTEGER | Render/evaluation order (lower = higher priority) |
| `exclusion_zone` | INTEGER (bool) | Legacy column; superseded by `zone_kind` |
| `zone_kind` | TEXT | Discriminator: `"boundary"` \| `"exclusion"` \| `"mow"` |
| `created_at` | TEXT | ISO-8601 creation timestamp |

### `zone_kind` values

| Value | Meaning |
|---|---|
| `boundary` | Outer operating boundary — the mower must not cross this polygon's perimeter. |
| `exclusion` | No-go area inside the boundary (obstacles, flowerbeds, etc.). Subtracted from coverage paths. |
| `mow` | Explicit mow zone inside the boundary. Path planner restricts coverage to this polygon. |

A lawn without any `mow` zones uses the `boundary` polygon minus all `exclusion` polygons
as the mow area.

---

## Table: `map_config`

Non-spatial fields that do not belong to individual zones remain in `map_config`.

| Column | Type | Description |
|---|---|---|
| `provider` | TEXT | Tile provider identifier (`"google"`, `"osm"`, etc.) |
| `api_key` | TEXT | Tile API key (stored encrypted) |
| `markers` | TEXT | JSON array of named point markers |
| `updated_at` | TEXT | ISO-8601 timestamp of last configuration write |
| `updated_by` | TEXT | User/service that performed the last write |

`GET /api/v2/map/configuration` returns the merged envelope with an extra synthetic field
`_zones_source: "map_zones"` to signal to clients that zone data is fetched separately
via the zones endpoints, not embedded in the configuration response.

---

## Zone API Endpoints

All endpoints are under the canonical `/api/v2/` surface.

| Method | Path | Status codes | Notes |
|---|---|---|---|
| GET | `/api/v2/map/zones` | 200 | Returns all zones as an array |
| POST | `/api/v2/map/zones?bulk=true` | 200, 400 | Bulk replace — **requires `?bulk=true`**; returns 400 without the query param |
| GET | `/api/v2/map/zones/{id}` | 200, 404 | Per-zone lookup |
| POST | `/api/v2/map/zones/{id}` | 201, 409, 422 | Atomic single-zone create; 409 if `id` already exists |
| PUT | `/api/v2/map/zones/{id}` | 200, 404 | Update a single zone |
| DELETE | `/api/v2/map/zones/{id}` | 204, 404 | Delete a single zone |

**Bulk POST** (`?bulk=true`) performs an atomic replace of all zones in one transaction.
It broadcasts a `planning.zone.changed` WebSocket event on success.

**Single-zone POST** (`POST /api/v2/map/zones/{id}`) is the preferred path for creating
one zone without disturbing others.  Returns 409 if the ID is already in use; callers
should use PUT to update existing zones.

---

## Deprecated / Gone Endpoints

`PUT /api/v2/map/configuration` previously accepted `zones`, `boundaries`, and
`exclusion_zones` fields in the request body.  These fields are **no longer honoured**:
the endpoint returns **410 Gone** if the body contains any of them.  Use the dedicated
zone endpoints instead.

---

## Audit Logging

Every zone mutation is recorded via `persistence.add_audit_log`.  The `action` field
uses dot-namespaced names; the `details` dict carries identifiers and a human-readable
summary.

| Action | Trigger | Example `details` |
|---|---|---|
| `map.zone.created` | Successful `POST /api/v2/map/zones/{id}` | `{"zone_id": "…", "name": "Front lawn", "zone_kind": "mow"}` |
| `map.zone.updated` | Successful `PUT /api/v2/map/zones/{id}` | `{"zone_id": "…", "fields_changed": ["polygon_json"]}` |
| `map.zone.deleted` | Successful `DELETE /api/v2/map/zones/{id}` | `{"zone_id": "…", "name": "Old exclusion"}` |
| `map.zones.bulk_replace` | Successful `POST /api/v2/map/zones?bulk=true` | `{"zone_count": 5}` |

Audit records are append-only and are not exposed through the public API.

---

## Developer Notes

- `MapRepository` (`backend/src/core/map_repository.py`) is the only layer that reads
  from or writes to `map_zones`.  Do not query the table directly from service code.
- Tests that create zones should pass `zone_kind` explicitly; omitting it falls back to
  `"mow"` for backward compatibility but this default may be tightened in future.
- The cleanup script `scripts/cleanup_test_fixtures.py` can be used to purge rows
  inserted by test runs from the production database.  Review its dry-run output before
  executing with `--apply`.
