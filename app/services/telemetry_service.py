from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.config import (
    ALERT_SEVERITY, ALERTS_FILE, CAPABILITY_FIELDS, DEFAULT_BASELINE, ENV_LIMITS,
    EQUIPMENT_FILE, FATIGUE_ALERT_SCORE, HIGH_RISK_ZONES, HISTORY_FILE, IMPACT_ALERT_G,
    READINGS_FILE, USERS_FILE, WEARABLE_TYPES, WEARABLES_FILE,
)
from app.models import TelemetryPayload
from app.storage import read, update


# ---------- Device registry ----------

def register_device(device_id: str, device_type: str, assigned_to: str | None,
                    serial_number: str | None = None) -> dict:
    if serial_number:
        if serial_number not in (read(EQUIPMENT_FILE) or {}):
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No inventory item with serial '{serial_number}'")
        assigned_to = None  # inventory owns the assignment for linked devices
    elif assigned_to:
        users = read(USERS_FILE) or []
        if not any(u["employee_id"] == assigned_to for u in users):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")

    def _mutate(devices: dict):
        devices = devices or {}
        if device_id in devices:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Device '{device_id}' already registered")
        devices[device_id] = {
            "device_id": device_id,
            "device_type": device_type,
            "assigned_to": assigned_to,
            "serial_number": serial_number,
        }
        return devices

    return update(WEARABLES_FILE, _mutate)[device_id]


def assign_device(device_id: str, employee_id: str | None) -> dict:
    if employee_id:
        users = read(USERS_FILE) or []
        if not any(u["employee_id"] == employee_id for u in users):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")

    def _mutate(devices: dict):
        devices = devices or {}
        device = devices.get(device_id)
        if device is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
        if device.get("serial_number"):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This device is linked to an inventory item. Assign it via /inventory/equipment/{serial}/assign",
            )
        device["assigned_to"] = employee_id
        devices[device_id] = device
        return devices

    return update(WEARABLES_FILE, _mutate)[device_id]


def list_devices() -> list[dict]:
    return list((read(WEARABLES_FILE) or {}).values())


def get_snapshot(employee_id: str) -> dict:
    snap = (read(READINGS_FILE) or {}).get(employee_id)
    if not snap:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No telemetry for this employee yet")
    return snap


def list_snapshots() -> list[dict]:
    return list((read(READINGS_FILE) or {}).values())


# ---------- Ingestion ----------

def _allowed_fields(device_type: str) -> set[str]:
    allowed = set()
    for capability in WEARABLE_TYPES[device_type]["capabilities"]:
        allowed |= CAPABILITY_FIELDS[capability]
    return allowed


def _merge(snapshot: dict, incoming: dict) -> dict:
    """Overlay new values onto the snapshot. Nested groups (ppe, environment) merge
    key by key, so a boot reporting boots=True doesn't erase the helmet's helmet=True."""
    merged = dict(snapshot)
    for key, value in incoming.items():
        if isinstance(value, dict):
            merged[key] = {**(snapshot.get(key) or {}), **value}
        else:
            merged[key] = value
    return merged


def _evaluate(incoming: dict, merged: dict, baseline: dict) -> dict[str, str | None]:
    """Re-check only the alert categories this payload carried data for.
    Returns {category: reason if active, else None}."""
    results: dict[str, str | None] = {}

    if "bpm" in incoming or "temperature" in incoming:
        reasons = []
        bpm = merged.get("bpm")
        temp = merged.get("temperature")
        if bpm is not None and not (baseline["bpm_min"] <= bpm <= baseline["bpm_max"]):
            reasons.append(f"BPM {bpm} outside [{baseline['bpm_min']}-{baseline['bpm_max']}]")
        if temp is not None and not (baseline["temp_min"] <= temp <= baseline["temp_max"]):
            reasons.append(f"Body temp {temp}C outside [{baseline['temp_min']}-{baseline['temp_max']}]")
        results["vitals"] = "; ".join(reasons) or None

    if "fatigue_score" in incoming:
        score = incoming["fatigue_score"]
        results["fatigue"] = (
            f"Fatigue score {score} (limit {FATIGUE_ALERT_SCORE})" if score >= FATIGUE_ALERT_SCORE else None
        )

    if "fall_detected" in incoming or "impact_g" in incoming:
        g = incoming.get("impact_g")
        if incoming.get("fall_detected"):
            results["fall_impact"] = "Fall detected"
        elif g is not None and g >= IMPACT_ALERT_G:
            results["fall_impact"] = f"Impact of {g}g detected"
        else:
            results["fall_impact"] = None

    if "ppe" in incoming:
        missing = [item for item, worn in (merged.get("ppe") or {}).items() if worn is False]
        results["ppe"] = f"PPE not worn: {', '.join(missing)}" if missing else None

    if "environment" in incoming:
        env = merged.get("environment") or {}
        breaches = [
            f"{key} {env[key]} (limit {limit})"
            for key, limit in ENV_LIMITS.items()
            if env.get(key) is not None and env[key] >= limit
        ]
        results["environment"] = "; ".join(breaches) or None

    if "sos" in incoming:
        results["sos"] = "SOS button triggered" if incoming["sos"] else None

    if "location" in incoming:
        loc = incoming["location"]
        results["high_risk_zone"] = f"Entered high-risk zone: {loc}" if loc in HIGH_RISK_ZONES else None

    return results


