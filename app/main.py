# app/main.py
from typing import Optional
from pydantic import ValidationError

from fastapi import (
    FastAPI,
    Request,
    Depends,
    Form,
    status,
    UploadFile,
    File,
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Boolean, ForeignKey, func

from .database import init_db, get_db
from . import schemas, crud, models
from .auth import create_access_token, decode_access_token
from .dependencies import get_current_active_user, require_admin_user
from . import services


# ==========================
# FastAPI 앱 생성 & 설정
# ==========================
app = FastAPI(title="AEO SEO Helper")

# 정적 파일 (CSS, JS 등)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Jinja2 템플릿 설정
templates = Jinja2Templates(directory="app/templates")


# ==========================
# 앱 시작 시 DB 테이블 생성
# ==========================
@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


# ==========================
# 쿠키에서 현재 로그인 유저 가져오기 (웹용)
# ==========================
# ==========================
# 쿠키에서 현재 로그인 유저 가져오기 (웹용)
# ==========================
async def get_current_user_from_cookie(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> models.User:
    """
    /login 에서 발급한 JWT를 access_token 쿠키에서 읽어와
    현재 로그인한 유저를 반환한다.
    토큰이 없거나 유효하지 않으면 401 에러 발생.
    """
    token_cookie = request.cookies.get("access_token")
    if not token_cookie:
        # 로그인 안 된 상태
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
        )

    # 쿠키 값은 "Bearer <token>" 형태로 저장되어 있음
    if token_cookie.startswith("Bearer "):
        token = token_cookie[len("Bearer ") :]
    else:
        token = token_cookie

    payload = decode_access_token(token)
    if payload is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 유효하지 않습니다. 다시 로그인해 주세요.",
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 사용자 정보가 없습니다.",
        )

    try:
        user_id = int(user_id_str)
    except ValueError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 잘못된 사용자 정보가 포함되어 있습니다.",
        )

    user = await crud.get_user(db, user_id=user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    return user

# ==========================
# 쿠키에서 현재 로그인 유저 가져오기 (옵션: 비로그인 허용)
# ==========================
async def get_optional_user_from_cookie(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[models.User]:
    """access_token 쿠키가 있으면 유저를 반환하고, 없거나 유효하지 않으면 None."""
    token_cookie = request.cookies.get("access_token")
    if not token_cookie:
        return None

    if token_cookie.startswith("Bearer "):
        token = token_cookie[len("Bearer ") :]
    else:
        token = token_cookie

    payload = decode_access_token(token)
    if payload is None:
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    try:
        user_id = int(user_id_str)
    except ValueError:
        return None

    user = await crud.get_user(db, user_id=user_id)
    return user

# ==========================
# 기본 라우트
# ==========================
# @app.get("/", response_class=HTMLResponse)
# async def root(request: Request):
#     """
#     루트 접근 시 /improvement 로 리다이렉트
#     """
#     return RedirectResponse(url="/improvement", status_code=status.HTTP_302_FOUND)

# from fastapi import Request
# from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request
        }
    )

# ==========================
# 회원가입 (Signup)
# ==========================
@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    """
    회원가입 폼 화면
    """
    return templates.TemplateResponse(
        "auth/signup.html",
        {
            "request": request,
            "error": None,
        },
    )


