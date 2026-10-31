"""
Demo seeder: employees, inventory, wearables (linked to inventory) and telemetry.

Run from the smartppe/ project root:

    python -m scripts.seed_demo            # populate; safe to re-run
    python -m scripts.seed_demo --reset    # wipe EVERYTHING first, then populate

A normal run adds whatever is missing (users, inventory, devices, assignments), then
refreshes telemetry (readings, history, alerts) so every run ends in the same demo state.
It reads the files back at the end so you can see what was actually written.
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.config import (
    ALERTS_FILE, ASSIGNMENTS_FILE, EQUIPMENT_FILE, HISTORY_FILE,
    READINGS_FILE, USERS_FILE, WEARABLES_FILE,
)
from app.models import TelemetryPayload, UserRegister
from app.services.inventory_service import (
    assign_equipment, bulk_import_equipment, get_equipment_item,
    refurbish_equipment, return_equipment,
)
from app.services.telemetry_service import ingest_telemetry, register_device
from app.services.user_service import register_user
from app.storage import read, update, write

PASSWORD = "Demo12345"
DOMAIN = "minecorp.co.za"

STAFF = [  # id, name, surname, role, area
    ("ADM001", "Thabo", "Nkosi", "admin", None),
    ("SUP001", "Pieter", "van Wyk", "supervisor", "Shaft-A"),
    ("SUP002", "Lindiwe", "Dube", "supervisor", "Shaft-B"),
]

MINERS = [  # id, name, surname, area, supervisor, scenario
    ("MIN001", "Sipho", "Mokoena", "Shaft-A", "SUP001", "normal"),
    ("MIN002", "Nomsa", "Khumalo", "Shaft-A", "SUP001", "fatigued"),
    ("MIN003", "Johan", "Botha", "Shaft-A", "SUP001", "fall"),
    ("MIN004", "Themba", "Zulu", "Shaft-A", "SUP001", "sos"),
    ("MIN005", "Ayanda", "Ndlovu", "Shaft-B", "SUP002", "gas"),
    ("MIN006", "Karabo", "Molefe", "Shaft-B", "SUP002", "high_risk_zone"),
    ("MIN007", "Fatima", "Patel", "Shaft-B", "SUP002", "ppe_violation"),
    ("MIN008", "Lerato", "Sithole", "Shaft-B", "SUP002", "high_heart_rate"),
    ("MIN009", "Bongani", "Dlamini", "Shaft-A", "SUP001", "off_duty"),
]

# device_type -> (serial/device prefix, inventory item name, manufacturer)
SMART_DEVICES = {
    "smartwatch": ("SW", "Smart Watch", "Vitalink"),
    "smart_helmet": ("HLM", "Smart Helmet", "MineGuard"),
    "gas_detector": ("GAS", "Personal Gas Detector", "AeroSense"),
    "smart_vest": ("VST", "Smart Hi-Vis Vest", "ReflexWear"),
    "smart_boot": ("BOOT", "Smart Safety Boots", "StrideSafe"),
}

# Non-electronic PPE: inventory only, no telemetry
BASIC_PPE = [  # prefix, item name, manufacturer, condition
    ("GLV", "Safety Gloves", "GripPro", "new"),
    ("GLS", "Safety Glasses", "ClearView", "used"),
]

DATA_FILES = {
    USERS_FILE: [], READINGS_FILE: {}, HISTORY_FILE: [], ALERTS_FILE: [],
    WEARABLES_FILE: {}, EQUIPMENT_FILE: {}, ASSIGNMENTS_FILE: [],
}


# ---------- helpers ----------

def ensure_valid_file(path, default):
    """Create the file if missing; repair it if it's empty or corrupt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path) as f:
            json.load(f)
    except FileNotFoundError:
        write(path, default)
    except json.JSONDecodeError:
        print(f"  ! {path.name} was empty or corrupt: reset it")
        write(path, default)


def make_user(emp_id, name, surname, role, area, supervisor_id, n) -> bool:
    try:
        register_user(UserRegister(
            name=name, surname=surname, role=role,
            email=f"{name}.{surname}@{DOMAIN}".lower().replace(" ", ""),
            phone=f"082000{n:04d}", employee_id=emp_id, password=PASSWORD,
            area=area, supervisor_id=supervisor_id,
        ))
        return True
    except HTTPException as e:
        if e.status_code == 409:
            return False  # already exists
        raise


