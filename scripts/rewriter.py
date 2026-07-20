"""
Gemini API를 이용한 뉴스 재구성.

원문 문장을 그대로 베끼지 않고 팩트만 추출해서 새 문장으로 재구성 (저작권 리스크 최소화).
모델: gemini-2.5-flash-lite (무료 티어)
"""
import json
import re
import google.generativeai as genai

from config import GEMINI_API_KEY

MODEL_NAME = "gemini-3.1-flash-lite"

SYSTEM_PROMPT = """너는 한국어 뉴스 큐레이션 카드뉴스 작가다.
아래 뉴스 기사의 제목과 요약을 바탕으로, 원문 문장을 절대 그대로 베끼지 말고
팩트(누가/무엇을/언제/수치)만 추출해서 완전히 새로운 문장으로 재구성하라.

반드시 아래 JSON 형식으로만 답하라. 다른 설명이나 마크다운 코드블록 없이 순수 JSON만 출력.

{
  "headline": "카드뉴스 상단에 들어갈 20자 이내 임팩트 있는 헤드라인",
  "subtitle": "헤드라인 끝을 강조할 6자 이내 핵심 키워드 (예: 개편안 공개, 8% 성장)",
  "summary_lines": ["요약 문장1 (22자 이내)", "요약 문장2 (22자 이내)", "요약 문장3 (22자 이내)"],
  "comment": "이 소식이 {category_context} 종사자에게 왜 중요한지 1줄 코멘트 (28자 이내)",
  "is_factual_risk": false
}

주의사항:
- subtitle은 headline의 핵심을 요약한 짧은 강조어 (표지 카드에서 파란색으로 강조 표시됨)
- summary_lines는 원문 문장 구조를 따라가지 말고 팩트만 뽑아 새로 작성
- 숫자, 날짜, 인명, 기관명은 원문과 정확히 일치해야 함 (오보 방지)
- 원문에 없는 내용을 추측해서 만들어내지 말 것
- 확실하지 않은 수치/사실이 있으면 is_factual_risk를 true로 설정
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    return json.loads(text)


def rewrite_news(title: str, description: str, category_context: str) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT.replace("{category_context}", category_context))

    user_prompt = f"제목: {title}\n요약: {description}"

    response = model.generate_content(
        user_prompt,
        generation_config={"temperature": 0.4, "response_mime_type": "application/json"},
    )

    try:
        parsed = _extract_json(response.text)
    except (json.JSONDecodeError, AttributeError) as e:
        raise RuntimeError(f"Gemini 응답 JSON 파싱 실패: {e}\n원본 응답: {getattr(response, 'text', None)}")

    parsed["_original_title"] = title
    parsed["_original_description"] = description
    return parsed


if __name__ == "__main__":
    sample = rewrite_news(
        title="외식업계, 배달앱 수수료 인하 요구 확산",
        description="자영업자 단체들이 배달앱 3사에 수수료 인하를 공동 요청했다고 19일 밝혔다.",
        category_context="식품/외식업",
    )
    print(json.dumps(sample, ensure_ascii=False, indent=2))
