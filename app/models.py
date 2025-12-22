# app/models.py
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import LONGTEXT

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 관계
    articles = relationship(
        "Article",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    monitored_keywords = relationship(
        "MonitoredKeyword",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    improvement_requests = relationship(
        "ImprovementRequest",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Article(Base):
    """
    Gemini로 생성한 블로그 원고 저장용 테이블
    """

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 사용자가 입력한 조건들
    title = Column(String(255), nullable=True)
    core_keyword = Column(String(255), nullable=True)
    product_name = Column(String(255), nullable=True)
    target_audience = Column(String(255), nullable=True)
    tone = Column(String(255), nullable=True)

    # 실제 생성된 본문
    content = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 관계
    user = relationship("User", back_populates="articles")


class MonitoredKeyword(Base):
    """순위 모니터링 기록 테이블
    한 번 체크할 때마다 한 행이 추가되는 구조.
    """

    __tablename__ = "monitored_keywords"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    keyword = Column(String(255), nullable=False)           # 검색어
    blog_url = Column(Text, nullable=False)                 # 추적 대상 블로그 URL
    log_no = Column(String(50), nullable=True)              # 블로그 글번호(logNo)

    web_rank = Column(Integer, nullable=True)               # 네이버 웹검색 순위 (없으면 None)
    blog_rank = Column(Integer, nullable=True)              # 네이버 블로그검색 순위 (없으면 None)

    last_checked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 관계
    user = relationship("User", back_populates="monitored_keywords")


class ImprovementRequest(Base):
    """네이버 블로그 분석/개선안 요청 저장 테이블

    비로그인 사용자도 저장 가능하도록 user_id 는 nullable.
    """

    __tablename__ = "improvement_requests"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    company_name = Column(String(255), nullable=True)
    contact_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)

    blog_url = Column(Text, nullable=False)
    core_keyword = Column(String(255), nullable=False, index=True)

    analysis_md = Column(Text, nullable=True)
    # 구조화(JSON) 분석 결과 저장 (UI 렌더링/버전관리용)
    analysis_json = Column(LONGTEXT, nullable=True)
    analysis_version = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="improvement_requests")