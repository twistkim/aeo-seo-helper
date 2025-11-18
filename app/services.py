# app/services.py
from typing import Optional, Any, List, Dict
import os
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import google.generativeai as genai

# ==========================
# 환경변수 로드
# ==========================
load_dotenv()

# ---- Gemini 설정 ----
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY 가 .env에 설정되어 있지 않습니다.")

genai.configure(api_key=GEMINI_API_KEY)

# 너 계정에서 list_models()로 확인한 유효 모델
GEMINI_MODEL_NAME = "models/gemini-pro-latest"

# ---- Naver 검색 API 설정 ----
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
    # 모니터링 기능을 쓸 때 에러를 내도록 하고, 여기서 바로 죽이진 않는다.
    print(
        "[WARN] NAVER_CLIENT_ID 혹은 NAVER_CLIENT_SECRET 이 .env에 없습니다. "
        "순위 모니터링 기능 사용 시 오류가 날 수 있습니다."
    )


# ==========================
# 공통 유틸
# ==========================
def _split_csv(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return [x.strip() for x in text.split(",") if x.strip()]


# ==========================
# 1) 블로그 원고 생성 (Gemini)
# ==========================
def generate_blog_post(
    core_keyword: str,
    product_name: Optional[str] = None,
    target_audience: Optional[str] = None,
    tone: Optional[str] = None,
    additional_instructions: Optional[str] = None,
    **extra_fields: Any,
) -> str:
    """
    네이버 상위 노출 기준(문단 수, 단어 수, FAQ, VIDEO, 금지어 등)을
    반영해서 블로그 원고를 생성한다.
    """

    # ---------- 폼 값 정리 ----------
    brand: Optional[str] = extra_fields.get("brand")
    intent: Optional[str] = extra_fields.get("intent")
    persona: Optional[str] = extra_fields.get("persona")
    must_keywords_raw: Optional[str] = extra_fields.get("must_keywords")
    must_headings_raw: Optional[str] = extra_fields.get("must_headings")
    cta_text: Optional[str] = extra_fields.get("cta_text") or "구독"
    banned_terms_raw: Optional[str] = extra_fields.get("banned_terms")
    product_detail_text: Optional[str] = extra_fields.get("product_detail_text")

    must_keywords = _split_csv(must_keywords_raw)
    must_headings = _split_csv(must_headings_raw)

    # 기본 금지어 + 사용자 금지어
    default_banned = [
        "효과",
        "효능",
        "개선",
        "주름개선",
        "탄력개선",
        "리프팅",
        "안티에이징",
        "치료",
        "치유",
        "회복",
        "통증 완화",
        "스트레스 완화",
        "임상",
        "임상으로 입증",
    ]
    user_banned = _split_csv(banned_terms_raw)
    banned_terms_list = sorted(set(default_banned + user_banned))
    banned_terms_str = ", ".join(banned_terms_list) if banned_terms_list else "없음"

    # 기본값 채우기
    product_name = product_name or "(제품명 미입력)"
    brand = brand or "(브랜드 미입력)"
    target_audience = target_audience or "(타겟 미입력)"
    intent = intent or "정보형 리뷰"
    persona = persona or "개인블로거"
    tone = tone or "친근+전문"
    additional_instructions = additional_instructions or "(추가 요청 없음)"
    product_detail_text = product_detail_text or "(별도 제품 브리프 없음)"

    must_keywords_block = (
        "\n".join(f"- {kw}" for kw in must_keywords) if must_keywords else "- (지정 없음)"
    )
    must_headings_block = (
        "\n".join(f"- {h}" for h in must_headings) if must_headings else "- (지정 없음)"
    )

    # ---------- 프롬프트 구성 ----------
    system_prompt = f"""
너는 네이버 블로그 상위노출을 목표로 글의 형식과 구조를 엄격히 맞춰 생성하는 카피에디터다.
상위 노출된 블로그 vs 비상위 노출 블로그의 차이를 잘 알고 있으며,
상위 노출 글의 패턴(문단 구성, 톤, CTA, FAQ, VIDEO, 키워드 분산)을 최대한 재현하고,
비상위 글에서 자주 보이는 문제(키워드 스팸, 과장 카피, 문단 길이 불균형 등)는 피해야 한다.

[상위 노출 구조 기준]
다음 기준을 가능한 한 엄격히 맞추려고 노력하라. 완벽히 일치하지 않더라도,
이 범위를 목표로 글의 길이와 구조를 조정한다.

[기준]
    - 문단수: 180~230개 <p> 문단을 선호한다.
    - 단어수: 650~700 단어를 목표로 하되, ±10~15% 범위 안에서 변동을 허용한다.
    - 서론 100자 내:
        · 핵심 키워드(예: "{core_keyword}")가 최소 1회 등장해야 한다.
        · 제품명(예: "{product_name}")이 최소 1회 자연스럽게 등장해야 한다.
    - FAQ: 본문 중간~하단에 질문/답변 형식의 FAQ 문단을 최소 2개 포함한다.
        · 예: "<strong>Q.</strong> ~?" / "<strong>A.</strong> ~" 형식
    - VIDEO 슬롯: 영상으로 보완 설명을 볼 수 있는 느낌의 '영상 추천' 문단을 2~3개 포함한다.
        · 예: "<strong>영상으로 보면 더 이해가 쉬운 포인트</strong>" 로 시작하는 문단 등
    - 제품명 등장 총량:
        · 제품명("{product_name}")은 전체 본문에서 3~10회 정도 자연스럽게 분산 등장해야 한다.
        · 같은 문장을 반복하거나, 리스트처럼 나열하는 스팸 형태는 금지한다.
        · 허위 정보(존재하지 않는 성분, 사실이 아닌 혜택 등)는 절대 만들어내지 않는다.
    - 신제품 전제:
        · "이미 수많은 후기", "압도적인 판매량", "국민템"과 같이 사회적 증거를 과장하는 표현은 사용하지 않는다.
        · 특히 통계/수치/랭킹을 임의로 만들지 않는다.
    - 금지어:
        · 다음 금지어 및 동의어를 직접적으로 사용하지 않는다: {banned_terms_str}
        · 대신 "제 경험상 ~하게 느꼈다", "저한테는 ~가 편했다", "개인차가 있을 수 있다" 같은 체감/인상 중심 표현으로 대체한다.

[형식 및 문체 지침]
1) 전체는 HTML로 출력하며, 각 문장은 반드시 1개의 <p> ... </p>로 감싼다.
   - 한 문단 = 한 문장 스타일을 지키고, 문장마다 줄바꿈되는 네이버 블로그 트렌드를 따른다.
2) HPSB 구조를 적용한다: Hook → Problem → Solution → Benefit → CTA
   - 각 섹션 시작부에 <strong>섹션명</strong> 을 넣되,
     과도한 H 태그나 마크다운(#, *, - 등)은 사용하지 않는다.
3) 마크다운 문법(#, *, -, ``` 등)을 절대 사용하지 않는다.
   - 오직 HTML 태그(<p>, <strong> 등)만 사용하고, 나머지는 순수 텍스트로 쓴다.
4) 광고성 과장 문구(“인생템”, “무조건 사야 함”, “완벽하게 해결” 등)는 피하고,
   솔직한 체험/후기 톤을 유지한다.
5) 피부/건강 관련 표현은 효능을 단정하지 말고,
   '관리/케어/루틴' 중심으로 부드럽게 서술한다.
"""

    user_prompt = f"""
[컨텍스트]
- 핵심 키워드: {core_keyword}
- 제품명: {product_name}
- 브랜드: {brand}
- 글 의도: {intent}
- 대상 독자: {target_audience}
- 페르소나/톤: {persona} / {tone}
- CTA 유형: {cta_text}

[콘텐츠 구성 요구]
1) HPSB 구조를 따른다.
   - Hook: 독자의 상황/고민에 공감하는 한두 문장
   - Problem: 키워드와 관련된 구체적인 고민/상황 설명
   - Solution: 제품/서비스를 중심으로 한 해결 방향, 사용법, 특징
   - Benefit: 실제 사용감/체감/상황 변화 위주(개인 경험 톤)
   - CTA: 독자가 "{cta_text}" 행동을 할 수 있도록 자연스럽게 유도
2) 서론 100자 안에 핵심 키워드와 제품명이 1회 이상 등장하도록 유도한다.
3) 본문 전체에서:
   - 핵심 키워드와 연관 키워드가 자연스럽게 여러 번 등장하되, 스팸처럼 보이지 않도록 한다.
4) 필수 포함 키워드(가능한 한 모두 자연스럽게 포함):
{must_keywords_block}

5) 필수 포함 소제목(섹션 구조에 녹여서 사용, <strong>소제목</strong> 형태 허용):
{must_headings_block}

6) FAQ 구성:
   - 중간~하단부에 최소 2개의 Q&A 문단을 만든다.
   - 형식 예시:
     · <strong>Q.</strong> oo가 궁금했어요
     · <strong>A.</strong> 제가 사용해보니 ~ 이런 느낌이었어요 (개인차 고지 포함)
7) VIDEO 슬롯 구성:
   - 영상으로 내용을 보완한다는 느낌의 문단을 2~3개 포함한다.
   - 예: "<strong>영상으로 보면 더 이해가 쉬운 포인트</strong>"로 시작해서,
     어느 부분을 영상으로 보면 좋은지 설명하는 문단.

[제품 브리프/상세 정보]
아래 제품 관련 정보를 참고해 구체적인 디테일과 맥락을 추가하되,
허위·추정 정보는 만들지 말고, 모르는 부분은 안전하게 넘어가라.

{product_detail_text}

[추가 요청 사항]
{additional_instructions}

[출력 형식]
- 전체 결과를 HTML <p> ... </p> 문장들로만 출력한다.
- 한 문장은 반드시 1개의 <p> ... </p> 태그로 감싼다.
- <ARTICLE>, <FAQ>, <VIDEOS> 같은 별도의 메타 태그는 쓰지 말고,
  FAQ/VIDEO는 위에서 설명한 문장 구조(굵은 제목 + 일반 문장)로만 표현한다.
- 마크다운 문법(#, *, -, ``` 등)을 절대 사용하지 않는다.
- CTA 문단에서는 자연스럽게 "{cta_text}" 행동을 유도하는 문장을 포함한다.
"""

    full_prompt = system_prompt + "\n\n" + user_prompt

    # ---------- Gemini 호출 ----------
    try:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        response = model.generate_content(full_prompt)
        text = (response.text or "").strip()

        # 안전장치: <p> 태그가 하나도 없으면 줄단위로 <p>로 감싸주기
        if "<p" not in text:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = "\n".join(f"<p>{line}</p>" for line in lines)

        return text
    except Exception as e:
        raise RuntimeError(f"Gemini 호출 실패: {e}")


# ==========================
# 2) 네이버 블로그 본문 크롤링 (iframe 대응)
# ==========================
def scrape_url_content(url: str) -> str:
    """
    네이버 블로그 URL에서 본문 텍스트를 크롤링해서 반환한다.
    네이버 블로그는 보통 iframe(mainFrame) 안에 본문이 있기 때문에
    2단계 요청을 수행한다.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/129 Safari/537.36"
        )
    }

    # 1) 첫 페이지 요청
    r1 = requests.get(url, headers=headers, timeout=10)
    r1.raise_for_status()

    soup1 = BeautifulSoup(r1.text, "html.parser")

    iframe = soup1.select_one("iframe#mainFrame")
    if not iframe:
        # iframe이 없으면 그냥 이 페이지에서 바로 본문을 찾는다.
        soup2 = soup1
    else:
        iframe_src = iframe.get("src")
        if not iframe_src:
            raise RuntimeError("네이버 블로그 iframe src를 찾을 수 없습니다.")

        if iframe_src.startswith("/"):
            iframe_url = "https://blog.naver.com" + iframe_src
        else:
            iframe_url = iframe_src

        r2 = requests.get(iframe_url, headers=headers, timeout=10)
        r2.raise_for_status()
        soup2 = BeautifulSoup(r2.text, "html.parser")

    selectors = [
        "div.se-main-container",  # 스마트에디터 ONE
        "#postViewArea",          # 구형 에디터
        "div#postViewArea",
        "div#contentArea",
    ]

    text = ""
    for sel in selectors:
        node = soup2.select_one(sel)
        if node:
            text = node.get_text(separator="\n", strip=True)
            break

    if not text.strip():
        body = soup2.body
        if not body:
            raise RuntimeError("본문을 찾을 수 없습니다. (body 요소 없음)")
        text = body.get_text(separator="\n", strip=True)

    if not text.strip():
        raise RuntimeError("본문 텍스트가 비어 있습니다. 다른 URL을 시도해보세요.")

    max_len = 8000
    if len(text) > max_len:
        text = text[:max_len]

    return text


# ==========================
# 3) 블로그 분석 + 개선안 (Gemini, Markdown)
# ==========================
def analyze_blog_post(
    blog_text: str,
    core_keyword: str,
    blog_url: str,
) -> str:
    """
    크롤링한 네이버 블로그 본문과 핵심 키워드를 기반으로
    SEO/상위노출 기준에 따른 분석 + 개선안을 마크다운 형식으로 생성한다.
    """

    analysis_prompt = f"""
너는 네이버 블로그 상위노출을 목표로 글을 점검하는 SEO 컨설턴트다.
아래 [기준]은 이미 상위노출/비상위노출 블로그들을 분석해서 정리한 기준이다.
이 기준을 최대한 반영해서 본문을 평가하고, 구체적인 수정 제안을 제시하라.

[분석 대상]
- URL: {blog_url}
- 핵심 키워드: {core_keyword}

[기준]
- 문단수: 180~230개 <p> 문단 선호
- 단어수: 650~700 단어 목표(±10~15% 허용)
- 서론 100자 내:
  · 핵심 키워드 ≥ 1회
  · 제품명 또는 주요 브랜딩 키워드 ≥ 1회
- FAQ: 최소 2개 (Q/A 형식)
- VIDEO 슬롯: 2~3개 (영상으로 설명 보완하는 느낌의 문단)
- 제품명 등장 총량: 3~10회 (자연스럽게 분산, 스팸 금지)
- 신제품 전제: "압도적 판매량", "국민템" 등 사회적 증거 과장 금지
- 금지어: 직·간접 효능 표현(효과, 효능, 개선, 리프팅, 안티에이징, 치료, 치유, 회복, 통증 완화, 스트레스 완화, 임상 입증 등) 사용 금지.
  · 대신 '체감', '느낌', '개인차' 표현으로 완화.

[본문 원문]
아래는 네이버 블로그에서 크롤링한 현재 본문이다.

[ORIGINAL_BLOG_CONTENT_START]
{blog_text}
[ORIGINAL_BLOG_CONTENT_END]

[요구 사항]
아래 항목을 **마크다운 형식으로** 작성하라. (제목, 번호 목록, 표 등을 적극 활용하라.)

1. ## 전체 구조 진단
   - 문단수/단어수 추정 (대략적인 범위로 설명)
   - 도입부(서론)의 역할과 키워드/제품명 노출 여부
   - HPSB(Hook-Problem-Solution-Benefit-CTA) 관점에서 어느 단계가 약한지 요약

2. ## 키워드 & 문장 수준 최적화
   - 핵심 키워드 및 연관 키워드 사용 패턴 평가
   - 키워드 스팸 의심 구간이 있다면 지적
   - 자연스럽게 키워드를 추가/치환할 수 있는 구체적인 문장 예시 제안

3. ## 구조 개선안 (섹션/문단 단위)
   - 추천하는 섹션 구성 예시 (마크다운 목록으로)
   - 현재 글에서 “이 문단은 위 섹션으로 이동하면 좋다” 같은 재배치 제안
   - FAQ/VIDEO 슬롯이 없다면 어디에 어떤 형태로 넣으면 좋은지 예시 작성

4. ## 규제/리스크 체크리스트
   - 효능·효과를 단정하는 표현이 있는지 여부
   - 사회적 증거 과장이 의심되는 구간
   - 표현을 어떻게 바꾸면 안전해지는지, 전/후 문장 예시로 제시

5. ## 리라이트 샘플 (부분 발췌)
   - 본문 중 중요한 2~3개 구간을 선택해,
     상위노출 기준을 반영해 “리라이트된 버전”을 마크다운 문단으로 제시
   - 원문과 비교했을 때 어떤 점이 좋아졌는지 간단 코멘트

[출력 형식 주의]
- 전체 답변은 마크다운 형식으로만 작성한다.
- HTML 태그(<p>, <strong> 등)는 사용하지 않는다.
- 한국어로 작성한다.
- 제목/소제목/리스트/강조 등 마크다운 문법을 적극 활용해,
  사람이 바로 읽고 Notion이나 문서에 붙여넣기 좋게 정리한다.
"""

    try:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        response = model.generate_content(analysis_prompt)
        text = response.text or ""
        return text.strip()
    except Exception as e:
        raise RuntimeError(f"블로그 분석 Gemini 호출 실패: {e}")


# ==========================
# 4) 네이버 검색 순위 모니터링 (웹/블로그)
# ==========================
def _extract_logno_from_url(url: str) -> Optional[str]:
    """
    네이버 블로그 URL에서 logNo(글 번호)를 추출한다.
    예)
      - https://blog.naver.com/xxx/224060246982
      - https://blog.naver.com/PostView.naver?blogId=xxx&logNo=224060246982
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "logNo" in qs and qs["logNo"]:
        return qs["logNo"][0]

    # path 마지막 토큰이 숫자 형태라면 logNo로 간주
    path_parts = [p for p in parsed.path.split("/") if p]
    if path_parts:
        last = path_parts[-1]
        if last.isdigit():
            return last

    return None


