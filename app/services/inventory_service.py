import io
from datetime import datetime, timezone

from fastapi import HTTPException, status as http_status
from openpyxl import load_workbook

from app.config import ASSIGNMENTS_FILE, EQUIPMENT_FILE, USERS_FILE, VALID_EQUIPMENT_CONDITIONS
from app.storage import read, update

# Accepts a few common header spellings so the admin doesn't need an exact template
_HEADER_ALIASES = {
    "item_name": ["item_name", "item name", "name", "equipment", "equipment_name"],
    "category": ["category", "type", "equipment_type"],
    "serial_number": ["serial/asset number", "serial_number", "serial number", "serial", "sn", "equipment_serial"],
    "condition": ["initial condition", "condition", "equipment_condition"],
    "manufacturer": ["manufacturer", "brand", "manufacturer name", "made by"],
}


def _map_headers(header_row) -> dict:
    header_map = {str(h).strip().lower(): i for i, h in enumerate(header_row) if h is not None}
    resolved = {}
    for field, aliases in _HEADER_ALIASES.items():
        resolved[field] = next((header_map[a] for a in aliases if a in header_map), None)
    return resolved


def parse_equipment_spreadsheet(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Returns (valid_items, row_errors). Raises ValueError if required columns are missing."""
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)

    try:
        header_row = next(rows)
    except StopIteration:
        raise ValueError("Spreadsheet is empty")

    col = _map_headers(header_row)
    missing = [field for field, idx in col.items() if idx is None]
    if missing:
        raise ValueError(
            f"Spreadsheet is missing required column(s): {missing}. "
            "Expected columns like: Item Name, Category, Serial/Asset Number, Initial Condition, Manufacturer."
        )

    valid_items, errors = [], []
    for row_num, row in enumerate(rows, start=2):  # row 1 was the header
        if row is None or all(c is None for c in row):
            continue
        try:
            item_name = str(row[col["item_name"]] or "").strip()
            category = str(row[col["category"]] or "").strip()
            serial_number = str(row[col["serial_number"]] or "").strip()
            condition = str(row[col["condition"]] or "").strip().lower()
            manufacturer = str(row[col["manufacturer"]] or "").strip()

            if not serial_number:
                raise ValueError("Serial number is required")
            if condition not in VALID_EQUIPMENT_CONDITIONS:
                raise ValueError(f"Invalid condition '{condition}'. Must be one of {VALID_EQUIPMENT_CONDITIONS}")
            if not item_name:
                raise ValueError("Item name is required")

            valid_items.append({
                "item_name": item_name,
                "category": category,
                "serial_number": serial_number,
                "condition": condition,
                "manufacturer": manufacturer,
                "status": "in_stock",
                "assigned_to": None,
            })
        except Exception as e:
            errors.append(f"Row {row_num}: {e}")

    return valid_items, errors


def bulk_import_equipment(items: list[dict]) -> tuple[int, list[str]]:
    """Merges items into equipment.json keyed by serial number. Re-importing keeps
    the live status and assignment of anything already registered."""
    duplicates = []

    def _mutate(current: dict):
        current = current or {}
        for item in items:
            key = item["serial_number"]
            existing = current.get(key)
            if existing is not None:
                duplicates.append(key)
                status_value = existing.get("status", "in_stock")
                assigned_to = existing.get("assigned_to")
            else:
                status_value = item.get("status", "in_stock")
                assigned_to = item.get("assigned_to")
            current[key] = {**item, "status": status_value, "assigned_to": assigned_to}
        return current

    update(EQUIPMENT_FILE, _mutate)
    return len(items) - len(duplicates), duplicates


def list_equipment() -> list[dict]:
    return list((read(EQUIPMENT_FILE) or {}).values())


def get_equipment_item(serial_number: str) -> dict | None:
    return (read(EQUIPMENT_FILE) or {}).get(serial_number)


def _log_assignment_event(item: dict, employee_id: str | None, action: str, condition: str, notes: str | None):
    event = {
        "serial_number": item["serial_number"],
        "item_name": item["item_name"],
        "employee_id": employee_id,
        "action": action,
        "condition_at_action": condition,
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    update(ASSIGNMENTS_FILE, lambda history: (history or []) + [event])
    return event


def assign_equipment(serial_number: str, employee_id: str, notes: str | None = None) -> dict:
    users = read(USERS_FILE) or []
    if not any(u["employee_id"] == employee_id and u["role"] == "miner" for u in users):
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Miner not found")

    def _mutate(equipment: dict):
        equipment = equipment or {}
        item = equipment.get(serial_number)
        if not item:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Equipment item not found")
        current = item.get("status", "in_stock")
        if current == "assigned":
            raise HTTPException(http_status.HTTP_409_CONFLICT, f"Already assigned to {item.get('assigned_to')}")
        if current in ("damaged", "retired"):
            raise HTTPException(http_status.HTTP_409_CONFLICT, f"Item is {current} and cannot be assigned")
        item["status"] = "assigned"
        item["assigned_to"] = employee_id
        equipment[serial_number] = item
        return equipment

    updated = update(EQUIPMENT_FILE, _mutate)
    item = updated[serial_number]
    _log_assignment_event(item, employee_id, "assigned", item["condition"], notes)
    return item


def return_equipment(serial_number: str, condition: str, notes: str | None = None) -> dict:
    # Captured inside the lock so the check and the write happen together
    returned_from = {}

    def _mutate(equipment: dict):
        equipment = equipment or {}
        item = equipment.get(serial_number)
        if not item:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Equipment item not found")
        if item.get("status") != "assigned":
            raise HTTPException(http_status.HTTP_409_CONFLICT, "Item is not currently assigned")
        returned_from["employee_id"] = item["assigned_to"]
        item["condition"] = condition
        item["assigned_to"] = None
        item["status"] = "damaged" if condition == "damaged" else "in_stock"
        equipment[serial_number] = item
        return equipment

    updated = update(EQUIPMENT_FILE, _mutate)
    item = updated[serial_number]
    _log_assignment_event(item, returned_from["employee_id"], "returned", condition, notes)
    return item


def refurbish_equipment(serial_number: str, notes: str | None = None) -> dict:
    def _mutate(equipment: dict):
        equipment = equipment or {}
        item = equipment.get(serial_number)
        if not item:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Equipment item not found")
        if item.get("status") != "damaged":
            raise HTTPException(http_status.HTTP_409_CONFLICT, "Only damaged items can be refurbished")
        item["condition"] = "refurbished"
        item["status"] = "in_stock"
        equipment[serial_number] = item
        return equipment

    updated = update(EQUIPMENT_FILE, _mutate)
    item = updated[serial_number]
    _log_assignment_event(item, None, "refurbished", "refurbished", notes)
    return item


def get_assignment_history(serial_number: str) -> list[dict]:
    history = read(ASSIGNMENTS_FILE) or []
    return [h for h in history if h["serial_number"] == serial_number]


def get_miner_equipment(employee_id: str) -> list[dict]:
    equipment = read(EQUIPMENT_FILE) or {}
    return [item for item in equipment.values() if item.get("assigned_to") == employee_id]


def is_item_assigned_to(serial_number: str, employee_id: str) -> bool:
    """SmartSafe hook: the safe calls this before releasing an item, so it only
    unlocks equipment actually assigned to the employee badged in."""
    item = (read(EQUIPMENT_FILE) or {}).get(serial_number)
    return bool(item and item.get("status") == "assigned" and item.get("assigned_to") == employee_id)