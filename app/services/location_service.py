from app.config import HISTORY_FILE, READINGS_FILE, USERS_FILE
from app.services.wearable_service import is_on_duty
from app.storage import read


def get_location_history(employee_id: str) -> list[dict]:
    """Full trail of where this employee's wearable device has reported from,
    Oldest first. skips readings where no location was sent."""
    history = read(HISTORY_FILE) or []
    return [
        {
            "location": h["location"],
            "timestamp": h["timestamp"],
            "bpm": h["bpm"],
            "temperature": h["temperature"],
        }
        for h in history
        if h["employee_id"] == employee_id and h.get("location")
    ]
    

def get_current_locations(supervisor_filter: str | None = None) -> list[dict]:
    """Latest known location for every miner - the data a live map view
    would render. if supervisor_filter is set, only that supervisor's 
    assigned miners are included"""
    users = read(USERS_FILE) or []
    readings = read(READINGS_FILE) or {}
    
    rows = []
    for u in users:
        if u["role"] != "miner":
            continue
        if supervisor_filter and u.get("supervisor_id") != supervisor_filter:
            continue
        
        r = readings.get(u["employee_id"])
        last_update = r["timestamp"] if r else None
        
        rows.append({
            "employee_id": u["employee_id"],
            "name": u["name"],
            "surname": u["surname"],
            "area": u.get("area"),
            "location": r.get("location") if r else None,
            "on_duty": is_on_duty(last_update),
            "last_update": last_update,
        })
    return rows