def _call_naver_search_api(
    search_type: str, query: str, display: int = 10, start: int = 1
) -> Dict[str, Any]:
    """
    네이버 검색 API 호출
    - search_type: "web" 또는 "blog"
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 없습니다.")

    if search_type == "web":
        url = "https://openapi.naver.com/v1/search/webkr.json"
    elif search_type == "blog":
        url = "https://openapi.naver.com/v1/search/blog.json"
    else:
        raise ValueError("search_type 은 'web' 또는 'blog' 이어야 합니다.")

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {
        "query": query,
        "display": display,
        "start": start,
        "sort": "sim",  # 정확도순
    }

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _find_rank_in_items(items: List[Dict[str, Any]], target_logno: str) -> Optional[int]:
    """
    검색 결과 items 리스트에서 target_logno 가 포함된 링크를 찾아
    (1부터 시작하는) 순위를 반환. 없으면 None.
    """
    for idx, item in enumerate(items):
        link = item.get("link", "")
        if target_logno and target_logno in link:
            return idx + 1
    return None


def check_naver_rank(
    keyword: str,
    blog_url: str,
    max_rank_to_check: int = 10,
) -> Dict[str, Optional[int]]:
    """
    네이버 검색 API(웹 + 블로그)를 이용해
    - 주어진 키워드로 검색했을 때
    - 특정 블로그 글(logNo)이 몇 위에 있는지(상위 max_rank_to_check위까지) 확인한다.

    반환:
        {
          "keyword": str,
          "blog_url": str,
          "log_no": str or None,
          "web_rank": int or None,
          "blog_rank": int or None,
        }
    """
    target_logno = _extract_logno_from_url(blog_url)
    if not target_logno:
        raise RuntimeError("블로그 URL에서 글 번호(logNo)를 추출할 수 없습니다.")

    # 웹검색 / 블로그 검색 각각 상위 N위까지 확인
    web_rank: Optional[int] = None
    blog_rank: Optional[int] = None

    # 블로그 검색
    try:
        blog_json = _call_naver_search_api(
            search_type="blog",
            query=keyword,
            display=max_rank_to_check,
            start=1,
        )
        blog_items = blog_json.get("items", [])
        blog_rank = _find_rank_in_items(blog_items, target_logno)
    except Exception as e:
        print(f"[WARN] 네이버 블로그 검색 호출 실패: {e}")

    # 웹 검색
    try:
        web_json = _call_naver_search_api(
            search_type="web",
            query=keyword,
            display=max_rank_to_check,
            start=1,
        )
        web_items = web_json.get("items", [])
        web_rank = _find_rank_in_items(web_items, target_logno)
    except Exception as e:
        print(f"[WARN] 네이버 웹 검색 호출 실패: {e}")

    return {
        "keyword": keyword,
        "blog_url": blog_url,
        "log_no": target_logno,
        "web_rank": web_rank,    # None 이면 상위 max_rank_to_check 위 밖
        "blog_rank": blog_rank,  # None 이면 상위 max_rank_to_check 위 밖
    }