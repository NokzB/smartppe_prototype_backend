# SmartPPE Prototype Backend

FastAPI backend for tracking mine workers' vitals (BPM, temperature) from a
wearable, with role-based dashboards and threshold-based alerting.
Storage is plain JSON files, intentionally, since this is a prototype.

## Project layout

```
smartppe/
├── app/
│   ├── main.py                # FastAPI app assembly
│   ├── config.py              # settings, blocked email domains, default baselines
│   ├── models.py              # Pydantic request/response schemas
│   ├── security.py            # password hashing, JWT, role-based access control
│   ├── storage.py             # JSON read/write layer (locking + atomic writes)
│   ├── services/
│   │   ├── user_service.py    # registration, login lookup, baseline updates
│   │   └── wearable_service.py# ingest readings, compute status, raise alerts
│   └── routers/
│       ├── auth_router.py         # /auth/register, /auth/login
│       ├── wearable_router.py     # /wearable/data
│       └── dashboard_router.py    # /admin/dashboard, /supervisor/dashboard, /alerts
└── data/                       # created automatically: users.json, readings.json, etc.
```

## Running it

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/docs` for interactive Swagger UI — this
alone will save you a lot of manual curl-typing while building the frontend.

## Example flow

**1. Register an admin, a supervisor, and a miner**

```bash
curl -X POST http://127.0.0.1:8000/auth/register -H "Content-Type: application/json" -d '{
  "name": "Thabo", "surname": "Nkosi", "role": "admin",
  "email": "thabo.nkosi@minecorp.co.za", "phone": "0821234567",
  "employee_id": "ADM001", "password": "StrongPass123"
}'

curl -X POST http://127.0.0.1:8000/auth/register -H "Content-Type: application/json" -d '{
  "name": "Lindiwe", "surname": "Dube", "role": "supervisor",
  "email": "lindiwe.dube@minecorp.co.za", "phone": "0827654321",
  "employee_id": "SUP001", "area": "Shaft-A", "password": "StrongPass123"
}'

curl -X POST http://127.0.0.1:8000/auth/register -H "Content-Type: application/json" -d '{
  "name": "Sipho", "surname": "Mokoena", "role": "miner",
  "email": "sipho.mokoena@minecorp.co.za", "phone": "0829998888",
  "employee_id": "MIN001", "area": "Shaft-A", "password": "StrongPass123"
}'
```

A registration with a gmail/yahoo/outlook/etc. address gets rejected with a
422 and a clear message — try it and see.

**2. Log in** (OAuth2 form fields: `username` = email, `password` = password)

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=thabo.nkosi@minecorp.co.za&password=StrongPass123"
```

Copy the `access_token` from the response for the next steps.

**3. Simulate a watch sending a reading**

```bash
curl -X POST http://127.0.0.1:8000/wearable/data -H "Content-Type: application/json" -d '{
  "employee_id": "MIN001", "bpm": 145, "temperature": 38.9, "activity": "stressed"
}'
```

Because 145 BPM / 38.9°C is outside the default baseline, this reading gets
marked `"critical"` and an entry is added to `alerts.json`.

**4. View dashboards** (use the admin/supervisor token in the Authorization header)

```bash
curl http://127.0.0.1:8000/admin/dashboard -H "Authorization: Bearer <TOKEN>"
curl http://127.0.0.1:8000/supervisor/dashboard -H "Authorization: Bearer <TOKEN>"
curl http://127.0.0.1:8000/alerts -H "Authorization: Bearer <TOKEN>"
```

**5. List miners — all, on duty only, or off duty only**

```bash
curl "http://127.0.0.1:8000/admin/miners" -H "Authorization: Bearer <ADMIN_TOKEN>"
curl "http://127.0.0.1:8000/admin/miners?duty=on_duty" -H "Authorization: Bearer <ADMIN_TOKEN>"
curl "http://127.0.0.1:8000/admin/miners?duty=off_duty" -H "Authorization: Bearer <ADMIN_TOKEN>"
```

A miner counts as **on duty** if their wearable has reported a reading within
the last `ACTIVE_THRESHOLD_MINUTES` (default 15, in `config.py`) — no clock-in
button required, since the watch itself is the signal. If they've never
reported, or the trail's gone cold, they show as off duty.

**6. Select a miner to view their full detail** (vitals, status, activity, location)

```bash
curl "http://127.0.0.1:8000/admin/miners/MIN001" -H "Authorization: Bearer <ADMIN_TOKEN>"
```

Location comes from the wearable payload — send it as part of the reading:

```bash
curl -X POST http://127.0.0.1:8000/wearable/data -H "Content-Type: application/json" -d '{
  "employee_id": "MIN001", "bpm": 78, "temperature": 36.8,
  "activity": "moderate", "location": "Shaft-A, Level 3"
}'
```

