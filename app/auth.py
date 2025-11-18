# app/auth.py
from datetime import datetime, timedelta
import os
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

# .env 로드
load_dotenv()

# ==========================
# 환경 변수 설정
# ==========================
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_PLEASE")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# 기본 토큰 만료 시간 (분)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# 비밀번호 해싱 설정 (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ==========================
# 비밀번호 관련 함수
# ==========================
MAX_BCRYPT_BYTES = 72


def _truncate_for_bcrypt(password: str) -> str:
    """
    bcrypt는 최대 72바이트까지 지원한다.
    해싱/검증 모두에서 동일한 규칙으로 비밀번호를 잘라서 사용한다.
    여기서는 간단하게 최대 72자까지 자른다.
    """
    if len(password) > MAX_BCRYPT_BYTES:
        return password[:MAX_BCRYPT_BYTES]
    return password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    사용자가 입력한 평문 비밀번호와, DB에 저장된 해시 비밀번호를 비교.
    bcrypt의 72바이트 제한에 맞추기 위해 동일한 규칙으로 잘라서 비교한다.
    """
    plain_password = _truncate_for_bcrypt(plain_password)
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    평문 비밀번호를 bcrypt로 해싱해서 반환.
    DB에는 잘린 비밀번호(동일 규칙 적용 후)의 해시값만 저장한다.
    """
    password = _truncate_for_bcrypt(password)
    return pwd_context.hash(password)


# ==========================
# JWT 관련 함수
# ==========================
def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    주어진 데이터로 JWT 액세스 토큰을 생성.
    보통 data에는 {"sub": str(user.id)} 같은 정보를 넣는다.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    JWT 토큰을 디코딩하여 payload(dict)를 반환.
    유효하지 않으면 None을 반환.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None