# app/schemas.py
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr


# ======================
# 공통 User 스키마
# ======================
class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(UserBase):
    id: int
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True


# ======================
# JWT 토큰 관련 스키마
# ======================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None


# ======================
# Article(블로그 원고) 스키마
# ======================
class ArticleBase(BaseModel):
    title: Optional[str] = None
    core_keyword: Optional[str] = None
    product_name: Optional[str] = None
    target_audience: Optional[str] = None
    tone: Optional[str] = None
    content: str


class ArticleCreate(ArticleBase):
    pass


class ArticleRead(ArticleBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        orm_mode = True


# ======================
# 순위 모니터링 기록 스키마
# ======================
class MonitoredKeywordBase(BaseModel):
    keyword: str
    blog_url: str


class MonitoredKeywordCreate(MonitoredKeywordBase):
    log_no: Optional[str] = None
    web_rank: Optional[int] = None
    blog_rank: Optional[int] = None


class MonitoredKeywordRead(MonitoredKeywordBase):
    id: int
    user_id: int
    log_no: Optional[str] = None
    web_rank: Optional[int] = None
    blog_rank: Optional[int] = None
    last_checked_at: datetime
    created_at: datetime

    class Config:
        orm_mode = True


# ======================
# 마이페이지용 묶음 응답 예시
# ======================
class MyPageData(BaseModel):
    user: UserRead
    articles: List[ArticleRead]
    monitored_keywords: List[MonitoredKeywordRead]