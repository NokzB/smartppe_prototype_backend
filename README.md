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