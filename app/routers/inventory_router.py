from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from app.models import EquipmentImportResult, EquipmentItem, AssignEquipmentRequest, AssignmentRecord, ReturnEquipmentRequest
from app.security import require_roles
from app.services.inventory_service import (
    parse_equipment_spreadsheet,
    bulk_import_equipment,
    get_equipment_item,
    list_equipment,
    assign_equipment,
    get_assignment_history,
    get_miner_equipment,
    refurbish_equipment,
    return_equipment,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.post("/equipment/import", response_model=EquipmentImportResult)
async def import_equipment(
    file: UploadFile = File(...),
    user: dict = Depends(require_roles("admin")),
):
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file type. Please upload a .xlsx spreadsheet")
    
    file_bytes = await file.read()
    try:
        valid_items, row_errors = parse_equipment_spreadsheet(file_bytes)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    
    imported_count, duplicates = bulk_import_equipment(valid_items)
    return EquipmentImportResult(
        imported=imported_count,
        skipped_duplicates=duplicates,
        errors=row_errors,
    )
    
@router.get("/equipment", response_model=list[EquipmentItem])
def get_all_equipment(user: dict = Depends(require_roles("admin", "supervisor"))):
    """Details section - every registered item."""
    return list_equipment()

@router.get("/equipment/{serial_number}", response_model=EquipmentItem)
def get_equipment_by_serial(
    serial_number: str,
    user: dict = Depends(require_roles("admin", "supervisor")),
):
    """Details section - every registered item."""
    item = get_equipment_item(serial_number)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment item not found")
    return item

@router.post("/equipment", response_model=EquipmentItem, status_code=status.HTTP_201_CREATED)
def register_equipment_item(
    item: EquipmentItem,
    user: dict = Depends(require_roles("admin")),
):
    """Manual single-item registration. for when theres no spreadsheet"""
    imported_count, duplicates = bulk_import_equipment([item.model_dump()])
    if duplicates:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Serial/Asset number '{item.serial_number}' already registered")
    return item

@router.post("/equipment/{serial_number}/assign", response_model=EquipmentItem)
def assign_item(
    serial_number: str,
    payload: AssignEquipmentRequest,
    user: dict = Depends(require_roles("admin")),
    
):
    return assign_equipment(serial_number, payload.employee_id, payload.notes)

@router.post("/equipment/{serial_number}/return", response_model=EquipmentItem)
def return_item(
    serial_number: str,
    payload: ReturnEquipmentRequest,
    user: dict = Depends(require_roles("admin")),
):
    return return_equipment(serial_number, payload.condition, payload.notes)

@router.post("/equipment/{serial_number}/refurbish, response_model=EquipmentItem")
def refurbish_item(
    serial_number: str,
    notes: str | None = None,
    user: dict = Depends(require_roles("admin")),
):
    return refurbish_equipment(serial_number, notes)

@router.get("/equipment/{serial_number}/history", response_model=list[AssignmentRecord])
def equipment_history(
    serial_number: str,
    user: dict = Depends(require_roles("admin")),
):
    return get_assignment_history(serial_number)

@router.get("miners/{employee_id}/equipment", response_model=list[EquipmentItem])
def miner_equipment(
    employee_id: str,
    user: dict = Depends(require_roles("admin")),
):
    return get_miner_equipment(employee_id)