# Vehicle Movements API

Vehicle in/out counting for a location. Independent of the ANPR module — these rows
come from whatever counts vehicles at a site, whether or not plate recognition is
involved.

- **Base path:** `/api/v1/vehicle-movements`
- **Auth:** Bearer JWT on every endpoint (`Authorization: Bearer <access_token>`)
- **Added in migration:** `k5e6f7g8h9i0_add_vehicle_movements`
- **Source:** [`routes/vehicle_movement.py`](../src/app/api/v1/routes/vehicle_movement.py)

---

## 1. Why this module exists

`anpr_records` already stores a timestamp, location, vehicle type and IN/OUT
direction — but every row there is tied to a plate detection, and the table only
has data where ANPR hardware runs. `vehicle_movements` records the same movement
without requiring a plate, so a site can be counted by a beam, a loop, a camera
line-cross, or an operator, and still feed the same screen.

**Row grain is one vehicle movement, not a period total.** A row is a single IN or
a single OUT. Totals for any window are a `COUNT` over the table, which means a
period's figures can always be drilled back down to the movements that produced
them. The `in_count` / `out_count` fields in the response are derived per row so
the frontend can render In and Out columns directly.

---

## 2. Database table

`vehicle_movements`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | no | `uuid4()` | Primary key |
| `location_id` | `uuid` | no | — | FK → `locations.id` |
| `camera_id` | `uuid` | yes | — | FK → `cameras.id`. Null when counting at the gate rather than per camera |
| `device_id` | `uuid` | yes | — | FK → `devices.id`. For traceability |
| `vehicle_type` | `vehicle_type_enum` | no | `'CAR'` | `CAR` \| `TWO_WHEELER` |
| `direction` | `vehicle_movement_direction_enum` | no | — | `IN` \| `OUT` |
| `number_plate` | `varchar(30)` | yes | — | Optional; filled when the source knows it |
| `recorded_at` | `timestamptz` | no | `now()` | When the vehicle **moved**, not when the row was written |
| `created_at` | `timestamptz` | no | `now()` | |
| `updated_at` | `timestamptz` | no | `now()` | |

### Indexes

| Index | Columns |
|---|---|
| `vehicle_movements_pkey` | `id` |
| `ix_vehicle_movements_location_id` | `location_id` |
| `ix_vehicle_movements_camera_id` | `camera_id` |
| `ix_vehicle_movements_recorded_at` | `recorded_at` |
| `ix_vehicle_movements_location_recorded` | `(location_id, recorded_at DESC)` |
| `ix_vehicle_movements_camera_recorded` | `(camera_id, recorded_at DESC)` |

The two composite indexes match the list endpoint's `ORDER BY recorded_at DESC, id DESC`
exactly, so paging stays on an index scan as the table grows. Confirmed in the plan:

```
Bitmap Index Scan on ix_vehicle_movements_location_recorded
```

### Enums

```
vehicle_type_enum                 = 'CAR' | 'TWO_WHEELER'   (shared with anpr_records)
vehicle_movement_direction_enum   = 'IN'  | 'OUT'           (new, module-specific)
```

`direction` uses its own PostgreSQL enum rather than reusing `anpr_direction_enum`
so this module and ANPR can change on their own schedules.

---

## 3. Permissions

Checked with `PermissionChecker` on every endpoint.

| Permission key | Used by |
|---|---|
| `vehicle_movements:view` | `GET /` , `GET /{id}` |
| `vehicle_movements:create` | `POST /` |
| `vehicle_movements:edit` | `PATCH /{id}` |
| `vehicle_movements:delete` | `DELETE /{id}` |
| `vehicle_movements:export` | reserved — no endpoint yet |

> These are registered in `scripts/seed.py`. **Run `python scripts/seed.py` once**
> or every endpoint returns `403`.

### Location scoping

Every endpoint is scoped to the caller's locations:

- Super Admin resolves to `None` → sees all locations.
- A scoped user resolves to a set of location IDs → sees only those.
- A user with **no** scopes resolves to an empty set → sees **nothing**.

