import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.models import RevokedToken, User
from app.schemas.auth import UserCreate, UserLogin, Token, UserInfo, PasswordChange
from app.core.security import (
    get_current_user,
    verify_password,
    create_access_token,
    get_password_hash,
    security,
)
from app.core.rate_limit import login_limiter

logger = logging.getLogger(__name__)

router = APIRouter()


def _utcnow_naive() -> datetime:
    """当前 UTC 时间（naive），与 RevokedToken.expires_at 的 naive UTC 存储约定一致。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.post("/register", response_model=UserInfo)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名或邮箱已存在"
        )

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        role="user"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=Token)
async def login(login_data: UserLogin, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{login_data.username}|{client_ip}"
    if login_limiter.is_blocked(db, rate_key):
        logger.warning("登录被限流拒绝：key=%s", rate_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"尝试次数过多，请 {settings.LOGIN_RATE_LIMIT_WINDOW_MINUTES} 分钟后再试",
        )

    user = db.query(User).filter(User.username == login_data.username).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        login_limiter.record_failure(db, rate_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")

    login_limiter.reset(db, rate_key)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(
    credentials=Depends(security),
    db: Session = Depends(get_db),
):
    """注销：将当前 token 的 jti 加入黑名单，直至其原过期时间。"""
    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录状态")

    jti = payload.get("jti")
    if jti:
        # 顺手清理已过期的黑名单记录，防止表无限膨胀
        db.query(RevokedToken).filter(RevokedToken.expires_at < _utcnow_naive()).delete()
        exp = payload.get("exp")
        expires_at = (
            datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None)
            if exp else _utcnow_naive()
        )
        db.merge(RevokedToken(jti=jti, expires_at=expires_at))
        db.commit()
        logger.info("token 已吊销：jti=%s", jti)
    return {"message": "已退出登录"}


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
async def change_password(
    pwd_data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not verify_password(pwd_data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="旧密码不正确")

    current_user.hashed_password = get_password_hash(pwd_data.new_password)
    db.commit()
    return {"message": "密码修改成功"}
