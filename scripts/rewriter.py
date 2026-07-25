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
  "facts": ["이 뉴스의 핵심 포인트 1 (완결된 짧은 구/문장, 22자 이내)", "핵심 포인트 2 (22자 이내)", "핵심 포인트 3 (22자 이내)"],
  "background": "이 일이 나온 배경/맥락을 3문장으로 (총 110자 내외)",
  "simple": "핵심을 비유나 쉬운 말로 풀어 4~5문장으로 (총 170자 내외). 왜 그런지·그래서 뭐가 달라지는지·독자에게 어떤 의미인지까지 친절하게 채워서",
  "why": "{category_context} 독자가 눈여겨볼 관전 포인트를 한 문장 힌트로. '~하세요' 같은 직접 지시는 금지. 앞으로 무엇이 달라질지·지켜볼 지점을 은근하게 (예: '~ 흐름을 눈여겨볼 만합니다', '~ 여부가 관건입니다'). 45자 이내",
  "is_factual_risk": false,
  "is_promotional": false
}

주의사항:
- 말투(lead·background·simple): '~습니다. ~습니다. ~습니다.'처럼 짧은 문장이 뚝뚝 끊기지 않게 하라.
  · 연결어미(~며, ~고, ~는데, ~면서, ~어/아서 등)와 쉼표로 자연스럽게 이어 읽기 편한 호흡을 만들 것.
  · 한 문단이 전부 똑같은 종결어미로 끝나지 않게 길이와 리듬을 다양하게.
  · 다만 한 문장을 지나치게 길게 늘이지는 말고(한 문장 60자 이내 권장), 딱딱한 보도체보다 친근하고 매끄러운 설명체로.
- 모든 문장은 원문 구조를 따라가지 말고 팩트만 뽑아 새로 작성
- facts(핵심 포인트) 작성 규칙:
  · 이 헤드라인이 다루는 '사건의 핵심'과 직접 관련된 포인트만 3개. 규모·이력 등 곁가지 수치 나열 금지.
  · 각 항목은 '완결된' 짧은 구나 문장. 서술어를 어색하게 자르지 말 것(예: '부담 커'(X) → '배송비 부담 가중'(O)).
  · 세 항목은 서로 다른 내용이어야 하고, lead·key_stat에 이미 나온 수치/문장을 그대로 반복하지 말 것.
  · 독자가 이 뉴스에서 기억할 만한 '요지'를 담을 것(단순 배경 데이터가 아니라).
  · 세 항목의 어미/구조를 다양하게(전부 '~구축/~강화/~확장'처럼 똑같이 끝나지 않게).
- 숫자 상식 검증(중요): 수치가 상식적으로 말이 안 되면(예: 한 기업/프로젝트 투자액이 한국 GDP(약 2,400조 원)를 넘는 등) 원문을 잘못 읽었을 가능성이 크다.
  그런 값은 key_stat에 넣지 말고(빈 문자열), 본문에도 쓰지 말며, 확신이 안 서면 is_factual_risk를 true로 설정.
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
