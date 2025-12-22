# app/crud.py
from typing import Optional, List
from datetime import datetime
import json

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from . import models, schemas
from .auth import get_password_hash, verify_password


# ==========================
# User 관련 CRUD
# ==========================
async def get_user_by_email(
    db: AsyncSession,
    email: str,
) -> Optional[models.User]:
    """
    이메일로 유저 한 명 조회
    """
    result = await db.execute(
        select(models.User).where(models.User.email == email)
    )
    return result.scalar_one_or_none()


async def get_user(
    db: AsyncSession,
    user_id: int,
) -> Optional[models.User]:
    """
    id로 유저 한 명 조회
    """
    result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    user_in: schemas.UserCreate,
) -> models.User:
    """
    회원가입: 비밀번호를 해싱한 후 DB에 유저 생성
    """
    hashed_password = get_password_hash(user_in.password)

    user = models.User(
        email=user_in.email,
        hashed_password=hashed_password,
        full_name=user_in.full_name,
        is_active=True,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> Optional[models.User]:
    """
    로그인 시 사용:
    - 이메일로 유저 조회
    - 비밀번호 검증
    둘 다 통과하면 User 반환, 아니면 None
    """
    user = await get_user_by_email(db, email=email)
    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


# ==========================
# Article (블로그 원고) 관련 CRUD
# ==========================
async def create_article(
    db: AsyncSession,
    user_id: int,
    article_in: schemas.ArticleCreate,
) -> models.Article:
    """
    Gemini로 생성된 블로그 원고를 DB에 저장
    """
    article = models.Article(
        user_id=user_id,
        title=article_in.title,
        core_keyword=article_in.core_keyword,
        product_name=article_in.product_name,
        target_audience=article_in.target_audience,
        tone=article_in.tone,
        content=article_in.content,
    )

    db.add(article)
    await db.commit()
    await db.refresh(article)

    return article


async def list_user_articles(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
) -> List[models.Article]:
    """
    특정 유저가 생성한 블로그 원고 목록 조회 (최신순)
    """
    result = await db.execute(
        select(models.Article)
        .where(models.Article.user_id == user_id)
        .order_by(models.Article.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ==========================
# 순위 모니터링 기록 관련 CRUD
# ==========================
async def create_monitored_keyword(
    db: AsyncSession,
    user_id: int,
    monitored_in: schemas.MonitoredKeywordCreate,
) -> models.MonitoredKeyword:
    """키워드 순위 체크 결과 한 건을 DB에 저장.

    - web_rank: 네이버 웹검색 기준 순위 (없으면 None)
    - blog_rank: 네이버 블로그검색 기준 순위 (없으면 None)
    """
    record = models.MonitoredKeyword(
        user_id=user_id,
        keyword=monitored_in.keyword,
        blog_url=monitored_in.blog_url,
        log_no=monitored_in.log_no,
        web_rank=monitored_in.web_rank,
        blog_rank=monitored_in.blog_rank,
    )

    db.add(record)
    await db.commit()
    await db.refresh(record)

    return record


async def list_user_monitored_keywords(
    db: AsyncSession,
    user_id: int,
    limit: int = 100,
) -> List[models.MonitoredKeyword]:
    """특정 유저의 순위 모니터링 기록 목록 조회 (최신순)

    MonitoredKeyword.last_checked_at 기준 내림차순으로 정렬한다.
    """

    result = await db.execute(
        select(models.MonitoredKeyword)
        .where(models.MonitoredKeyword.user_id == user_id)
        .order_by(models.MonitoredKeyword.last_checked_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


def _to_json_text(value) -> Optional[str]:
    """Normalize analysis_json payload to a JSON string for DB storage."""
    if value is None:
        return None

    # already a JSON string
    if isinstance(value, str):
        return value

    # Pydantic v2 model
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            pass

    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        # last resort: stringify
        return json.dumps({"raw": str(value)}, ensure_ascii=False)


# ==========================
# Improvement (블로그 분석 요청) 관련 CRUD
# ==========================
async def create_improvement_request(
    db: AsyncSession,
    user_id: Optional[int],
    req_in: schemas.ImprovementRequestCreate,
) -> models.ImprovementRequest:
    """
    네이버 블로그 분석 요청 1건 저장
    (비로그인 사용자도 user_id=None 으로 저장 가능)
    """
    record = models.ImprovementRequest(
        user_id=user_id,
        company_name=req_in.company_name,
        contact_name=req_in.contact_name,
        phone=req_in.phone,
        email=req_in.email,
        blog_url=req_in.blog_url,
        core_keyword=req_in.core_keyword,
        analysis_md=req_in.analysis_md,
        analysis_json=_to_json_text(getattr(req_in, "analysis_json", None)),
        analysis_version=getattr(req_in, "analysis_version", None),
    )

    db.add(record)
    await db.commit()
    await db.refresh(record)

    return record


async def list_user_improvement_requests(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
) -> List[models.ImprovementRequest]:
    """
    특정 유저의 블로그 분석 요청 목록 조회 (최신순)
    """
    result = await db.execute(
        select(models.ImprovementRequest)
        .where(models.ImprovementRequest.user_id == user_id)
        .order_by(models.ImprovementRequest.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ==========================
# Admin: Improvement 전체 조회/상세 조회
# ==========================
async def get_improvement_request_by_id(
    db: AsyncSession,
    request_id: int,
) -> Optional[models.ImprovementRequest]:
    """improvement_requests 단건 조회 (관리자 상세보기용)."""
    result = await db.execute(
        select(models.ImprovementRequest)
        .where(models.ImprovementRequest.id == request_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_all_improvement_requests(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    q: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[models.ImprovementRequest]:
    """전체 improvement_requests 조회 (최신순).

    - q: 회사명/담당자/전화/이메일/키워드/URL 에 대해 부분일치 검색
    - date_from/date_to: created_at 기준 범위 필터
    - limit/offset: 페이지네이션
    """
    stmt = select(models.ImprovementRequest)

    # 검색어 필터
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                models.ImprovementRequest.company_name.ilike(like),
                models.ImprovementRequest.contact_name.ilike(like),
                models.ImprovementRequest.phone.ilike(like),
                models.ImprovementRequest.email.ilike(like),
                models.ImprovementRequest.core_keyword.ilike(like),
                models.ImprovementRequest.blog_url.ilike(like),
            )
        )

    # 날짜 범위 필터
    if date_from:
        stmt = stmt.where(models.ImprovementRequest.created_at >= date_from)
    if date_to:
        stmt = stmt.where(models.ImprovementRequest.created_at <= date_to)

    stmt = (
        stmt.order_by(models.ImprovementRequest.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(stmt)
    return result.scalars().all()