def ensure_item(serial, name, category, condition, manufacturer) -> bool:
    """Create the inventory item if it doesn't exist. Returns True if created."""
    if get_equipment_item(serial):
        return False
    bulk_import_equipment([{
        "item_name": name, "category": category, "serial_number": serial,
        "condition": condition, "manufacturer": manufacturer,
        "status": "in_stock", "assigned_to": None,
    }])
    return True


def ensure_assigned(serial, emp_id):
    item = get_equipment_item(serial)
    if item is None:
        print(f"  ! {serial} is missing from inventory")
        return
    if item.get("status", "in_stock") == "in_stock":
        assign_equipment(serial, emp_id, "Demo issue")
    elif item.get("assigned_to") != emp_id:
        print(f"  ! {serial} is {item.get('status')} / {item.get('assigned_to')}: left as is")


def ensure_device(device_id, device_type, serial) -> bool:
    """Register the device linked to its inventory item. Returns True if created."""
    try:
        register_device(device_id, device_type, None, serial_number=serial)
        return True
    except HTTPException as e:
        if e.status_code != 409:
            raise

    # Already registered (e.g. by an older seeder): make sure it's linked.
    def _link(devices: dict):
        devices[device_id]["serial_number"] = serial
        devices[device_id]["assigned_to"] = None
        return devices

    update(WEARABLES_FILE, _link)
    return False


def build_payload(device_type: str, scenario: str, area: str, final: bool) -> dict:
    """One realistic reading for this device type. Earlier readings are always
    'normal'; the scenario only shows up in the final reading."""
    sc = scenario if final else "normal"
    location = "Blast Zone B" if sc == "high_risk_zone" else f"{area}, Level {random.randint(1, 3)}"
    stressed = sc in {"high_heart_rate", "sos", "fall"}
    p: dict = {"location": location}

    if device_type == "smartwatch":
        p.update(
            bpm=142 if sc == "high_heart_rate" else random.randint(68, 92),
            temperature=38.4 if sc == "high_heart_rate" else round(random.uniform(36.4, 37.2), 1),
            fatigue_score=random.randint(78, 92) if sc == "fatigued" else random.randint(10, 40),
            activity="stressed" if stressed else "moderate",
            sos=(sc == "sos"),
        )
    elif device_type == "smart_helmet":
        p.update(
            fall_detected=(sc == "fall"),
            impact_g=6.8 if sc == "fall" else round(random.uniform(0.2, 1.5), 1),
            ppe={"helmet": sc != "ppe_violation"},
            environment={"noise_db": random.randint(70, 82)},
        )
    elif device_type == "gas_detector":
        gas = sc == "gas"
        p["environment"] = {
            "co_ppm": 58 if gas else random.randint(3, 12),
            "methane_pct": 1.4 if gas else round(random.uniform(0.1, 0.4), 2),
            "ambient_temp_c": random.randint(26, 31),
            "air_quality_index": 190 if gas else random.randint(40, 90),
        }
    elif device_type == "smart_vest":
        p["ppe"] = {"vest": sc != "ppe_violation"}
    elif device_type == "smart_boot":
        p.update(ppe={"boots": True}, activity="stressed" if stressed else "moderate")
    return p


# ---------- main ----------