An explicit `location_id` is validated with `verify_location_in_scope` and returns
`403` when outside the caller's scope. A `camera_id` outside scope simply yields no
rows rather than an error, because the location filter still applies underneath it.

---

## 4. Endpoints

### 4.1 `GET /api/v1/vehicle-movements` — list with filters and totals

**Purpose.** The single call the frontend list screen makes. Returns one page of
movements plus In/Out totals for the **entire filtered window**, so the summary
cards stay still while the user pages through the table.

**Permission:** `vehicle_movements:view`

#### Query parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `page` | `integer` ≥ 1 | `1` | Page number |
| `page_size` | `integer` 1–100 | `20` | Rows per page |
| `quick_range` | `enum` | — | `today` \| `yesterday` \| `last_7_days` \| `last_30_days` \| `this_month`. Resolved **server-side in IST**. Ignored when `from_date` or `to_date` is given |
| `from_date` | `datetime` (ISO 8601) | — | Inclusive lower bound on `recorded_at` |
| `to_date` | `datetime` (ISO 8601) | — | Inclusive upper bound on `recorded_at` |
| `area_id` | `uuid` | — | Narrow to all locations in an area |
| `location_id` | `uuid` | — | Single location. `403` if outside your scope |
| `camera_id` | `uuid` | — | Single camera |
| `vehicle_type` | `enum` | — | `CAR` \| `TWO_WHEELER` |
| `direction` | `enum` | — | `IN` \| `OUT` |
| `number_plate` | `string` | — | Case-insensitive partial match |

**Date precedence.** An explicit `from_date` / `to_date` always beats `quick_range`.
This is what lets the UI show "Today" selected in the dropdown while still honouring
a hand-typed range.

**Why `quick_range` is server-side.** `today` means today in **IST**, regardless of
where the browser is. Computing the window in the browser means a viewer in another
timezone silently requests a different day than their dropdown says — a bug that
exists elsewhere in this codebase and is deliberately avoided here.

#### Response `200` — `VehicleMovementListResponse`

| Field | Type | Description |
|---|---|---|
| `items` | `VehicleMovementResponse[]` | This page of rows, newest first |
| `total` | `integer` | Rows matching the filters (all pages) |
| `page` | `integer` | Echo of the requested page |
| `page_size` | `integer` | Effective page size after clamping |
| `total_pages` | `integer` | `ceil(total / page_size)` |
| `summary` | `VehicleMovementSummary` | Totals for the whole filtered window |

**`VehicleMovementSummary`**

| Field | Type | Description |
|---|---|---|
| `total_in` | `integer` | Count of `IN` rows in the window, all vehicle types |
| `total_out` | `integer` | Count of `OUT` rows in the window, all vehicle types |
| `net` | `integer` | `total_in − total_out`. Negative is normal for a window that opens mid-day |
| `car` | `VehicleMovementTypeTotals` | Same three figures for `CAR` only |
| `two_wheeler` | `VehicleMovementTypeTotals` | Same three figures for `TWO_WHEELER` only |

**`VehicleMovementTypeTotals`**

| Field | Type | Description |
|---|---|---|
| `total_in` | `integer` | `IN` rows of this vehicle type |
| `total_out` | `integer` | `OUT` rows of this vehicle type |
| `net` | `integer` | `total_in − total_out` |

`car` and `two_wheeler` always sum to the three combined fields above, so the
Car and Two Wheeler cards and the overall figures come from one request. The
combined fields are unchanged — the per-type objects are additions.

**`VehicleMovementResponse`**

| Field | Type | Null | Description |
|---|---|---|---|
| `id` | `uuid` | no | |
| `created_at` | `datetime` | no | Row written |
| `updated_at` | `datetime` | no | Row last edited |
| `location_id` | `uuid` | no | |
| `location_name` | `string` | yes | Joined from `locations` |
| `camera_id` | `uuid` | yes | |
| `camera_label` | `string` | yes | Joined from `cameras.position_label` |
| `device_id` | `uuid` | yes | |
| `vehicle_type` | `string` | no | `CAR` \| `TWO_WHEELER` |
| `direction` | `string` | no | `IN` \| `OUT` |
| `number_plate` | `string` | yes | |
| `recorded_at` | `datetime` | no | UTC, ISO 8601 with `Z` |
| `in_count` | `integer` | no | `1` when direction is `IN`, else `0` |
| `out_count` | `integer` | no | `1` when direction is `OUT`, else `0` |

