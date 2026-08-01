"""
캡션(본문) 생성 — 'docs 본문(캡션) 설계 스펙' + '브랜드 보이스 가이드' 기반.

이미지/캐러셀은 전혀 손대지 않는다. 인스타에 직접 타이핑되는 본문 텍스트만 만든다.

구조(스펙):
  [1행] 훅  = 오늘 뉴스 최고 수치를 담은 임팩트 한 문장(라벨 금지)
  [2행] 보강 = 두 번째로 강한 수치/사실
  (빈 줄)
  리드   = "오늘 챙겨야 할 핵심 뉴스 N가지, 요약해드립니다 👇"
  (빈 줄)
  뉴스별  = {이모지} {i}. {제목}  +  2~4문장 재서술(핵심→배경→사장님 관점 시사점)
  💡 한 줄 정리
  ━━━━━━━━━━
  📌 저장 / 💬 동적 질문 / 🔔 팔로우 / 🔗 원문은 프로필 링크
  해시태그 = 코어셋 + 기사 키워드(동적) + 브랜드태그 (10~15개)

톤: 존댓말, 신뢰·쉬움·실용, 과장 최상급 금지. 수치는 원문값 그대로.
"""
import json
import re

from config import GEMINI_API_KEY

MODEL_NAME = "gemini-3.1-flash-lite"

# 계정별 캡션 설정 (코어셋·브랜드태그·주제어)
_CAP = {
    "food_industry": {"topic": "식품·외식", "tag": "#오늘의식품뉴스",
                      "core": ["#외식창업", "#식당창업", "#자영업", "#소상공인", "#외식업"]},
    "ecommerce":     {"topic": "이커머스", "tag": "#오늘의이커머스뉴스",
                      "core": ["#이커머스", "#쿠팡", "#스마트스토어", "#온라인쇼핑몰", "#셀러"]},
    "startup":       {"topic": "창업·자영업", "tag": "#오늘의창업뉴스",
                      "core": ["#창업", "#자영업", "#소상공인", "#상권분석", "#사장님"]},
}
_DEFAULT_CAP = {"topic": "오늘", "tag": "#오늘의뉴스", "core": ["#뉴스", "#오늘의뉴스"]}

_SYS = """너는 '{aud}' 옆에 있는 유능한 정보통 동료다. 매일 {topic} 뉴스에서 사장님이 놓치면 안 될 것만
골라 쉽고 신뢰감 있게 정리한다. 아래 '오늘의 뉴스'로 인스타 캡션 재료를 만들어라. 순수 JSON만 출력.

톤·규칙(반드시):
- 존댓말(~습니다/~예요). 따뜻하지만 프로페셔널. 반말·과한 밈 금지.
- 신뢰: 수치·퍼센트·인명·기관은 입력값 그대로. 임의 생성·과장 금지.
  최상급/낚시어('최고','무조건','충격','대박','실화','역대급') 사용 금지.
- 쉽게: 어려운 내용을 쉬운 말로, 핵심부터.
- 실용: 각 뉴스에 '사장님 관점에서 뭐가 달라지나'를 한 스푼.
- 원문 문장 복붙 금지 — 새 문장으로 재서술.
- 이모지는 기능적으로 절제(훅·헤딩에 1개 정도).

출력 JSON 형식(다른 텍스트 없이):
{{
  "hook": "첫 줄 훅 — 오늘 뉴스 중 최고 임팩트 '수치'를 담은 한 문장. '~수치','오늘의 뉴스' 같은 라벨로 시작 금지. 이모지 1개까지 허용. 30자 내외",
  "hook_sub": "두 번째로 강한 수치/사실 한 문장(수치 포함, 40자 내외). 마땅치 않으면 빈 문자열",
  "items": [{{"emoji": "뉴스 성격에 맞는 이모지 1개", "summary": "이 뉴스 2~4문장 요약(핵심 사실 → 배경 → 사장님 관점 시사점). 재서술."}}],
  "insight": "오늘 뉴스 전체를 관통하는 한 줄 정리 1~2문장(사장님 관점)",
  "question": "오늘 주제에 맞게 사장님에게 던지는 댓글 유도 질문 한 문장",
  "hashtags": ["기사 키워드에서 뽑은 해시태그 단어 4~6개('#' 없이 단어만, 공백 없이)"]
}}
items 배열은 입력한 뉴스와 같은 순서·같은 개수로."""


def _extract_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(text)