def seed(reset: bool):
    print("== Preparing data files")
    for path, default in DATA_FILES.items():
        ensure_valid_file(path, default)
        if reset:
            write(path, default)
    if reset:
        print("  everything wiped (--reset)")

    # 1. Users (supervisors first: miners reference them)
    print("== Users")
    made = 0
    for i, (emp_id, name, surname, role, area) in enumerate(STAFF):
        made += make_user(emp_id, name, surname, role, area, None, i)
    for i, (emp_id, name, surname, area, sup, _) in enumerate(MINERS, start=len(STAFF)):
        made += make_user(emp_id, name, surname, "miner", area, sup, i)
    total_users = len(STAFF) + len(MINERS)
    print(f"  {made} created, {total_users - made} already existed")

    # 2. Inventory, devices and assignments (inventory is the source of truth)
    print("== Inventory, devices and assignments")
    items_made = devices_made = 0
    for emp_id, _, _, _, _, _ in MINERS:
        for dtype, (prefix, item_name, maker) in SMART_DEVICES.items():
            serial = f"{prefix}-{emp_id}"
            items_made += ensure_item(serial, item_name, "Smart Wearable", "new", maker)
            devices_made += ensure_device(serial, dtype, serial)
            ensure_assigned(serial, emp_id)
        for prefix, item_name, maker, condition in BASIC_PPE:
            serial = f"{prefix}-{emp_id}"
            items_made += ensure_item(serial, item_name, "PPE", condition, maker)
            ensure_assigned(serial, emp_id)

    # Spare stock, plus lifecycle history so the Inventory tab has something to show
    for n in (1, 2):
        items_made += ensure_item(f"HLM-SPARE-0{n}", "Smart Helmet", "Smart Wearable", "new", "MineGuard")

    if ensure_item("HLM-OLD-01", "Safety Helmet", "PPE", "used", "HardHat Co"):
        items_made += 1
        assign_equipment("HLM-OLD-01", "MIN009", "Demo issue")
        return_equipment("HLM-OLD-01", "damaged", "Visor cracked after rockfall")

    if ensure_item("BOOT-OLD-01", "Safety Boots", "PPE", "used", "StrideSafe"):
        items_made += 1
        assign_equipment("BOOT-OLD-01", "MIN001", "Demo issue")
        return_equipment("BOOT-OLD-01", "damaged", "Sole separated")
        refurbish_equipment("BOOT-OLD-01", "Resoled by workshop")  # back in stock as refurbished

    print(f"  {items_made} inventory items created, {devices_made} devices registered")

    # 3. Telemetry: always refreshed, so every run ends in the same demo state
    print("== Telemetry")
    for path, default in ((READINGS_FILE, {}), (HISTORY_FILE, []), (ALERTS_FILE, [])):
        write(path, default)

    now = datetime.now(timezone.utc)
    sent = failed = 0
    for emp_id, _, _, area, _, scenario in MINERS:
        base = now - timedelta(hours=3) if scenario == "off_duty" else now
        for i in range(12, -1, -1):  # 12 history points 2 minutes apart, then the scenario reading
            ts = base - timedelta(minutes=i * 2)
            for dtype, (prefix, _, _) in SMART_DEVICES.items():
                device_id = f"{prefix}-{emp_id}"
                fields = build_payload(dtype, scenario, area, final=(i == 0))
                try:
                    ingest_telemetry(TelemetryPayload(device_id=device_id, timestamp=ts, **fields))
                    sent += 1
                except HTTPException as e:
                    failed += 1
                    if failed <= 5:
                        print(f"  ! {device_id}: {e.detail}")
        print(f"  {emp_id} {scenario}")
    print(f"  {sent} readings ingested, {failed} failed")

    # 4. Read everything back
    print("== Verification (read back from the JSON files)")
    users = read(USERS_FILE) or []
    equipment = read(EQUIPMENT_FILE) or {}
    readings = read(READINGS_FILE) or {}
    devices = read(WEARABLES_FILE) or {}
    critical = [e for e, r in readings.items() if r.get("status") == "critical"]
    print(f"  users:      {len(users)} ({sum(u['role'] == 'miner' for u in users)} miners)")
    print(f"  inventory:  {len(equipment)} items, {sum(i.get('status') == 'assigned' for i in equipment.values())} assigned")
    print(f"  devices:    {len(devices)}")
    print(f"  snapshots:  {len(readings)} employees, {len(critical)} critical")
    print(f"  history:    {len(read(HISTORY_FILE) or [])} readings")
    print(f"  alerts:     {len(read(ALERTS_FILE) or [])}")

    print(f"\nLog in with password: {PASSWORD}")
    print(f"  admin:       thabo.nkosi@{DOMAIN}")
    print(f"  supervisor:  pieter.vanwyk@{DOMAIN}")
    print(f"  supervisor:  lindiwe.dube@{DOMAIN}")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)