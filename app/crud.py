# app/crud.py
from typing import Optional, List

from sqlalchemy import select
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