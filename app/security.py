from datetime import datetime, timedelta, timezone
import uuid


from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY, REVOKED_TOKENS_FILE
from app.storage import read, update
from app.config import USERS_FILE

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "jti": uuid.uuid4().hex})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def revoke_token(jti: str, expired_at: datetime) -> None:
    def _mutate(revoked: list):
        revoked = revoked or []
        revoked.append({"jti": jti, "expires_at": expires_at.isoformat()})
        return revoked
    update(REVOKED_TOKENS_FILE, _mutate)
   
    
def _is_token_revoked(jti: str) -> bool:
    revoked = read(REVOKED_TOKENS_FILE) or []
    return any(r["jti"] == jti for r in revoked)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    employee_id = payload.get("sub")
    jti = payload.get("jti")
    if not employee_id or not jti:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    if _is_token_revoked(jti):
        raise HTTPException(status_code=401, detail="Session has ended - please log in again")


    users = read(USERS_FILE) or []
    user = next((u for u in users if u["employee_id"] == employee_id), None)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    
    user = dict(user)
    user["_jti"] = jti
    user["_exp"] = payload.get("exp")
    return user


def require_roles(*allowed_roles: str):
    """Dependency factory for role-based access control on routes."""

    def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {allowed_roles}",
            )
        return user

    return _checker
