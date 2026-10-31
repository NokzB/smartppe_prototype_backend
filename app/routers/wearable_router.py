from fastapi import APIRouter, Depends

from app.config import WEARABLE_TYPES
from app.models import ( 
    ReadingRecord, WearableReading,
    DeviceAssignRequest, TelemetryPayload,
    WearableDeviceCreate,
)
from app.security import require_roles
from app.services.telemetry_service import (
    assign_device, get_snapshot, ingest_telemetry, list_devices,
    list_snapshots, register_device,
)
from app.services.wearable_service import ingest_reading


router = APIRouter(prefix="/wearable", tags=["wearable"])


# NOTE: in the real system this endpoint will be called by the watch/gateway,
# not a logged-in dashboard user. For the prototype we leave it open so you
# can test with curl/Postman. Before going further than a prototype, put a
# device API key or mTLS in front of this instead of (or in addition to) the
# JWT roles below — see README "Securing the ingestion endpoint".


# The below code has been made redundent as it overwrites the snapshot, which would wipe out merged telemetry and reset status. to be removed in production
# @router.post("/data", response_model=ReadingRecord)
# def submit_reading(payload: WearableReading):
#     return ingest_reading(payload)


@router.post("/telemetry", response_model=dict)
def submit_telemetry(payload: TelemetryPayload):
    # open for now.  put a device API key in front of this before real hardware connection
    return ingest_telemetry(payload)

@router.get("/types", response_model=dict)
def wearable_types(user: dict = Depends(require_roles("admin"))):
    """Displays all wearable types"""
    return WEARABLE_TYPES

@router.post("/devices", response_model=dict, status_code=201)
def create_device(payload: WearableDeviceCreate, user: dict = Depends(require_roles("admin"))):
    """to register new devices"""
    return register_device(payload.device_id, payload.device_type, payload.assigned_to, payload.serial_number)

@router.get("/devices", response_model=list[dict])
def get_devices(user: dict = Depends(require_roles("admin"))):
    """gives a full list of devices currently registered on the system"""
    return list_devices()

@router.put("/devices/{device_id}/assign", response_model=dict)
def reassign_device(device_id: str, payload: DeviceAssignRequest, user: dict = Depends(require_roles("admin"))):
    """Reassigns existing devices to employees"""
    return assign_device(device_id, payload.employee_id)

@router.get("/snapshot", response_model=list[dict])
def all_snapshots(user: dict = Depends(require_roles("admin"))):
    """Gives a full picture for every employee: all 8 data catagories"""
    return list_snapshots()

@router.get("/snapshot/{employee_id}", response_model=dict)
def employee_snapshot(employee_id: str, user: dict = Depends(require_roles("admin"))):
    """Gives a full picture for the selected employee"""
    return get_snapshot(employee_id)