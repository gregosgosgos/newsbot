"""
게시 기록(cross-day 중복 방지) — 최근 며칠간 각 카테고리에 올린 뉴스의 핵심어를 저장.

GitHub Actions 러너는 매 실행마다 초기화되므로, 기록을 저장소(state/posted.json)에
커밋해 다음 날 실행이 읽을 수 있게 한다(파이프라인의 git commit 단계에서 함께 커밋).

'어제와 거의 판박이'인 후보만 걸러내고(near-duplicate), 진전이 있는 후속 기사는
통과되도록 topic_overlaps를 엄격한 임계값으로 호출해 사용한다.
"""
import os
import json
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
HISTORY_PATH = os.path.join("state", "posted.json")
KEEP_DAYS = 2          # 오늘 기준 최근 며칠치 기록을 중복 비교에 사용/보관


def _today():
    return datetime.now(KST).date()


def _load() -> dict:
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def recent_token_sets(category_id: str, days: int = KEEP_DAYS) -> list:
    """최근 `days`일간 해당 카테고리에 올린 뉴스들의 토큰 집합 리스트."""
    data = _load(); today = _today(); out = []
    for e in data.get(category_id, []):
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if 0 <= (today - d).days <= days:
            out.append(set(e.get("tokens", [])))
    return out


def append_today(category_id: str, entries: list):
    """오늘 올린 뉴스들을 기록에 추가하고 오래된 항목은 정리해 저장.

    entries: [{"headline": str, "tokens": set|list}, ...]
    """
    data = _load(); today_str = datetime.now(KST).strftime("%Y-%m-%d")
    lst = data.get(category_id, [])
    for it in entries:
        lst.append({
            "date": today_str,
            "headline": it.get("headline", ""),
            "tokens": sorted(it.get("tokens", [])),
        })
    cutoff = _today() - timedelta(days=KEEP_DAYS + 1)   # 여유 하루 더 보관
    kept = []
    for e in lst:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if d >= cutoff:
            kept.append(e)
    data[category_id] = kept
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
