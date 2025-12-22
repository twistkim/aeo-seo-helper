# app/schemas.py
from datetime import datetime
from typing import Optional, List, Any

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
        from_attributes = True


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
        from_attributes = True


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
        from_attributes = True


# ======================
# Improvement 분석(JSON) 스키마
# ======================
class ImprovementIssue(BaseModel):
    title: str
    severity: str = "low"  # high | medium | low
    evidence: Optional[str] = None
    impact: Optional[str] = None
    fix: Optional[str] = None


class ImprovementFAQ(BaseModel):
    q: str
    a: str


class ImprovementAnalysisScores(BaseModel):
    seo: Optional[int] = None
    readability: Optional[int] = None
    structure: Optional[int] = None
    keyword: Optional[int] = None


class ImprovementAnalysisMetrics(BaseModel):
    estimated_paragraphs: Optional[int] = None
    estimated_words: Optional[int] = None
    intro_has_keyword: Optional[bool] = None
    intro_has_brand_or_product: Optional[bool] = None
    faq_count: Optional[int] = None
    video_slot_count: Optional[int] = None


class ImprovementAnalysis(BaseModel):
    summary: Optional[str] = None
    scores: Optional[ImprovementAnalysisScores] = None
    metrics: Optional[ImprovementAnalysisMetrics] = None

    # 우선순위 이슈 목록
    issues: List[ImprovementIssue] = []

    # 개선 적용 순서 / 구조 제안
    rewrite_plan: List[str] = []
    suggested_outline: List[str] = []

    # FAQ/VIDEO 제안
    faq: List[ImprovementFAQ] = []
    video_slots: List[str] = []

    # 최종 체크리스트
    final_checklist: List[str] = []

    # 모델 원문(raw) 보관이 필요하면 여기에 넣어도 됨 (옵션)
    raw_text: Optional[str] = None

    # 파서가 모르는 키가 와도 통과시키기(서비스 안정성)
    model_config = {
        "extra": "allow",
    }


# ======================
# Improvement(블로그 분석 요청) 스키마
# ======================
class ImprovementRequestBase(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    blog_url: str
    core_keyword: str
    analysis_md: Optional[str] = None
    analysis_json: Optional[ImprovementAnalysis] = None
    analysis_version: Optional[str] = None


class ImprovementRequestCreate(ImprovementRequestBase):
    pass


class ImprovementRequestRead(ImprovementRequestBase):
    id: int
    user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ======================
# 마이페이지용 묶음 응답 예시
# ======================
class MyPageData(BaseModel):
    user: UserRead
    articles: List[ArticleRead]
    monitored_keywords: List[MonitoredKeywordRead]
    improvement_requests: List[ImprovementRequestRead] = []