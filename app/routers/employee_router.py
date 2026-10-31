from fastapi import APIRouter, Depends, HTTPException, status

from app.models import EmployeeUpdate, UserPublic, UserRegister
from app.security import require_roles
from app.services.user_service import (
    delete_employee,
    get_employee,
    list_employees,
    register_user,
    update_employee,
)

router = APIRouter(prefix="/admin/employees", tags=["employees"])


@router.get("", response_model=list[UserPublic])
def get_employees(user: dict = Depends(require_roles("admin"))):
    return list_employees()


@router.get("/{employee_id}", response_model=UserPublic)
def get_employee_by_id(employee_id: str, user: dict = Depends(require_roles("admin"))):
    return get_employee(employee_id)


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def create_employee(payload: UserRegister, user: dict = Depends(require_roles("admin"))):
    return register_user(payload)


@router.put("/{employee_id}", response_model=UserPublic)
def edit_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    user: dict = Depends(require_roles("admin")),
):
    updated = update_employee(employee_id, payload.model_dump(exclude_unset=True))
    return updated


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_employee(employee_id: str, user: dict = Depends(require_roles("admin"))):
    if employee_id == user["employee_id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't delete your own account while logged in as it")
    delete_employee(employee_id)
    return