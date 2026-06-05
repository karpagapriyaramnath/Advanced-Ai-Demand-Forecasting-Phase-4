from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .db import session_scope
from .entities import Account

passwords = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/session/signin")
ROLE_ALIASES = {"admin": "super_admin", "planner": "analyst"}
ROLES = {"super_admin", "analyst", "viewer"}


def hash_secret(password: str) -> str:
    return passwords.hash(password)


def check_secret(password: str, password_hash: str) -> bool:
    return passwords.verify(password, password_hash)


def issue_token(email: str, role: str) -> str:
    expiry = datetime.utcnow() + timedelta(minutes=settings.token_minutes)
    return jwt.encode({"sub": email, "role": role, "exp": expiry}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def current_account(token: str = Depends(bearer), db: Session = Depends(session_scope)) -> Account:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        email = payload.get("sub")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    account = db.query(Account).filter(Account.email == email, Account.active.is_(True)).first()
    if not account:
        raise HTTPException(status_code=401, detail="Account not found")
    normalized_role = ROLE_ALIASES.get(account.role, account.role)
    if normalized_role != account.role:
        account.role = normalized_role
        db.commit()
    return account


def admin_account(account: Account = Depends(current_account)) -> Account:
    if account.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin permission required")
    return account


def analyst_account(account: Account = Depends(current_account)) -> Account:
    if account.role not in {"super_admin", "analyst"}:
        raise HTTPException(status_code=403, detail="Analyst permission required")
    return account
