"""
네이버 뉴스 검색 API 클라이언트

주의: 이 API는 '카테고리' 파라미터가 없다. query(검색어) 기반 검색만 지원.
카테고리마다 config.py 의 키워드들로 여러 번 검색해서 뉴스 풀을 직접 구성한다.
"""
import re
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
            "pubdate": item["pubdate"],
        })
    return results


def collect_category_news(keywords: list, hours_window: int = 20) -> list:
    now = datetime.now(KST)
    cutoff = now - timedelta(hours=hours_window)

    seen_titles = set()
    merged = []
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
            key = it["title"]
            if key in seen_titles:
                continue
            seen_titles.add(key)
            it["matched_keyword"] = kw
            merged.append(it)

    merged.sort(key=lambda x: _parse_pubdate(x["pubdate"]), reverse=True)
    return merged


if __name__ == "__main__":
    from config import CATEGORIES
    for cat_id, cat in CATEGORIES.items():
        news = collect_category_news(cat["keywords"])
        print(f"\n=== {cat['name_kr']} ({cat_id}) : {len(news)}건 ===")
        for n in news[:3]:
            print(" -", n["title"])
