from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.config import BLOCKED_EMAIL_DOMAINS, VALID_ROLES, WEARABLE_TYPES
from app.validators import is_blocked_email_domain


Role = Literal["admin", "supervisor", "miner"]
Activity = Literal["moderate", "stressed"]
Status = Literal["stable", "warning", "critical"]
EquipmentCondition = Literal["new", "used", "damaged", "refurbished"]
EquipmentStatus = Literal["in_stock", "assigned", "damaged", "retired"]


# ---------- Registration / Users ----------

class UserRegister(BaseModel):
    name: str
    surname: str
    role: Role
    email: EmailStr
    phone: str
    employee_id: str
    password: str = Field(min_length=8)
    area: Optional[str] = None  # useful for supervisor filtering later
    company_name: Optional[str] = None

    @field_validator("email")
    @classmethod
    def block_public_webmail(cls, v: str) -> str:
        if is_blocked_email_domain(v):
            raise ValueError(
                "Please register with your company email address. "
                "Public webmail providers (gmail, yahoo, outlook, etc.) are not allowed."
            )
        return v

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {VALID_ROLES}")
        return v


class UserPublic(BaseModel):
    employee_id: str
    name: str
    surname: str
    role: Role
    email: EmailStr
    phone: str
    area: Optional[str] = None
    company_name: Optional[str] = None
    

class CurrentUserResponse(BaseModel):
    welcome_message: str
    employee_id: str
    name: str
    surname: str
    role: Role
    email: EmailStr
    phone: str
    area: Optional[str] = None
    company_name: Optional[str] = None
    
    
class EmployeeUpdate(BaseModel):
    """Partial Update - every field optional, only what's sent gets changed."""
    name: Optional[str] = None
    surname: Optional[str] = None
    role: Optional[Role] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    area: Optional[str] = None
    company_name: Optional[str] = None
    
    @field_validator("email")
    @classmethod
    def block_public_webmail(cls, v: Optional[str]) -> Optional[str]:
        if v and is_blocked_email_domain(v):
            raise ValueError("Please use a company email address, not a public webmail provider")
        return v
        

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    
class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CurrentUserResponse
    

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Baseline (per-employee alert thresholds) ----------

class Baseline(BaseModel):
    employee_id: str
    bpm_min: float
    bpm_max: float
    temp_min: float
    temp_max: float


# ---------- Wearable data ingestion ----------

class WearableReading(BaseModel):
    employee_id: str
    bpm: float
    temperature: float
    activity: Activity = "moderate"
    location: Optional[str] = None  # e.g. "Shaft-A, Level 3" — swap for GPS/beacon coords later
    timestamp: Optional[datetime] = None  # server fills this in if absent


class ReadingRecord(BaseModel):
    employee_id: str
    bpm: float
    temperature: float
    activity: Activity
    status: Status
    location: Optional[str] = None
    timestamp: datetime
    
class LocationHistoryEntry(BaseModel):
    location: str
    timestamp: datetime
    bpm: Optional[float] = None
    temperature: Optional[float] = None
    

class CurrentLocation(BaseModel):
    employee_id: str
    name: str
    surname: str
    area: Optional[str] = None
    location: Optional[str] = None
    on_duty: bool
    last_update: Optional[datetime] = None
    
    
class PPEStatus(BaseModel):
    helmet: Optional[bool] = None
    vest: Optional[bool] = None
    boots: Optional[bool] = None
    glasses: Optional[bool] = None
    gloves: Optional[bool] = None


class Environment(BaseModel):
    co_ppm: Optional[float] = None
    methane_pct: Optional[float] = None
    ambient_temp_c: Optional[float] = None
    noise_db: Optional[float] = None
    air_quality_index: Optional[float] = None
    

class TelemetryPayload(BaseModel):
    """Every field except device_id is optional: each device only sends what it's sensors measure"""
    device_id: str
    timestamp: Optional[datetime] = None # consider making this non-optional
    location: Optional[str] = None
    activity: Optional[Activity] = None
    bpm: Optional[float] = None
    temperature: Optional[float] = None
    fatigue_score: Optional[float] = None
    fall_detected: Optional[bool] = None
    impact_g: Optional[float] = None # research, might be bool
    ppe: Optional[PPEStatus] = None
    environment: Optional[Environment] = None
    sos: Optional[bool] = None
    
    
class WearableDeviceCreate(BaseModel):
    device_id: str
    device_type: str
    assigned_to: Optional[str] = None # employee_id
    serial_number: Optional[str] = None # links this device to an inventory item
    
    @field_validator("device_type")
    @classmethod
    def type_must_be_registered(cls, v: str) -> str:
        if v not in WEARABLE_TYPES:
            raise ValueError(f"device_type must be one of {sorted(WEARABLE_TYPES)}")
        return v
    

class DeviceAssignRequest(BaseModel):
    employee_id: Optional[str] = None

# ---------- Dashboard ----------

class DashboardRow(BaseModel):
    employee_id: str
    name: str
    surname: str
    area: Optional[str]
    role: Role
    status: Status
    bpm: Optional[float]
    temperature: Optional[float]
    activity: Optional[Activity]
    last_update: Optional[datetime]


class MinerSummary(BaseModel):
    """One row in the admin's miner list — on duty / off duty view."""
    employee_id: str
    name: str
    surname: str
    area: Optional[str]
    on_duty: bool
    last_update: Optional[datetime]


class MinerDetail(BaseModel):
    """Full detail shown when the admin selects a specific miner."""
    employee_id: str
    name: str
    surname: str
    area: Optional[str]
    role: Role
    on_duty: bool
    status: Status
    bpm: Optional[float]
    temperature: Optional[float]
    activity: Optional[Activity]
    location: Optional[str]
    last_update: Optional[datetime]


class Alert(BaseModel):
    employee_id: str
    name: str
    surname: str
    area: Optional[str] = None
    alert_type: str = "vitals"
    severity: str = "warning"
    reason: str
    bpm: Optional[float] = None
    temperature: Optional[float] = None
    location: Optional[str] = None
    timestamp: datetime
    acknowledged: bool = False
    

# --- Equipment Inventory ---
class EquipmentItem(BaseModel):
    item_name: str
    category: str
    serial_number: str # used as the unique key
    condition: EquipmentCondition
    manufacturer: str
    status: EquipmentStatus = "in_stock"
    assigned_to: Optional[str] = None
    assigned_date: datetime
    storage_location: Optional[str] = None
    
class EquipmentImportResult(BaseModel):
    imported: int
    skipped_duplicates: list[str]  # list of serial numbers that were skipped due to duplicates
    errors: list[str]
    
class AssignEquipmentRequest(BaseModel):
    condition: EquipmentCondition
    notes: Optional[str] = None
    
class AssignmentRecord(BaseModel):
    serial_number: str
    item_name: str
    employee_id: str
    action: Literal["assigned", "returned", "refurbished", "retired"]
    notes: Optional[str] = None
    timestamp: datetime

class ReturnEquipmentRequest(BaseModel):
    condition: EquipmentCondition  # what state it came back in — "damaged" is common here
    notes: Optional[str] = None