@app.post("/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    회원가입 처리:
    - 이미 존재하는 이메일인지 확인
    - 아니면 유저 생성
    - 완료 후 /login 으로 리다이렉트
    """
    existing = await crud.get_user_by_email(db, email=email)
    if existing:
        # 이미 가입된 이메일
        return templates.TemplateResponse(
            "auth/signup.html",
            {
                "request": request,
                "error": "이미 사용 중인 이메일입니다.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user_in = schemas.UserCreate(
        email=email,
        password=password,
        full_name=full_name,
    )
    await crud.create_user(db, user_in=user_in)

    # 회원가입 완료 후 로그인 페이지로 이동 (쿼리스트링으로 메시지 전달)
    return RedirectResponse(
        url="/login?msg=signup_success",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ==========================
# 로그인 (Login)
# ==========================
@app.get("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    msg: Optional[str] = None,
):
    """
    로그인 폼 화면
    - msg=signup_success 이면 상단에 '회원가입 완료' 메시지 표시
    """
    message = None
    if msg == "signup_success":
        message = "회원가입이 완료되었습니다. 로그인 해주세요."

    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "error": None,
            "message": message,
        },
    )


@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    로그인 처리:
    - 이메일로 유저 조회
    - 비밀번호 검증
    - 성공 시 JWT 액세스 토큰 생성
    - 토큰을 쿠키에 저장하고, 추후 보호된 페이지로 리다이렉트
    """
    user = await crud.authenticate_user(db, email=email, password=password)
    if not user:
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "error": "이메일 또는 비밀번호가 올바르지 않습니다.",
                "message": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # JWT 액세스 토큰 생성
    access_token = create_access_token(data={"sub": str(user.id)})

    # 일단 쿠키에 저장 (나중에 의존성에서 쿠키 읽도록 확장 가능)
    response = RedirectResponse(
        url="/generator",  # 추후 생성할 '블로그 원고 생성' 페이지
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
    )
    return response


# ==========================
# 로그인 확인용 샘플 엔드포인트
# ==========================
@app.get("/me", response_model=schemas.UserRead)
async def read_me(current_user: models.User = Depends(get_current_active_user)):
    """
    현재 로그인한 유저 정보 확인용 (Swagger에서 토큰으로 테스트 가능)
    """
    return current_user

# ==========================
# 로그아웃
# ==========================
@app.get("/logout")
async def logout():
    """
    access_token 쿠키를 삭제하고 로그인 페이지로 리다이렉트
    """
    response = RedirectResponse(
        url="/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie("access_token")
    return response

# ==========================
# 블로그 원고 자동 생성 (/generator)
# ==========================
@app.get("/generator", response_class=HTMLResponse)
async def generator_form(
    request: Request,
    current_user: models.User = Depends(get_current_user_from_cookie),
):
    """
    블로그 원고 생성 폼 화면.
    로그인한 사용자만 접근 가능.
    """
    return templates.TemplateResponse(
        "generator.html",
        {
            "request": request,
            "user": current_user,
            "error": None,
            "result": None,
            "form": {
                "core_keyword": "",
                "product_name": "",
                "brand": "",
                "target_audience": "",
                "intent": "",
                "persona": "",
                "tone": "",
                "must_keywords": "",
                "must_headings": "",
                "cta_text": "",
                "banned_terms": "",
                "additional_instructions": "",
            },
        },
    )


@app.post("/generator", response_class=HTMLResponse)
async def generate_post(
    request: Request,
    core_keyword: str = Form(...),
    product_name: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    target_audience: Optional[str] = Form(None),
    intent: Optional[str] = Form(None),
    persona: Optional[str] = Form(None),
    tone: Optional[str] = Form(None),
    must_keywords: Optional[str] = Form(None),
    must_headings: Optional[str] = Form(None),
    cta_text: Optional[str] = Form(None),
    banned_terms: Optional[str] = Form(None),
    additional_instructions: Optional[str] = Form(None),
    product_detail_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie),
):
    """
    폼 데이터를 받아 Gemini API를 호출하고,
    생성된 원고를 DB에 저장한 뒤 화면에 표시.
    """
    # 필수 값 체크
    if not core_keyword.strip():
        return templates.TemplateResponse(
            "generator.html",
            {
                "request": request,
                "user": current_user,
                "error": "핵심 키워드는 필수입니다.",
                "result": None,
                "form": {
                    "core_keyword": core_keyword or "",
                    "product_name": product_name or "",
                    "brand": brand or "",
                    "target_audience": target_audience or "",
                    "intent": intent or "",
                    "persona": persona or "",
                    "tone": tone or "",
                    "must_keywords": must_keywords or "",
                    "must_headings": must_headings or "",
                    "cta_text": cta_text or "",
                    "banned_terms": banned_terms or "",
                    "additional_instructions": additional_instructions or "",
                },
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 제품 상세 .txt 파일 내용 읽기 (있으면)
    product_detail_text: Optional[str] = None
    if product_detail_file and product_detail_file.filename:
        raw = await product_detail_file.read()
        try:
            product_detail_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            # 혹시 인코딩이 다른 경우를 대비해 대충이라도 읽기
            product_detail_text = raw.decode("cp949", errors="ignore")

    try:
        # Gemini로 블로그 원고 생성
        content = services.generate_blog_post(
            core_keyword=core_keyword,
            product_name=product_name,
            brand=brand,
            target_audience=target_audience,
            intent=intent,
            persona=persona,
            tone=tone,
            must_keywords=must_keywords,
            must_headings=must_headings,
            cta_text=cta_text,
            banned_terms=banned_terms,
            product_detail_text=product_detail_text,
            additional_instructions=additional_instructions,
        )
    except Exception as e:
        # Gemini 호출 실패 시 에러 메시지 표시
        return templates.TemplateResponse(
            "generator.html",
            {
                "request": request,
                "user": current_user,
                "error": f"원고 생성 중 오류가 발생했습니다: {e}",
                "result": None,
                "form": {
                    "core_keyword": core_keyword or "",
                    "product_name": product_name or "",
                    "brand": brand or "",
                    "target_audience": target_audience or "",
                    "intent": intent or "",
                    "persona": persona or "",
                    "tone": tone or "",
                    "must_keywords": must_keywords or "",
                    "must_headings": must_headings or "",
                    "cta_text": cta_text or "",
                    "banned_terms": banned_terms or "",
                    "additional_instructions": additional_instructions or "",
                },
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # DB에 저장할 Article 데이터 준비 (기본 필드만 우선 저장)
    article_in = schemas.ArticleCreate(
        title=None,  # 나중에 제목 추출 로직을 붙여도 됨
        core_keyword=core_keyword,
        product_name=product_name,
        target_audience=target_audience,
        tone=tone,
        content=content,
    )

    article = await crud.create_article(
        db,
        user_id=current_user.id,
        article_in=article_in,
    )

    # 생성 결과를 같은 페이지에서 보여준다.
    return templates.TemplateResponse(
        "generator.html",
        {
            "request": request,
            "user": current_user,
            "error": None,
            "result": {
                "article_id": article.id,
                "content": article.content,
                "core_keyword": article.core_keyword,
                "product_name": article.product_name,
                "target_audience": article.target_audience,
                "tone": article.tone,
            },
            "form": {
                "core_keyword": core_keyword or "",
                "product_name": product_name or "",
                "brand": brand or "",
                "target_audience": target_audience or "",
                "intent": intent or "",
                "persona": persona or "",
                "tone": tone or "",
                "must_keywords": must_keywords or "",
                "must_headings": must_headings or "",
                "cta_text": cta_text or "",
                "banned_terms": banned_terms or "",
                "additional_instructions": additional_instructions or "",
            },
        },
    )



@app.get("/improvement", response_class=HTMLResponse)
async def improvement_page(
    request: Request,
    current_user: Optional[models.User] = Depends(get_optional_user_from_cookie),
):
    return templates.TemplateResponse(
        "improvement.html",
        {
            "request": request,
            "user": current_user,
        },
    )


@app.post("/improvement")
async def improvement_action(
    request: Request,
    blog_url: str = Form(...),
    core_keyword: str = Form(...),
    company_name: Optional[str] = Form(None),
    contact_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_optional_user_from_cookie),
):
    try:
        # 1) URL에서 본문 크롤링
        content = services.scrape_url_content(blog_url)

        # 2) Gemini로 분석/개선안 생성
        #    - 신규: JSON 스키마 분석 (서비스 UI용)
        #    - 폴백: 기존 마크다운/텍스트 그대로 보여주기
        analysis_json, raw_text = services.analyze_blog_post_json(
            blog_text=content,
            core_keyword=core_keyword,
            blog_url=blog_url,
            max_retries=1,
        )

        # 화면/DB 폴백용 텍스트: JSON이 성공해도 원문(raw_text)을 같이 저장해두면 디버깅에 유리
        analysis_md = (raw_text or "").strip()

        # 3) DB 저장 (비로그인도 저장 가능)
        saved_id = None
        try:
            payload = {
                "company_name": company_name,
                "contact_name": contact_name,
                "phone": phone,
                "email": email,
                "blog_url": blog_url,
                "core_keyword": core_keyword,
                "analysis_md": analysis_md,
                # 구조화(JSON) 결과 + 버전 (schemas.py에서 ImprovementAnalysis로 검증)
                "analysis_json": analysis_json,
                "analysis_version": ("v1" if analysis_json is not None else None),
            }

            try:
                req_in = schemas.ImprovementRequestCreate(**payload)
            except ValidationError as ve:
                # JSON 분석 결과가 스키마에 맞지 않아도, 분석 텍스트는 저장/반환할 수 있게 폴백
                payload["analysis_json"] = None
                payload["analysis_version"] = None
                req_in = schemas.ImprovementRequestCreate(**payload)

            saved = await crud.create_improvement_request(
                db,
                user_id=(current_user.id if current_user else None),
                req_in=req_in,
            )
            saved_id = getattr(saved, "id", None)
        except Exception:
            # 저장 실패해도 분석 결과는 반환
            saved_id = None

        return JSONResponse(
            {
                "success": True,
                # 서비스 UI에서 우선 사용할 구조화 결과
                "analysis_json": analysis_json,
                # JSON이 없거나 디버깅이 필요할 때 표시할 원문(기존처럼)
                "analysis": analysis_md,
                "request_id": saved_id,
            }
        )
    except Exception as e:
        return JSONResponse(
            {
                "success": False,
                "error": str(e),
            }
        )


# ==========================
# 네이버 검색 순위 모니터링 (/monitoring)
# ==========================
@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie),
):
    """순위 모니터링 폼 + 최근 기록 리스트 화면"""
    logs = await crud.list_user_monitored_keywords(
        db,
        user_id=current_user.id,
        limit=50,
    )

    return templates.TemplateResponse(
        "monitoring.html",
        {
            "request": request,
            "user": current_user,
            "logs": logs,
            "result": None,
            "error": None,
            "form": {
                "keyword": "",
                "blog_url": "",
            },
        },
    )


@app.post("/monitoring", response_class=HTMLResponse)
async def monitoring_action(
    request: Request,
    keyword: str = Form(...),
    blog_url: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie),
):
    """키워드 + 블로그 URL로 네이버 검색 순위를 체크하고 결과를 저장"""
    error: Optional[str] = None
    result_data = None

    if not keyword.strip() or not blog_url.strip():
        error = "키워드와 블로그 URL을 모두 입력해 주세요."
    else:
        try:
            # 1) 네이버 검색 API를 통해 현재 순위 확인
            rank_info = services.check_naver_rank(
                keyword=keyword,
                blog_url=blog_url,
            )

            # 2) DB에 기록 저장
            mk_create = schemas.MonitoredKeywordCreate(
                keyword=keyword,
                blog_url=blog_url,
                log_no=rank_info.get("log_no"),
                web_rank=rank_info.get("web_rank"),
                blog_rank=rank_info.get("blog_rank"),
            )

            record = await crud.create_monitored_keyword(
                db,
                user_id=current_user.id,
                monitored_in=mk_create,
            )

            result_data = {
                "keyword": record.keyword,
                "blog_url": record.blog_url,
                "log_no": record.log_no,
                "web_rank": record.web_rank,
                "blog_rank": record.blog_rank,
            }
        except Exception as e:
            error = f"순위 확인 중 오류가 발생했습니다: {e}"

    # 항상 최신 로그 목록을 다시 불러와서 화면에 표시
    logs = await crud.list_user_monitored_keywords(
        db,
        user_id=current_user.id,
        limit=50,
    )

    return templates.TemplateResponse(
        "monitoring.html",
        {
            "request": request,
            "user": current_user,
            "logs": logs,
            "result": result_data,
            "error": error,
            "form": {
                "keyword": keyword or "",
                "blog_url": blog_url or "",
            },
        },
    )

# ==========================
# 마이페이지 (/mypage)
# ==========================
@app.get("/mypage", response_class=HTMLResponse)
async def mypage(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie),
):
    """
    내가 생성한 블로그 원고 + 키워드 모니터링 기록을 한 화면에서 보는 페이지
    """
    # 내가 만든 원고들
    articles = await crud.list_user_articles(
        db,
        user_id=current_user.id,
        limit=50,
    )

    # 내가 체크한 순위 모니터링 로그
    logs = await crud.list_user_monitored_keywords(
        db,
        user_id=current_user.id,
        limit=50,
    )

    # 내가 요청한 블로그 개선(분석) 기록
    improvement_requests = await crud.list_user_improvement_requests(
        db,
        user_id=current_user.id,
        limit=50,
    )

    return templates.TemplateResponse(
        "mypage.html",
        {
            "request": request,
            "user": current_user,
            "articles": articles,
            "logs": logs,
            "improvement_requests": improvement_requests,
        },
    )


