from fastapi import APIRouter, Depends, HTTPException, status as http_status

from app.config import ALERTS_FILE, READINGS_FILE, USERS_FILE
from app.models import Alert, Baseline, DashboardRow, MinerDetail, MinerSummary, CurrentLocation, LocationHistoryEntry
from app.security import require_roles
from app.services.user_service import set_baseline
from app.services.wearable_service import is_on_duty
from app.services.location_service import get_current_locations, get_location_history
from app.storage import read

router = APIRouter(tags=["dashboards"])


def _build_dashboard_rows(area_filter: str | None = None) -> list[DashboardRow]:
    users = read(USERS_FILE) or []
    readings = read(READINGS_FILE) or {}

    rows = []
    for u in users:
        if u["role"] not in ("miner",):
            continue  # dashboards track workers being monitored, not admins/supervisors themselves
        if area_filter and u.get("area") != area_filter:
            continue

        r = readings.get(u["employee_id"])
        rows.append(
            DashboardRow(
                employee_id=u["employee_id"],
                name=u["name"],
                surname=u["surname"],
                area=u.get("area"),
                role=u["role"],
                status=r["status"] if r else "stable",
                bpm=r["bpm"] if r else None,
                temperature=r["temperature"] if r else None,
                activity=r["activity"] if r else None,
                last_update=r["timestamp"] if r else None,
            )
        )
    return rows


@router.get("/admin/dashboard", response_model=list[DashboardRow])
def admin_dashboard(user: dict = Depends(require_roles("admin"))):
    # Admin sees every employee, every area.
    return _build_dashboard_rows(area_filter=None)


@router.get("/supervisor/dashboard", response_model=list[DashboardRow])
def supervisor_dashboard(user: dict = Depends(require_roles("supervisor", "admin"))):
    # Supervisor sees only their own area. Admins hitting this endpoint see
    # everything (no area assigned) — adjust if supervisors should be
    # strictly scoped even further.
    return _build_dashboard_rows(area_filter=user.get("area"))


@router.get("/alerts", response_model=list[Alert])
def list_alerts(user: dict = Depends(require_roles("admin", "supervisor"))):
    alerts = read(ALERTS_FILE) or []
    if user["role"] == "supervisor" or user["role"] == "admin":
        alerts = [a for a in alerts if a.get("area") == user.get("area")]
    return alerts


@router.get("/admin/miners", response_model=list[MinerSummary])
def list_miners(
    duty: str = "all",  # "all" | "on_duty" | "off_duty"
    user: dict = Depends(require_roles("admin")),
):
    """List all miners, optionally filtered to only those currently on duty
    or off duty. This is the list the admin picks a name from."""
    if duty not in ("all", "on_duty", "off_duty"):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "duty must be one of: all, on_duty, off_duty")

    users = read(USERS_FILE) or []
    readings = read(READINGS_FILE) or {}

    rows = []
    for u in users:
        if u["role"] != "miner":
            continue
        r = readings.get(u["employee_id"])
        last_update = r["timestamp"] if r else None
        on_duty = is_on_duty(last_update)

        if duty == "on_duty" and not on_duty:
            continue
        if duty == "off_duty" and on_duty:
            continue

        rows.append(
            MinerSummary(
                employee_id=u["employee_id"],
                name=u["name"],
                surname=u["surname"],
                area=u.get("area"),
                on_duty=on_duty,
                last_update=last_update,
            )
        )
    return rows


@router.get("/admin/miners/{employee_id}", response_model=MinerDetail)
def get_miner_detail(
    employee_id: str,
    user: dict = Depends(require_roles("admin")),
):
    """Full detail for a single miner — vitals, status, activity, location,
    on/off duty — shown when the admin selects a name from the list."""
    users = read(USERS_FILE) or []
    target = next((u for u in users if u["employee_id"] == employee_id and u["role"] == "miner"), None)
    if not target:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Miner not found")

    readings = read(READINGS_FILE) or {}
    r = readings.get(employee_id)
    last_update = r["timestamp"] if r else None

    return MinerDetail(
        employee_id=target["employee_id"],
        name=target["name"],
        surname=target["surname"],
        area=target.get("area"),
        role=target["role"],
        on_duty=is_on_duty(last_update),
        status=r["status"] if r else "stable",
        bpm=r["bpm"] if r else None,
        temperature=r["temperature"] if r else None,
        activity=r["activity"] if r else None,
        location=r["location"] if r else None,
        last_update=last_update,
    )


@router.put("/admin/baseline/{employee_id}", response_model=dict)
def update_baseline(
    employee_id: str,
    baseline: Baseline,
    user: dict = Depends(require_roles("admin", "supervisor")),
):
    updated = set_baseline(employee_id, baseline.model_dump())
    return {"employee_id": updated["employee_id"], "baseline": updated["baseline"]}

# location tracking endpoints

@router.get("/admin/locations", response_model=list[CurrentLocation])
def admin_current_locations(user: dict = Depends(require_roles("admin"))):
    """Live snapshot - where every miner currently is."""
    return get_current_locations(supervisor_filter=None)


@router.get("/supervisor/locations", response_model=list[CurrentLocation])
def supervisor_current_locations(user: dict = Depends(require_roles("supervisor", "admin"))):
    """Scoped to supervisor's own assigned miners"""
    supervisor_filter = user["employee_id"] if user["role"] == "supervisor" else None
    return get_current_locations(supervisor_filter=supervisor_filter)


@router.get("/admin/miners/{employee_id}/location-history", response_model=list[LocationHistoryEntry])
def miner_location_history(
    employee_id: str,
    user: dict = Depends(require_roles("admin", "supervisor")),
):
    """Movement trail for one miner - to retrace their path after an incident"""
    if user["role"] == "supervisor":
        users = read(USERS_FILE) or []
        target = next((u for u in users if u["employee_id"] == "employee_id"), None)
        if not target or target.get("supervisor_id") != user["employee_id"]:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Not one of your assigned miners")
    return get_location_history(employee_id)