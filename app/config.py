"""
Central configuration for the SmartPPE prototype.

In production, SECRET_KEY and any org-specific settings should come from
environment variables / a secrets manager, never hardcoded like this.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

USERS_FILE = DATA_DIR / "users.json"
READINGS_FILE = DATA_DIR / "readings.json"   # latest reading per employee
HISTORY_FILE = DATA_DIR / "readings_history.json"  # append-only log
ALERTS_FILE = DATA_DIR / "alerts.json"
WEARABLES_FILE = DATA_DIR / "wearables.json"

# --- Auth ---
SECRET_KEY = os.environ.get("SMARTPPE_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hour shift

VALID_ROLES = {"admin", "supervisor", "miner"}

# --- Email domain policy ---
# Prototype approach: block known free/public webmail providers, so only
# "company-looking" domains get through. See README for why this is a
# stop-gap, not real verification.
BLOCKED_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "ymail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "icloud.com", "me.com",
    "aol.com",
    "protonmail.com", "proton.me",
    "zoho.com",
    "gmx.com", "gmx.net",
    "yandex.com",
    "webmail.com",
    "mail.com",
}

# --- Duty status inference ---
# A miner is considered "on duty" if their wearable has reported a reading
# within this many minutes. No recent reading (or none ever) = off duty.
ACTIVE_THRESHOLD_MINUTES = 15

# --- Default baseline vitals (used until an admin/supervisor sets a
# per-employee baseline) ---
DEFAULT_BASELINE = {
    "bpm_min": 60,
    "bpm_max": 100,
    "temp_min": 36.1,
    "temp_max": 37.5,
}


# --- Inventory ---
# For the prototype, we use a file based system to store the inventory. In a real system,
# this would be a database table, and the inventory would be managed by
# the admin/supervisor users.
EQUIPMENT_FILE = DATA_DIR / "equipment.json"
VALID_EQUIPMENT_CONDITIONS = {"new", "used", "damaged", "refurbished"}
ASSIGNMENTS_FILE = DATA_DIR / "assignments.json"
REVOKED_TOKENS_FILE = DATA_DIR / "revoked_tokens.json"


# --- Wearable registry ---
# what each measurement category is called in the payload
CAPABILITY_FIELDS = {
    "location": {"location"},
    "activity": {"activity"},
    "heart_rate": {"bpm"},
    "body_temperature": {"temperature"},
    "fatigue": {"fatigue_score"},
    "fall_impact": {"fall_detected", "impact_g"},
    "ppe": {"ppe"},
    "environment": {"environment"},
    "sos": {"sos"},
}

# Wearable types and what each one is allowed to report.
WEARABLE_TYPES = {
    "smartwatch": {
        "label": "Smart Watch",
        "capabilities": ["location", "activity", "heart_rate", "body_temperature", "fatigue", "sos"],
    },
    "smart_helmet": {
        "label": "Smart Helmet",
        "capabilities": ["location", "fall_impact", "ppe", "environment"],
    },
    "gas_detector": {
        "label": "Personal Gas Detector",
        "capabilities": ["location", "environment", "sos"],
    },
    "smart_vest": {
        "label": "Smart Hi-Vis Vest",
        "capabilities": ["location", "ppe"],
    },
    "smart_boot": {
        "label": "Smart Safety Boots",
        "capabilities": ["location", "activity", "ppe", "fall_impact"],
    },
}

# Fail fast at startup if a device type refers to a capability that doesn't exist.
# Without this, a typo only shows up when the first reading arrives.
for _device_type, _spec in WEARABLE_TYPES.items():
    for _cap in _spec["capabilities"]:
        if _cap not in CAPABILITY_FIELDS:
            raise ValueError(
                f"WEARABLE_TYPES['{_device_type}'] uses unknown capability '{_cap}'. "
                f"Known capabilities: {sorted(CAPABILITY_FIELDS)}"
            )
            
            

# --- Alert Rules (replace with site's/ regulator's rules/limits) ---
HIGH_RISK_ZONES = {"Blast Zone B", "Old Workings", "Shaft-C Deep"}
FATIGUE_ALERT_SCORE = 70
IMPACT_ALERT_G = 4.0
ENV_LIMITS = {
    "co_ppm": 35,
    "methane_pct": 1.0,
    "ambient_temp_c": 37,
    "noise_db": 85,
    "air_quality_index": 150,
}

ALERT_SEVERITY = {
    "sos": "emergency",
    "fall_impact": "emergency",
    "environment": "high",
    "high_risk_zone": "high",
    "vitals": "high",
    "fatigue": "warning",
    "ppe": "warning",
}