> `in_count` and `out_count` are derived from `direction`, so a row can never claim
> to be both. Render them straight into the In / Out columns.

#### Example

```http
GET /api/v1/vehicle-movements?quick_range=today&page_size=3
Authorization: Bearer <token>
```

```json
{
  "items": [
    {
      "id": "b7c4b13f-297c-423e-837b-065188e427e0",
      "created_at": "2026-08-26T14:13:44.708276Z",
      "updated_at": "2026-08-26T14:13:44.708276Z",
      "location_id": "95343ff5-4028-4155-8a5d-22cbb39774c6",
      "location_name": "[DEMO] Alpha City Mall",
      "camera_id": null,
      "camera_label": null,
      "device_id": null,
      "vehicle_type": "CAR",
      "direction": "OUT",
      "number_plate": null,
      "recorded_at": "2026-08-26T07:40:00Z",
      "in_count": 0,
      "out_count": 1
    },
    {
      "id": "1e353aa0-7636-4614-802e-8a67b58b345f",
      "created_at": "2026-08-26T14:11:12.572045Z",
      "updated_at": "2026-08-26T14:11:12.572045Z",
      "location_id": "95343ff5-4028-4155-8a5d-22cbb39774c6",
      "location_name": "[DEMO] Alpha City Mall",
      "camera_id": "8154ab9a-22a8-48a9-9e0d-be2462c3f781",
      "camera_label": "Ground - Zone A Cam",
      "device_id": null,
      "vehicle_type": "TWO_WHEELER",
      "direction": "IN",
      "number_plate": null,
      "recorded_at": "2026-08-26T07:10:00Z",
      "in_count": 1,
      "out_count": 0
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 3,
  "total_pages": 2,
  "summary": {
    "total_in": 238,
    "total_out": 207,
    "net": 31,
    "car":         { "total_in": 129, "total_out": 113, "net": 16 },
    "two_wheeler": { "total_in": 109, "total_out": 94,  "net": 15 }
  }
}
```

---

### 4.2 `POST /api/v1/vehicle-movements` — record a movement

**Purpose.** Write one movement. Used by whatever counts vehicles — an operator
screen, or a device posting over HTTP.

**Permission:** `vehicle_movements:create`

#### Request body — `VehicleMovementCreate`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `location_id` | `uuid` | **yes** | — | `403` if outside your scope |
| `direction` | `enum` | **yes** | — | `IN` \| `OUT` |
| `vehicle_type` | `enum` | no | `CAR` | `CAR` \| `TWO_WHEELER` |
| `camera_id` | `uuid` | no | `null` | |
| `device_id` | `uuid` | no | `null` | |
| `number_plate` | `string` (≤ 30) | no | `null` | |
| `recorded_at` | `datetime` (ISO 8601) | no | server `now()` | Supply when a device replays movements it buffered while offline |

#### Response `201` — `VehicleMovementResponse`

Same shape as the list item, including `location_name` and `camera_label`, so a row
created from the UI can be rendered without a second request.

#### Example

```http
POST /api/v1/vehicle-movements
Authorization: Bearer <token>
Content-Type: application/json

{
  "location_id": "95343ff5-4028-4155-8a5d-22cbb39774c6",
  "camera_id": "8154ab9a-22a8-48a9-9e0d-be2462c3f781",
  "vehicle_type": "CAR",
  "direction": "IN",
  "number_plate": "GJ01AB1234",
  "recorded_at": "2026-08-26T10:15:00+05:30"
}
```