def _gemini(cat_name, category_id, items):
    import google.generativeai as genai
    cfg = _CAP.get(cat_name) or _CAP.get(category_id) or _DEFAULT_CAP
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        MODEL_NAME,
        system_instruction=_SYS.format(aud="사장님", topic=cfg["topic"]))
    blocks = []
    for i, it in enumerate(items, 1):
        ks = it.get("key_stat") or {}
        blocks.append(
            f"[뉴스 {i}]\n제목: {it.get('headline','')}\n"
            f"핵심수치: {ks.get('value','')} ({ks.get('label','')})\n"
            f"무슨 일: {it.get('lead','')}\n배경: {it.get('background','')}\n"
            f"시사점 힌트: {it.get('why','')}")
    resp = model.generate_content(
        "오늘의 뉴스:\n\n" + "\n\n".join(blocks),
        generation_config={"temperature": 0.5, "response_mime_type": "application/json"})
    return _extract_json(resp.text)


def _hashtags(cfg, dynamic):
    out, seen = [], set()
    for t in cfg["core"] + ["#" + re.sub(r"[\s#]", "", str(w)) for w in (dynamic or [])] + [cfg["tag"]]:
        if t and t != "#" and t.lower() not in seen:
            seen.add(t.lower()); out.append(t)
    return out[:15]


def _assemble(cat_name, category_id, items, cap):
    cfg = _CAP.get(cat_name) or _CAP.get(category_id) or _DEFAULT_CAP
    cit = cap.get("items", [])
    L = []
    if cap.get("hook"):
        L.append(cap["hook"].strip())
    if cap.get("hook_sub"):
        L.append(cap["hook_sub"].strip())
    L.append("")
    L.append(f"오늘 챙겨야 할 핵심 뉴스 {len(items)}가지, 요약해드립니다 👇")
    L.append("")
    for i, it in enumerate(items, 1):
        c = cit[i-1] if i-1 < len(cit) else {}
        emoji = (c.get("emoji") or "📌").strip()
        L.append(f"{emoji} {i}. {it.get('headline','')}")
        summ = (c.get("summary") or it.get("lead", "")).strip()
        if summ:
            L.append(summ)
        L.append("")
    if cap.get("insight"):
        L.append(f"💡 한 줄 정리: {cap['insight'].strip()}")
    L.append("━━━━━━━━━━")
    L.append("📌 나중에 다시 볼 분은 저장해두세요!")
    q = (cap.get("question") or "오늘 뉴스 중 사업에 제일 와닿는 건 무엇인가요? 댓글로 알려주세요.").strip()
    L.append(f"💬 {q}")
    L.append(f"🔔 매일 아침 {cfg['topic']} 뉴스, 팔로우하고 받아보세요.")
    L.append("🔗 원문 기사는 프로필 링크에")
    L.append("")
    L.append(" ".join(_hashtags(cfg, cap.get("hashtags"))))
    return "\n".join(L)


def _fallback(cat_name, category_id, items):
    """Gemini 실패 시: 이미 생성된 뉴스 필드로 결정형 조립."""
    cap = {"items": []}
    # 훅: 수치가 있는 첫 뉴스 사용
    stat_it = next((it for it in items if (it.get("key_stat") or {}).get("value")), None)
    if stat_it:
        ks = stat_it["key_stat"]
        cap["hook"] = f"{stat_it.get('headline','')} 📊"
        cap["hook_sub"] = f"{ks.get('value','')} — {ks.get('label','')}"
    else:
        cap["hook"] = items[0].get("headline", "오늘의 핵심 뉴스") if items else "오늘의 핵심 뉴스"
        cap["hook_sub"] = ""
    for it in items:
        cap["items"].append({"emoji": "📰", "summary": it.get("simple") or it.get("lead", "")})
    cap["insight"] = (items[0].get("why", "") if items else "")
    cap["question"] = "오늘 뉴스 중 사업에 제일 와닿는 건 무엇인가요? 댓글로 알려주세요."
    cap["hashtags"] = []
    return _assemble(cat_name, category_id, items, cap)


def generate_caption(category_id, cat_name, items):
    """스펙 기반 캡션 문자열 생성. Gemini 실패해도 폴백으로 항상 캡션을 반환."""
    if not items:
        return ""
    try:
        cap = _gemini(cat_name, category_id, items)
        if not isinstance(cap, dict) or not cap.get("items"):
            raise ValueError("빈 캡션 응답")
        return _assemble(cat_name, category_id, items, cap)
    except Exception as e:
        print(f"[WARN] 캡션 Gemini 실패, 폴백 사용: {e}")
        return _fallback(cat_name, category_id, items)