# ==========================
# Admin: Improvement 요청 전체 조회/상세
# ==========================
@app.get("/admin/improvements", response_class=HTMLResponse)
async def admin_improvements_list(
    request: Request,
    q: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    admin_user: models.User = Depends(require_admin_user),
):
    """최고관리자 전용: improvement_requests 전체 목록."""
    if page < 1:
        page = 1

    limit = 50
    offset = (page - 1) * limit

    items = await crud.list_all_improvement_requests(
        db,
        limit=limit,
        offset=offset,
        q=q,
    )

    return templates.TemplateResponse(
        "admin/improvement_list.html",
        {
            "request": request,
            "user": admin_user,
            "items": items,
            "q": q or "",
            "page": page,
            "limit": limit,
        },
    )


@app.get("/admin/improvements/{request_id}", response_class=HTMLResponse)
async def admin_improvements_detail(
    request: Request,
    request_id: int,
    db: AsyncSession = Depends(get_db),
    admin_user: models.User = Depends(require_admin_user),
):
    """최고관리자 전용: improvement_requests 상세."""
    item = await crud.get_improvement_request_by_id(db, request_id=request_id)
    if not item:
        # 템플릿에서 예쁘게 표시하고 싶으면 별도 404 템플릿을 만들어도 됨
        return templates.TemplateResponse(
            "admin/improvement_detail.html",
            {
                "request": request,
                "user": admin_user,
                "item": None,
                "error": "요청 내역을 찾을 수 없습니다.",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return templates.TemplateResponse(
        "admin/improvement_detail.html",
        {
            "request": request,
            "user": admin_user,
            "item": item,
            "error": None,
        },
    )