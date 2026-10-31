from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import ALERTS_FILE, HISTORY_FILE, READINGS_FILE, USERS_FILE, DATA_DIR, EQUIPMENT_FILE, ASSIGNMENTS_FILE, REVOKED_TOKENS_FILE, WEARABLES_FILE
from app.storage import ensure_file
from app.routers import auth_router, wearable_router, dashboard_router, inventory_router, employee_router


app = FastAPI(
    title="SmartPPE Prototype API",
    description="Backend prototype for tracking miner vitals from wearables, "
    "with role-based admin/supervisor dashboards and threshold alerting. "
    "Uses JSON files as a stand-in datastore.",
    version="0.1.0",
)

# Allow the frontend (running on a different origin/port during dev) to call
# this API from the browser. Tighten allow_origins to your real frontend
# URL(s) before this goes anywhere near production - "*" is fine for local
# prototyping only.

# origins = [
#     # "http://192.168.137.1:5137",
#     "http://192.168.0.209:5137",
#     "http://localhost:5137",
#     # "http://192.168.0.209:45678",
# ]
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://192\.168\.\d+\.\d+:\d+|http://localhost:\d+",
    # allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    # allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Make sure our "database" files exist on startup
ensure_file(USERS_FILE, [])
ensure_file(READINGS_FILE, {})
ensure_file(HISTORY_FILE, [])
ensure_file(ALERTS_FILE, [])
ensure_file(EQUIPMENT_FILE, {})
ensure_file(ASSIGNMENTS_FILE, [])
ensure_file(REVOKED_TOKENS_FILE, [])
ensure_file(WEARABLES_FILE, {})


app.include_router(auth_router.router)
app.include_router(wearable_router.router)
app.include_router(dashboard_router.router)
app.include_router(inventory_router.router)
app.include_router(employee_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