**7. Set a real baseline for an employee** (from their actual resting vitals)

```bash
curl -X PUT http://127.0.0.1:8000/admin/baseline/MIN001 \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{
  "bpm_min": 55, "bpm_max": 110, "temp_min": 36.0, "temp_max": 37.8
}'
```

---

## Design decisions and best practices

### JSON storage — what's handled, what isn't
- **Handled:** atomic writes (`storage.py` writes to a temp file then
  `os.replace()`s it, so a crash mid-write can't corrupt the file), and a
  per-file lock so concurrent requests can't race each other on
  read-modify-write.
- **Not handled, and won't scale:** every read loads the *whole* file into
  memory. Fine for tens/hundreds of employees, painful for thousands.
  There's also no indexing, no query language, no transactions across
  multiple files (e.g. updating `readings.json` and `alerts.json` together
  isn't atomic as a pair, only individually).
- **Migration path:** when you're ready, swap `storage.py` for
  **SQLite** first (it's a single file too, zero server setup, but gives you
  real transactions, indexing, and concurrent reads for free). Use
  **SQLModel** (built by the FastAPI author) — it reuses your existing
  Pydantic-style models almost unchanged, so the jump from "JSON dict" to
  "database row" is small. Move to **Postgres** when you need multiple app
  servers or serious concurrent write volume (i.e. real deployment with many
  mines/shafts reporting simultaneously).

### Email domain validation
The blocklist in `config.py` (`BLOCKED_EMAIL_DOMAINS`) catches the common
free providers, but it's inherently a blocklist — someone can still register
with `randomfreemail.net` if it's not in the list. Two stronger alternatives
for later:
1. **Allowlist per organization**: when you onboard a mining company, store
   their real domain(s) (e.g. `@minecorp.co.za`) and only accept those. This
   is the standard approach for B2B systems and avoids the blocklist
   arms-race entirely.
2. **Email verification**: send a confirmation link/OTP to the address
   before the account is active. Doesn't stop someone using
   `person@gmail.com`, but does stop typos and fake addresses. Combine both
   for a production system.

### Auth & roles
- Passwords are hashed with **bcrypt** via `passlib` — never store or log
  plaintext passwords.
- **JWT** access tokens carry `employee_id` and `role`; `require_roles(...)`
  is a reusable FastAPI dependency, so locking any endpoint to certain roles
  is a one-line addition. Consider shorter token lifetimes + a refresh-token
  flow before this goes anywhere near production; 8-hour tokens are
  convenient for a shift-based prototype but are a long exposure window if a
  token leaks.
- `SECRET_KEY` is read from an environment variable with a dev fallback —
  make sure the real deployment sets `SMARTPPE_SECRET_KEY` and never commits
  a real key to source control.

### Alerting
Alerts currently fire the instant a reading is outside baseline. Two things
worth adding as you go:
- **Debounce/hysteresis**: a single noisy reading from a wearable
  shouldn't necessarily trigger a full "critical" alert — consider requiring
  N consecutive out-of-range readings, or an average over the last
  30–60 seconds, to cut down false alarms.
- **Push, don't poll**: right now, dashboards have to call `/admin/dashboard`
  repeatedly to notice a new critical status. For a real "alert the
  admin/supervisor" experience, add a **WebSocket** endpoint (FastAPI
  supports this natively) or **Server-Sent Events** so the dashboard updates
  the instant a critical reading lands, and consider push
  notifications/SMS for off-dashboard alerting (a supervisor underground
  won't be staring at a browser tab).

### Data sensitivity
Heart rate and body temperature are health data. Since you're building this
in South Africa, **POPIA** (Protection of Personal Information Act) applies
to how this data is collected, stored, and who can access it — worth a look
even at prototype stage so the architecture doesn't have to be reworked
later. Practically: keep the JSON/DB files off any publicly-accessible
storage, encrypt backups, and make sure only `admin`/`supervisor` roles (not
every authenticated user) can read another employee's vitals — which the
`require_roles` dependency already enforces here.

### Securing the ingestion endpoint
`/wearable/data` is currently open (no auth) so you can test it easily. Once
the actual watch/gateway hardware is in the loop, don't reuse employee login
JWTs for this — issue each device a long-lived **API key** (or use mTLS if
the gateway supports it) so a stolen employee password can't be used to
inject fake vital-sign data.

### What's deliberately left modular for you to extend
- `activity` is currently just whatever the device reports (`moderate` /
  `stressed`) — swap in real logic once you know what the watch actually
  measures (e.g. derived from movement/accelerometer data).
- Dashboard rows only cover the fields you listed; `DashboardRow` in
  `models.py` is the one place to extend when you add more data points.
- Area-based filtering for supervisors assumes one supervisor = one area;
  if a supervisor can cover multiple areas, change `area: Optional[str]` to
  `areas: list[str]` on the user model.