```json
{
  "id": "cd9c6345-8d3a-4036-ab07-533d58a19739",
  "created_at": "2026-08-26T14:11:12.461437Z",
  "updated_at": "2026-08-26T14:11:12.461437Z",
  "location_id": "95343ff5-4028-4155-8a5d-22cbb39774c6",
  "location_name": "[DEMO] Alpha City Mall",
  "camera_id": "8154ab9a-22a8-48a9-9e0d-be2462c3f781",
  "camera_label": "Ground - Zone A Cam",
  "device_id": null,
  "vehicle_type": "CAR",
  "direction": "IN",
  "number_plate": "GJ01AB1234",
  "recorded_at": "2026-08-26T04:45:00Z",
  "in_count": 1,
  "out_count": 0
}
```

> `recorded_at` is stored and returned in **UTC**. `10:15 +05:30` comes back as
> `04:45Z`. Convert for display.

---

### 4.3 `POST /api/v1/vehicle-movements/import` — upload a daily report

**Purpose.** Upload the daily Summary Report spreadsheet and store its movements
in one request. Same parser as the CLI script — they share
`services/vehicle_movement_import.py`, so the two can never disagree.

**Permission:** `vehicle_movements:create`
**Content type:** `multipart/form-data`

#### Form fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | file (`.xlsx` / `.xlsm`) | **yes** | — | The Summary Report. Max 8 MB |
| `location_id` | `uuid` | **yes** | — | Site these movements belong to. The spreadsheet contains no location, so it must be given here. `400` if it does not exist, `403` if outside your scope |
| `report_date` | `date` (`YYYY-MM-DD`) | **yes** | — | The day the report covers. Taken from the payload, never the filename |
| `replace` | `boolean` | no | `false` | Replace this location's movements for that date |
| `camera_id` | `uuid` | no | `null` | Applied to every imported row |

**Why `report_date` is a payload field.** The filename is not trustworthy — the
sample file was named `25th Aug 2026` but was generated on the 26th. Requiring the
date explicitly means a whole day can never be filed under the wrong date because
an export template was stale.

#### Response `201`

| Field | Type | Description |
|---|---|---|
| `success` | `boolean` | Always `true` on 201 |
| `location_id` | `string` | Echo of the location written to |
| `report_date` | `string` | Echo of the date written to |
| `imported` | `integer` | Movements inserted |
| `replaced` | `integer` | Existing rows deleted first (`0` unless `replace=true`) |
| `sheets` | `array` | Per-sheet breakdown — see below |
| `warnings` | `string[]` | Skipped rows, and any disagreement with the sheet's own Total row |

Each entry in `sheets`: `sheet`, `vehicle_type`, `total_in`, `total_out`,
`movements`, `rows_read`.

```json
{
  "success": true,
  "location_id": "74d2b082-dfae-486b-a8d8-91439d5133a7",
  "report_date": "2026-08-25",
  "imported": 445,
  "replaced": 0,
  "sheets": [
    { "sheet": "Two Wheeler",  "vehicle_type": "TWO_WHEELER",
      "total_in": 109, "total_out": 94,  "movements": 203, "rows_read": 201 },
    { "sheet": "Four Wheeler", "vehicle_type": "CAR",
      "total_in": 129, "total_out": 113, "movements": 242, "rows_read": 240 }
  ],
  "warnings": [
    "Four Wheeler: Total row says OUT=51 but the rows contain 113 — importing the 113 actual rows"
  ]
}
```

#### Errors

| Code | When |
|---|---|
| `400` | Day already imported and `replace` not sent; unknown `location_id`; not an `.xlsx`; empty or oversized file; no usable sheets; no movement rows |
| `403` | `location_id` outside your scope, or missing permission |
| `422` | `report_date` not a valid date, or a required field missing |

#### Example

```bash
curl -X POST "$API/api/v1/vehicle-movements/import" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@Summary Report _ 25th Aug 2026.xlsx" \
  -F "location_id=74d2b082-dfae-486b-a8d8-91439d5133a7" \
  -F "report_date=2026-08-25"
```

The whole import is one transaction — a failure part-way leaves nothing behind.

