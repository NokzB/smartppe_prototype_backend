from fastapi import APIRouter, HTTPException, status
# from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends
from datetime import datetime, timezone


from app.models import LoginRequest, LoginResponse, Token, UserPublic, UserRegister, CurrentUserResponse
from app.security import create_access_token, verify_password, require_roles, revoke_token, get_current_user
from app.services.user_service import find_user_by_email, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister):
    user = register_user(payload)
    return UserPublic(**user)


def _build_current_user_response(user: dict) -> CurrentUserResponse:
    return CurrentUserResponse(
        welcome_message=f"Welcome, {user['name']} {user['surname']}",
        employee_id=user["employee_id"],
        name=user["name"],
        surname=user["surname"],
        role=user["role"],
        email=user["email"],
        phone=user["phone"],
        area=user.get("area"),
        company_name=user.get("company_name"),
    )


@router.post("/login", response_model=Token)
# def login(form_data: OAuth2PasswordRequestForm = Depends()):
def login(payload: LoginRequest):
    # form_data.username carries the email (OAuth2 password flow convention)
    user = find_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token({"sub": user["employee_id"], "role": user["role"]})
    return LoginResponse(access_token=token, user=_build_current_user_response(user))


@router.get("/me", response_model=CurrentUserResponse)
def get_current_user_info(user: dict = Depends(get_current_user)):
    return _build_current_user_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: dict = Depends(require_roles("admin"))):
    exp_timestamp = user.get("_exp")
    expires_at= datetime.fromtimestamp(exp_timestamp, tx=timezone.utc)
    revoke_token(user["_jti"], expires_at)
    return