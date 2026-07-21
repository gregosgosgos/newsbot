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


def _norm_title(t: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t).lower()

def _is_duplicate(norm: str, kept: list, thresh: float = 0.55) -> bool:
    """이미 채택된 제목들과 유사하면 True (같은 사건 다른 기사 제거)."""
    for k in kept:
        if not norm or not k:
            continue
        if difflib.SequenceMatcher(None, norm, k).ratio() >= thresh:
            return True
        short, long = sorted([norm, k], key=len)
        if len(short) >= 8 and short in long:   # 한쪽이 다른쪽에 크게 포함
            return True
    return False


def _similar(a: str, b: str, thresh: float = 0.55) -> bool:
    if not a or not b:
        return False
    if difflib.SequenceMatcher(None, a, b).ratio() >= thresh:
        return True
    short, long = sorted([a, b], key=len)
    return len(short) >= 8 and short in long


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
    clusters = []  # {"norm", "items": [...], "keywords": set}
    for it in pool:
        n = _norm_title(it["title"])
        for c in clusters:
            if _similar(n, c["norm"]):
                c["items"].append(it)
                c["keywords"].add(it["matched_keyword"])
                break
        else:
            clusters.append({"norm": n, "items": [it], "keywords": {it["matched_keyword"]}})

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


def fetch_article_text(url: str, max_chars: int = 2500) -> str:
    """기사 원문 링크에서 본문 텍스트 추출 (trafilatura). 실패 시 빈 문자열."""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        txt = trafilatura.extract(downloaded, include_comments=False,
                                  include_tables=False, favor_precision=True) or ""
        return txt.strip()[:max_chars]
    except Exception as e:
        print(f"[WARN] 본문 추출 실패 {url}: {e}")
        return ""


if __name__ == "__main__":
    from config import CATEGORIES
    for cat_id, cat in CATEGORIES.items():
        news = collect_category_news(cat["keywords"])
        print(f"\n=== {cat['name_kr']} ({cat_id}) : {len(news)}건 ===")
        for n in news[:3]:
            print(" -", n["title"])
