from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.config import ACTIVE_THRESHOLD_MINUTES, ALERTS_FILE, HISTORY_FILE, READINGS_FILE, USERS_FILE
from app.models import WearableReading
from app.storage import read, update


def is_on_duty(last_timestamp_iso: str | None) -> bool:
    """A miner is 'on duty' if their wearable reported within the active
    window (see ACTIVE_THRESHOLD_MINUTES). No reading yet, or the trail's
    gone cold, means off duty."""
    if not last_timestamp_iso:
        return False
    last = datetime.fromisoformat(last_timestamp_iso)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age_minutes = (datetime.now(timezone.utc) - last).total_seconds() / 60
    return age_minutes <= ACTIVE_THRESHOLD_MINUTES


def _get_user(employee_id: str) -> dict:
    users = read(USERS_FILE) or []
    user = next((u for u in users if u["employee_id"] == employee_id), None)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown employee_id — is the device registered?")
    return user


def _evaluate_status(bpm: float, temp: float, baseline: dict) -> tuple[str, str | None]:
    """Returns (status, reason). status is 'stable' or 'critical'."""
    reasons = []
    if bpm < baseline["bpm_min"] or bpm > baseline["bpm_max"]:
        reasons.append(f"BPM {bpm} outside baseline [{baseline['bpm_min']}-{baseline['bpm_max']}]")
    if temp < baseline["temp_min"] or temp > baseline["temp_max"]:
        reasons.append(f"Temp {temp}°C outside baseline [{baseline['temp_min']}-{baseline['temp_max']}]")

    if reasons:
        return "critical", "; ".join(reasons)
    return "stable", None


def ingest_reading(payload: WearableReading) -> dict:
    user = _get_user(payload.employee_id)
    baseline = user.get("baseline") or {}
    timestamp = payload.timestamp or datetime.now(timezone.utc)

    status_value, reason = _evaluate_status(payload.bpm, payload.temperature, baseline)

    record = {
        "employee_id": payload.employee_id,
        "bpm": payload.bpm,
        "temperature": payload.temperature,
        "activity": payload.activity,
        "location": payload.location,
        "status": status_value,
        "timestamp": timestamp.isoformat(),
    }

    # 1. Update "latest reading per employee" snapshot (what dashboards read)
    def _mutate_current(current: dict):
        current = current or {}
        current[payload.employee_id] = record
        return current

    update(READINGS_FILE, _mutate_current)

    # 2. Append to history log (for trends/audit later)
    def _mutate_history(history: list):
        history = history or []
        history.append(record)
        return history

    update(HISTORY_FILE, _mutate_history)

    # 3. Raise an alert if critical
    if status_value == "critical":
        alert = {
            "employee_id": user["employee_id"],
            "name": user["name"],
            "surname": user["surname"],
            "area": user.get("area"),
            "reason": reason,
            "bpm": payload.bpm,
            "temperature": payload.temperature,
            "timestamp": timestamp.isoformat(),
            "acknowledged": False,
        }

        def _mutate_alerts(alerts: list):
            alerts = alerts or []
            alerts.append(alert)
            return alerts

        update(ALERTS_FILE, _mutate_alerts)

    return record
