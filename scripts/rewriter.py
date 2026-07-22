"""
Gemini API를 이용한 뉴스 재구성 (설명형).

기사 본문을 바탕으로, 일반 독자가 읽고 이해할 수 있게 팩트를 풀어서 설명한다.
원문 문장을 그대로 베끼지 않고 새 문장으로 재구성 (저작권 리스크 최소화).
모델: gemini-3.1-flash-lite (무료 티어)
"""
import json
import re
import google.generativeai as genai

from config import GEMINI_API_KEY

MODEL_NAME = "gemini-3.1-flash-lite"

SYSTEM_PROMPT = """너는 한국어 뉴스 큐레이션 카드뉴스 작가다.
아래 기사(제목/요약/본문)를 바탕으로, 뉴스를 잘 모르는 일반 독자도 읽고 이해할 수 있게
팩트를 쉽게 풀어서 설명하라. 원문 문장을 그대로 베끼지 말고 새 문장으로 재구성한다.

반드시 아래 JSON 형식으로만 답하라. 다른 설명이나 마크다운 코드블록 없이 순수 JSON만 출력.

{
  "headline": "20자 이내 임팩트 있는 헤드라인",
  "subtitle": "헤드라인 핵심을 요약한 6자 이내 강조 키워드 (예: 개편안 공개, 8% 성장)",
  "key_stat": {"value": "기사에서 가장 인상적인 수치 한 개 (단위 포함, 예: 9,314억 원, 8%, 32명). 뚜렷한 수치가 없으면 빈 문자열 \"\"", "label": "그 수치가 무엇인지 15자 이내 설명"},
  "lead": "무슨 일이 있었는지 3문장으로 설명 (총 110자 내외, 구체적 사실 중심)",
  "facts": ["핵심 팩트1 (수치/주체 등, 18자 이내)", "핵심 팩트2 (18자 이내)", "핵심 팩트3 (18자 이내)"],
  "background": "이 일이 나온 배경/맥락을 3문장으로 (총 110자 내외)",
  "simple": "핵심을 비유나 쉬운 말로 풀어 2~3문장으로 (총 100자 내외)",
  "why": "{category_context} 독자가 눈여겨볼 관전 포인트를 한 문장 힌트로. '~하세요' 같은 직접 지시는 금지. 앞으로 무엇이 달라질지·지켜볼 지점을 은근하게 (예: '~ 흐름을 눈여겨볼 만합니다', '~ 여부가 관건입니다'). 45자 이내",
  "is_factual_risk": false,
  "is_promotional": false
}

주의사항:
- 모든 문장은 원문 구조를 따라가지 말고 팩트만 뽑아 새로 작성
- 숫자, 날짜, 인명, 기관명은 원문과 정확히 일치 (오보 방지)
- 본문에 없는 내용을 추측해서 지어내지 말 것. 정보가 부족하면 있는 사실만 쓴다
- background/simple은 독자가 "그래서 이게 무슨 의미인지" 이해하도록 쉽게
- 확실하지 않은 수치/사실이 있으면 is_factual_risk를 true로 설정
- is_promotional: 이 기사가 사회적으로 의미 있는 '뉴스'가 아니라 특정 기업·제품·서비스의
  홍보/광고성(신제품 출시·이벤트·할인·프로모션·보도자료 위주)이면 true. 산업 동향·정책·
  시장 변화 등 실제 뉴스면 false
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    return json.loads(text)


def rewrite_news(title: str, description: str, body: str, category_context: str) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        MODEL_NAME,
        system_instruction=SYSTEM_PROMPT.replace("{category_context}", category_context),
    )

    parts = [f"제목: {title}", f"요약: {description}"]
    if body:
        parts.append(f"본문:\n{body}")
    user_prompt = "\n".join(parts)

    response = model.generate_content(
        user_prompt,
        generation_config={"temperature": 0.4, "response_mime_type": "application/json"},
    )

    try:
        parsed = _extract_json(response.text)
    except (json.JSONDecodeError, AttributeError) as e:
        raise RuntimeError(f"Gemini 응답 JSON 파싱 실패: {e}\n원본 응답: {getattr(response, 'text', None)}")

    parsed["_original_title"] = title
    return parsed


if __name__ == "__main__":
    sample = rewrite_news(
        title="외식업계, 배달앱 수수료 인하 요구 확산",
        description="자영업자 단체들이 배달앱 3사에 수수료 인하를 공동 요청했다고 19일 밝혔다.",
        body="",
        category_context="식품/외식업",
    )
    print(json.dumps(sample, ensure_ascii=False, indent=2))
