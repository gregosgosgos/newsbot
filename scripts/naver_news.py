"""
네이버 뉴스 검색 API 클라이언트

주의: 이 API는 '카테고리' 파라미터가 없다. query(검색어) 기반 검색만 지원.
카테고리마다 config.py 의 키워드들로 여러 번 검색해서 뉴스 풀을 직접 구성한다.
"""
import re
import difflib
import requests
from html import unescape
from datetime import datetime, timedelta, timezone

from config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, NAVER_DISPLAY_PER_QUERY

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
KST = timezone(timedelta(hours=9))


def _strip_html(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _parse_pubdate(pubdate_str: str) -> datetime:
    return datetime.strptime(pubdate_str, "%a, %d %b %Y %H:%M:%S %z")


def search_news(query: str, display: int = None, sort: str = "date") -> list:
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 설정되지 않았습니다.")

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {
        "query": query,
        "display": display or NAVER_DISPLAY_PER_QUERY,
        "start": 1,
        "sort": sort,
    }
    resp = requests.get(NAVER_NEWS_URL, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    items = resp.json().get("items", [])

    results = []
    for item in items:
        results.append({
            "title": _strip_html(item["title"]),
            "description": _strip_html(item["description"]),
            "link": item.get("originallink") or item["link"],
            "pubdate": item["pubDate"],
        })
    return results


_STOP = {"뉴스", "속보", "종합", "단독", "오늘", "관련", "기자", "사진"}

def _title_key(t: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t).lower()

def _title_tokens(t: str) -> set:
    return {w.lower() for w in re.split(r"[^0-9A-Za-z가-힣]+", t)
            if len(w) >= 2 and w.lower() not in _STOP}


def _similar(a: str, b: str) -> bool:
    """두 기사 제목이 같은 사건인지 판단 (글자 유사도 + 핵심 명사 겹침).

    표현이 달라도 핵심 명사가 겹치면 같은 사건으로 본다.
    예: '유통가 상생 바람…' 과 '유통가 상생 빛났다…' → 같은 사건.
    """
    ka, kb = _title_key(a), _title_key(b)
    if not ka or not kb:
        return False
    if difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.5:
        return True
    short, long = sorted([ka, kb], key=len)
    if len(short) >= 8 and short in long:
        return True
    ta, tb = _title_tokens(a), _title_tokens(b)
    if ta and tb:
        inter = ta & tb
        if len(inter) / len(ta | tb) >= 0.4:                       # 토큰 자카드
            return True
        if len(inter) >= 2 and any(len(w) >= 3 for w in inter):    # 핵심어 2개 이상 겹침(하나는 3자+)
            return True
    return False


def collect_category_news(keywords: list, hours_window: int = 20) -> list:
    """화제성(보도량) 기준으로 정렬한 대표 기사 리스트를 반환.

    같은 사건을 다룬 기사들을 하나의 클러스터로 묶고, 클러스터 크기(= 얼마나 많은
    매체가 보도했는가)가 큰 순서로 정렬한다. 화제인 뉴스일수록 여러 곳이 동시에
    보도하므로 이 값이 화제성의 좋은 근사치가 된다. 각 클러스터의 대표는 최신 기사.
    """
    now = datetime.now(KST)
    cutoff = now - timedelta(hours=hours_window)

    pool = []
    for kw in keywords:
        try:
            items = search_news(kw)
        except Exception as e:
            print(f"[WARN] '{kw}' 검색 실패: {e}")
            continue
        for it in items:
            try:
                pub = _parse_pubdate(it["pubdate"])
            except ValueError:
                continue
            if pub < cutoff:
                continue
            it["matched_keyword"] = kw
            pool.append(it)

    # 최신순으로 훑으며 유사 제목끼리 클러스터링 (대표 = 클러스터 내 최신 기사)
    pool.sort(key=lambda x: _parse_pubdate(x["pubdate"]), reverse=True)
    clusters = []  # {"title", "items": [...], "keywords": set}
    for it in pool:
        for c in clusters:
            if _similar(it["title"], c["title"]):
                c["items"].append(it)
                c["keywords"].add(it["matched_keyword"])
                break
        else:
            clusters.append({"title": it["title"], "items": [it],
                             "keywords": {it["matched_keyword"]}})

    # 화제성 점수: 보도량(클러스터 크기) > 키워드 다양성 > 최신성
    clusters.sort(
        key=lambda c: (len(c["items"]), len(c["keywords"]),
                       _parse_pubdate(c["items"][0]["pubdate"])),
        reverse=True,
    )
    result = []
    for c in clusters:
        rep = c["items"][0]           # 대표 = 최신 기사
        rep["buzz"] = len(c["items"])  # 보도량(참고용)
        result.append(rep)
    return result


_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I)
_OG_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I)


def fetch_article(url: str, max_chars: int = 2500):
    """기사 원문에서 (본문 텍스트, 대표이미지 URL) 을 한 번의 요청으로 추출."""
    try:
        import trafilatura
        html = trafilatura.fetch_url(url)
        if not html:
            return "", ""
        body = (trafilatura.extract(html, include_comments=False,
                                    include_tables=False, favor_precision=True) or "").strip()[:max_chars]
        m = _OG_RE.search(html) or _OG_RE2.search(html)
        img = m.group(1).strip() if m else ""
        if img.startswith("//"):
            img = "https:" + img
        return body, img
    except Exception as e:
        print(f"[WARN] 기사 fetch 실패 {url}: {e}")
        return "", ""


def fetch_article_text(url: str, max_chars: int = 2500) -> str:
    return fetch_article(url, max_chars)[0]


def download_image(url: str, dest: str) -> str:
    """대표 이미지를 내려받아 dest에 저장. 성공 시 dest, 실패 시 ''."""
    if not url:
        return ""
    try:
        import os
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and ctype.startswith("image") and len(r.content) > 3000:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(r.content)
            return dest
    except Exception as e:
        print(f"[WARN] 이미지 다운로드 실패 {url}: {e}")
    return ""


if __name__ == "__main__":
    from config import CATEGORIES
    for cat_id, cat in CATEGORIES.items():
        news = collect_category_news(cat["keywords"])
        print(f"\n=== {cat['name_kr']} ({cat_id}) : {len(news)}건 ===")
        for n in news[:3]:
            print(" -", n["title"])