---

### 4.4 `GET /api/v1/vehicle-movements/{movement_id}` — fetch one

**Purpose.** Read a single movement, e.g. to populate an edit form.

**Permission:** `vehicle_movements:view`

| Parameter | Type | In |
|---|---|---|
| `movement_id` | `uuid` | path |

**Response `200`** — `VehicleMovementResponse` (identical shape to a list item).

---

### 4.5 `PATCH /api/v1/vehicle-movements/{movement_id}` — correct a movement

**Purpose.** Fix a miscounted or mistyped row.

**Permission:** `vehicle_movements:edit`

#### Request body — `VehicleMovementUpdate`

All fields optional; omitted fields are left unchanged.

| Field | Type | Description |
|---|---|---|
| `direction` | `enum` | `IN` \| `OUT` |
| `vehicle_type` | `enum` | `CAR` \| `TWO_WHEELER` |
| `number_plate` | `string` (≤ 30) | |
| `recorded_at` | `datetime` | |

**Response `200`** — the updated `VehicleMovementResponse`.

> **Known limitation.** `BaseRepository.update` strips `null` values before writing,
> so `{"number_plate": null}` cannot currently clear the field. This is codebase-wide
> behaviour affecting all 23 PATCH/PUT routes, not specific to this module.

---

### 4.6 `DELETE /api/v1/vehicle-movements/{movement_id}` — remove a movement

**Purpose.** Remove a row recorded in error. This is a **hard delete** — the row is
gone, not soft-deleted.

**Permission:** `vehicle_movements:delete`

**Response `200`** — `MessageResponse`

```json
{ "message": "Vehicle movement deleted successfully", "success": true }
```

---

## 5. Status codes

| Code | When | Body |
|---|---|---|
| `200` | Success | As documented above |
| `201` | Created | `VehicleMovementResponse` |
| `401` | Missing or invalid token | `{"detail": "Not authenticated"}` |
| `403` | Missing permission, or `location_id` outside your scope | `{"success": false, "detail": "..."}` |
| `404` | Unknown `movement_id` | `{"success": false, "detail": "Vehicle movement not found"}` |
| `422` | Invalid parameter — bad enum, unparseable date, `page_size` out of range | FastAPI validation array |

Bad dates return `422`, not `500`. Several older routes in this codebase parse dates
by hand and return `500` instead; this module types them as `datetime` and lets
FastAPI validate.

```json
{"detail": [{
  "type": "enum",
  "loc": ["query", "direction"],
  "msg": "Input should be 'IN' or 'OUT'",
  "input": "UP"
}]}
```

---

## 6. Verified behaviour

Exercised against the running API with five rows at `[DEMO] Alpha City Mall`
(3 IN, 2 OUT; 3 CAR, 2 TWO_WHEELER):

| Request | `total` | `total_in` | `total_out` |
|---|---|---|---|
| no filters | 5 | 3 | 2 |
| `?direction=IN` | 3 | 3 | 0 |
| `?direction=OUT` | 2 | 0 | 2 |
| `?vehicle_type=CAR` | 3 | 1 | 2 |
| `?vehicle_type=TWO_WHEELER` | 2 | 2 | 0 |
| `?quick_range=yesterday` | 0 | 0 | 0 |
| `?number_plate=GJ01` | 1 | 1 | 0 |

A user whose scope resolves to an empty set receives `total=0` — the location filter
is never dropped.

---

## 7. Daily Excel import

`scripts/import_vehicle_movements.py` loads a daily *Summary Report* spreadsheet
into this table.

### Expected file

One sheet per vehicle type, one row per movement:

```
A            B                 C
Hour         Two Wheeler in    Two Wheeler Out
10:00:10     In
10:15:24                       Out
13:47:43     In                Out      <- one IN *and* one OUT
Total        109               94       <- skipped, used to validate
```

- **Sheet name → vehicle type.** A name containing `two` / `2 wheel` / `bike` maps to
  `TWO_WHEELER`; `four` / `4 wheel` / `car` maps to `CAR`. Sheets matching neither are
  skipped with a warning.
