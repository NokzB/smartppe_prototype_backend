from fastapi import HTTPException, status

from app.config import DEFAULT_BASELINE, USERS_FILE
from app.models import UserRegister
from app.security import hash_password
from app.storage import read, update


def register_user(payload: UserRegister) -> dict:
    def _mutate(users: list):
        if any(u["employee_id"] == payload.employee_id for u in users):
            raise HTTPException(status.HTTP_409_CONFLICT, "Employee ID already registered")
        if any(u["email"].lower() == payload.email.lower() for u in users):
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

        new_user = {
            "employee_id": payload.employee_id,
            "name": payload.name,
            "surname": payload.surname,
            "role": payload.role,
            "email": payload.email,
            "phone": payload.phone,
            "area": payload.area,
            "password_hash": hash_password(payload.password),
            "company_name": payload.company_name,
            "baseline": dict(DEFAULT_BASELINE),
        }
        users.append(new_user)
        return users

    users = read(USERS_FILE) or []
    updated = update(USERS_FILE, _mutate)
    return next(u for u in updated if u["employee_id"] == payload.employee_id)


def find_user_by_email(email: str) -> dict | None:
    users = read(USERS_FILE) or []
    return next((u for u in users if u["email"].lower() == email.lower()), None)


def set_baseline(employee_id: str, baseline: dict) -> dict:
    def _mutate(users: list):
        for u in users:
            if u["employee_id"] == employee_id:
                u["baseline"] = baseline
                return users
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")

    updated = update(USERS_FILE, _mutate)
    return next(u for u in updated if u["employee_id"] == employee_id)


def list_employees() -> list[dict]:
    users = read(USERS_FILE) or []
    return users

def get_employee(employee_id: str) -> dict:
    users = read(USERS_FILE) or []
    user = next((u for u in users if u["employee_id"] == employee_id), None)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return user

def update_employee(employee_id: str, fields: dict) -> dict:
    def _mutate(users: list):
        for u in users:
            if u["employee_ud"] == employee_id:
                if "email" in fields and fields["email"]:
                        if any(other["email"].lower() == fields["email"].lower() and other["employee_id"] != employee_id for other in users):
                            raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use by other employee")
                        u.update({k: v for k, v in fields.items() if v is not None})
                        return users
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    
    updated = update(USERS_FILE, _mutate)
    return next(u for u in updated if u["employee_id"] == employee_id)


def delete_employee(employee_id: str) -> None:
    def _mutate(users: list):
        remaining = [u for u in users if u["employee_id"] != employee_id]
        if len(remaining) == len(users):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
        return remaining
    
    update(USERS_FILE, _mutate)