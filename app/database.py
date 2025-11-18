# app/database.py
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

# .env 로드
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

# 비동기 엔진 생성
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # 디버깅 시 True로 바꾸면 SQL이 콘솔에 찍힘
    future=True,
)

# 세션 팩토리
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Base 클래스 (모든 ORM 모델이 상속)
Base = declarative_base()


# FastAPI 의존성에서 사용할 DB 세션
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# 테이블 생성용 유틸 (앱 시작 시 한 번 호출)
async def init_db():
    """
    애플리케이션 시작 시 테이블을 생성하고 싶을 때 사용.
    main.py에서 startup 이벤트에 연결해서 쓸 예정.
    """
    from . import models  # 모델을 임포트해서 Base.metadata에 등록

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)