- **A row with both In and Out is two movements** — one entering and one leaving at
  the same second. This reading is what makes the computed totals match the sheet's
  own `Total` row.
- **The date comes from the filename**, e.g. `Summary Report _ 25th Aug 2026.xlsx`.
  Ordinal suffixes are optional and the month may be long or short. Override with
  `--date YYYY-MM-DD`.
- **Times are read as IST** and stored in UTC.
- **The location is not in the file** and must be supplied.

### Usage

```bash
# always dry-run first
python scripts/import_vehicle_movements.py \
    "Summary Report _ 25th Aug 2026.xlsx" \
    --location-name "Open Ground Jagatpur" --dry-run

# then import
python scripts/import_vehicle_movements.py \
    "Summary Report _ 25th Aug 2026.xlsx" \
    --location-name "Open Ground Jagatpur"

# re-import the same day after a corrected file
python scripts/import_vehicle_movements.py <file> --location-name <name> --replace
```

Inside Docker: `docker compose exec -e PYTHONPATH=/app app python scripts/...`

| Option | Description |
|---|---|
| `xlsx_path` | Path to the file (positional, required) |
| `--location-id` | Location UUID. Mutually exclusive with `--location-name` |
| `--location-name` | Partial name match. Fails listing candidates if ambiguous |
| `--camera-id` | Optional camera applied to every imported row |
| `--date` | `YYYY-MM-DD`, overrides the filename |
| `--replace` | Delete this location's movements for that date first |
| `--dry-run` | Report what would happen, write nothing |

### Safety

- **Re-running without `--replace` refuses** rather than doubling the data:
  `445 movements already exist for … on 2026-08-25.`
- `--replace` is scoped to that location, that date and the vehicle types present in
  the file, so it cannot touch another day or another site.
- Everything runs in one transaction — a failure part-way leaves nothing behind.

### Validation

The script compares the sheet's `Total` row against the rows actually present and
warns on disagreement, importing the real rows. The sample file showed this:

```
Sheet 'Two Wheeler'  -> TWO_WHEELER   IN=109  OUT=94    (203 movements)
Sheet 'Four Wheeler' -> CAR           IN=129  OUT=113   (242 movements)
WARNING  Total row says OUT=51 but the rows contain 113 — importing the 113 actual rows
```

Two Wheeler matched exactly. **Four Wheeler's stated OUT total of 51 disagrees with
the 113 `Out` rows in the sheet** — most likely a `SUM` range that was not extended
when rows were added. Worth checking at source, since that spreadsheet total is
presumably being read by someone.

The script exits `0` on a clean import, `1` when it imported but found a total
mismatch, and `2` on an error — so a cron job can alert on `1`.

---

## 8. Not built yet

- **No device ingest.** Nothing writes to this table in real time. If movements
  should arrive from edge devices over MQTT, that needs a topic handler in
  `mqtt/client.py` and a Celery task, following the `tasks/parking_scan.py` pattern.
- **No CSV/Excel export.** The `vehicle_movements:export` permission is reserved but
  unused.
- **No tests.** Consistent with the rest of the repository, which has none.

---

## 9. Files

| Path | Role |
|---|---|
| `src/app/models/vehicle_movement.py` | Table definition |
| `src/app/schemas/vehicle_movement.py` | Request/response models, `build_movement_response` |
| `src/app/repositories/vehicle_movement.py` | Filtered queries, direction totals |
| `src/app/services/vehicle_movement.py` | Business layer |
| `src/app/api/v1/routes/vehicle_movement.py` | Endpoints, quick-range resolution |
| `alembic/versions/k5e6f7g8h9i0_add_vehicle_movements.py` | Migration |
| `src/app/core/constants.py` | `MovementDirection`, five permission keys |
| `scripts/seed.py` | Permission seeding |
| `scripts/import_vehicle_movements.py` | Daily Excel import (CLI) |
| `src/app/services/vehicle_movement_import.py` | Shared workbook parsing and storage |
