import os
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from . import models, crud, schemas
from .auth import decode_access_token
from .database import get_db

# 로그인 시 토큰을 발급해 줄 엔드포인트 경로
# 나중에 main.py에서 /login POST로 토큰을 발급할 예정이므로 이렇게 맞춰둔다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Depends(oauth2_scheme)],
) -> models.User:
    """
    Authorization 헤더의 Bearer 토큰을 읽어서
    디코딩한 뒤, 해당 유저를 DB에서 조회하여 반환.

    유효하지 않은 토큰이거나, 유저가 존재하지 않으면 401 에러.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        # 디코딩 실패, 서명 오류, 만료 등
        raise credentials_exception

    # 우리는 토큰 생성 시 {"sub": str(user.id)} 형태로 저장할 예정
    user_id_str: Optional[str] = payload.get("sub")  # type: ignore
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise credentials_exception

    user = await crud.get_user(db, user_id=user_id)
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[models.User, Depends(get_current_user)],
) -> models.User:
    """
    기본적으로 활성 유저만 허용하기 위한 의존성.
    current_user.is_active 가 False라면 400 에러.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비활성화된 계정입니다.",
        )
    return current_user


# ======================
# Web(템플릿)용: 쿠키 기반 인증
# ======================
async def get_current_user_from_cookie(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:
    """브라우저 템플릿 라우트에서 쓰는 쿠키 기반 인증.

    - 쿠키 이름은 기본적으로 `access_token` 을 기대한다.
    - 값이 `Bearer <token>` 형태로 저장되어 있어도 처리한다.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="로그인이 필요합니다.",
    )

    raw = request.cookies.get("access_token") or request.cookies.get("token")
    if not raw:
        raise credentials_exception

    token = raw
    if token.startswith("Bearer "):
        token = token[len("Bearer ") :]

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id_str: Optional[str] = payload.get("sub")  # type: ignore
    if not user_id_str:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise credentials_exception

    user = await crud.get_user(db, user_id=user_id)
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user_from_cookie(
    current_user: Annotated[models.User, Depends(get_current_user_from_cookie)],
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비활성화된 계정입니다.",
        )
    return current_user


# ======================
# Admin 권한 체크
# ======================
def _super_admin_email() -> str:
    return (os.getenv("SUPER_ADMIN_EMAIL") or "").strip().lower()


async def require_admin_user(
    current_user: Annotated[models.User, Depends(get_current_active_user_from_cookie)],
) -> models.User:
    """최고관리자만 접근 허용.

    SUPER_ADMIN_EMAIL 환경변수와 current_user.email 이 일치해야 통과.
    """
    admin_email = _super_admin_email()
    if not admin_email:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPER_ADMIN_EMAIL 이 설정되지 않았습니다.",
        )

    if (current_user.email or "").strip().lower() != admin_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 접근할 수 있습니다.",
        )

    return current_user


# (선택) API(Bearer 토큰)용 관리자 체크가 필요할 때 사용
async def require_admin_user_bearer(
    current_user: Annotated[models.User, Depends(get_current_active_user)],
) -> models.User:
    admin_email = _super_admin_email()
    if not admin_email:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPER_ADMIN_EMAIL 이 설정되지 않았습니다.",
        )

    if (current_user.email or "").strip().lower() != admin_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 접근할 수 있습니다.",
        )

    return current_user