def _resolve_employee(device: dict) -> str | None:
    """Linked devices follow their inventory assignment. Unlinked devices use their own assigned_to."""
    serial = device.get("serial_number")
    if serial:
        item = (read(EQUIPMENT_FILE) or {}).get(serial)
        return item.get("assigned_to") if item and item.get("status") == "assigned" else None
    return device.get("assigned_to")


def ingest_telemetry(payload: TelemetryPayload) -> dict:
    devices = read(WEARABLES_FILE) or {}
    device = devices.get(payload.device_id)
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown device_id: register it first")

    employee_id = _resolve_employee(device)
    if not employee_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Nobody is currently wearing this device (check its inventory assignment)",
        )

    users = read(USERS_FILE) or []
    user = next((u for u in users if u["employee_id"] == employee_id), None)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assigned employee no longer exists")

    incoming = payload.model_dump(exclude={"device_id", "timestamp"}, exclude_none=True)

    not_allowed = set(incoming) - _allowed_fields(device["device_type"])
    if not_allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"A {device['device_type']} can't report: {sorted(not_allowed)}",
        )

    ts = payload.timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    baseline = user.get("baseline") or DEFAULT_BASELINE
    newly_raised: list[tuple[str, str]] = []

    def _mutate(snapshots: dict):
        snapshots = snapshots or {}
        current = snapshots.get(employee_id) or {
            "employee_id": employee_id,
            "bpm": None, "temperature": None, "activity": None, "location": None,
            "active_alerts": {},
        }
        merged = _merge(current, incoming)

        active = dict(current.get("active_alerts") or {})
        for category, reason in _evaluate(incoming, merged, baseline).items():
            if reason:
                if category not in active:
                    newly_raised.append((category, reason))  # log only when the alert starts
                active[category] = reason
            else:
                active.pop(category, None)

        merged["active_alerts"] = active
        merged["status"] = "critical" if active else "stable"
        merged["timestamp"] = ts.isoformat()
        merged["last_device_id"] = payload.device_id
        snapshots[employee_id] = merged
        return snapshots

    snapshot = update(READINGS_FILE, _mutate)[employee_id]

    # Append-only history (audit trail / trends)
    record = {
        "employee_id": employee_id,
        "device_id": payload.device_id,
        "device_type": device["device_type"],
        "timestamp": ts.isoformat(),
        **incoming,
    }
    update(HISTORY_FILE, lambda h: (h or []) + [record])

    # Alert log
    if newly_raised:
        new_rows = [
            {
                "employee_id": employee_id,
                "name": user["name"],
                "surname": user["surname"],
                "area": user.get("area"),
                "alert_type": category,
                "severity": ALERT_SEVERITY.get(category, "warning"),
                "reason": reason,
                "bpm": snapshot.get("bpm"),
                "temperature": snapshot.get("temperature"),
                "location": snapshot.get("location"),
                "timestamp": ts.isoformat(),
                "acknowledged": False,
            }
            for category, reason in newly_raised
        ]
        update(ALERTS_FILE, lambda a: (a or []) + new_rows)

    return snapshot