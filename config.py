"""
전체 설정 파일
72시간 실험 프로젝트: 카테고리별 뉴스 자동 수집 -> 리라이팅 -> 카드뉴스 -> 인스타 게시

환경변수는 Railway 배포 시 Variables 탭에서 설정.
로컬 테스트 시에는 .env 파일 사용 (python-dotenv).
"""
import os

# 로컬 테스트 시 .env 로드 (GitHub Actions에는 .env가 없으므로 자동으로 무시됨).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── API 키 (Railway Variables 또는 .env 에 설정) ──────────────────────
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── 카테고리별 설정 ──────────────────────────────────────────────────
# 네이버 뉴스 검색 API는 카테고리 파라미터가 없음 (query 검색만 지원).
# 따라서 카테고리마다 검색 키워드 세트를 직접 정의하고,
# 여러 키워드로 검색한 결과를 모아서 "이 카테고리의 뉴스 풀"로 사용.
CATEGORIES = {
    "food_industry": {
        "name_kr": "식품/외식업",
        "keywords": ["외식업계", "식자재 가격", "프랜차이즈 창업", "배달앱 수수료", "식품 물가"],
    },
    "ecommerce": {
        "name_kr": "이커머스",
        "keywords": ["이커머스 트렌드", "네이버 스마트스토어", "쿠팡 정책", "온라인 쇼핑몰"],
    },
    "startup": {
        "name_kr": "창업/자영업",
        "keywords": ["소상공인 지원", "자영업 폐업", "1인 창업", "사업자 대출"],
    },
    "realestate": {
        "name_kr": "부동산",
        "keywords": ["부동산 시장", "전세 시세", "아파트 매매", "부동산 정책"],
    },
    "finance": {
        "name_kr": "재테크/금융",
        "keywords": ["재테크", "금리 전망", "주식 시장", "예적금 금리"],
    },
    "it_tech": {
        "name_kr": "IT/테크",
        "keywords": ["AI 서비스", "스타트업 투자", "빅테크 실적", "테크 트렌드"],
    },
    "beauty": {
        "name_kr": "뷰티",
        "keywords": ["화장품 시장", "K뷰티 수출", "뷰티 트렌드", "화장품 브랜드"],
    },
    "travel": {
        "name_kr": "여행",
        "keywords": ["해외여행", "항공권 가격", "국내 여행지", "여행 트렌드"],
    },
    "parenting": {
        "name_kr": "육아",
        "keywords": ["육아 정책", "어린이집", "육아휴직", "출산 지원금"],
    },
    "auto": {
        "name_kr": "자동차",
        "keywords": ["신차 출시", "전기차 보조금", "자동차 시장", "중고차 시세"],
    },
    "sports": {
        "name_kr": "스포츠",
        "keywords": ["프로야구", "축구 국가대표", "스포츠 이적", "스포츠 스타"],
    },
    "entertainment": {
        "name_kr": "연예",
        "keywords": ["연예계 소식", "드라마 화제", "아이돌 컴백", "예능 시청률"],
    },
    "game": {
        "name_kr": "게임",
        "keywords": ["신작 게임", "게임 업데이트", "e스포츠", "게임 순위"],
    },
    "health": {
        "name_kr": "헬스/피트니스",
        "keywords": ["건강 정보", "다이어트 트렌드", "헬스장 창업", "운동 효과"],
    },
    "pet": {
        "name_kr": "반려동물",
        "keywords": ["반려동물 시장", "펫보험", "유기동물", "반려동물 트렌드"],
    },
    "fashion": {
        "name_kr": "패션",
        "keywords": ["패션 트렌드", "패션 브랜드", "패션위크", "온라인 패션몰"],
    },
    "education": {
        "name_kr": "교육/입시",
        "keywords": ["대입 정책", "사교육비", "수능", "교육 정책"],
    },
    "job": {
        "name_kr": "취업/커리어",
        "keywords": ["채용 시장", "취업 트렌드", "이직", "청년 고용"],
    },
    "interior": {
        "name_kr": "인테리어",
        "keywords": ["인테리어 트렌드", "리모델링", "가구 시장", "홈스타일링"],
    },
    "cooking": {
        "name_kr": "요리/레시피",
        "keywords": ["레시피 트렌드", "밀키트", "홈쿠킹", "외식 메뉴 트렌드"],
    },
    "politics": {
        "name_kr": "정치",
        "keywords": ["국회", "정부 정책", "국정감사", "정치 이슈"],
    },
    "economy": {
        "name_kr": "경제일반",
        "keywords": ["경제 지표", "물가 상승", "수출입 동향", "경제 전망"],
    },
    "environment": {
        "name_kr": "환경/기후",
        "keywords": ["기후 변화", "탄소중립", "친환경 정책", "재생에너지"],
    },
    "culture": {
        "name_kr": "문화/공연",
        "keywords": ["전시회", "공연 소식", "영화 개봉", "문화 행사"],
    },
    "law": {
        "name_kr": "생활법률/제도",
        "keywords": ["부동산 법률", "노동법 개정", "소비자 분쟁", "생활 법률"],
    },
}

# ── 카드뉴스 디자인 ──────────────────────────────────────────────────
IMG_WIDTH = 1080
IMG_HEIGHT = 1350  # 인스타 4:5 비율 (피드에서 가장 큰 노출 면적)
# ── 폰트/에셋 경로 (OS 자동감지: 로컬 Windows / GitHub Actions 리눅스) ──
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

def _find(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[-1]

KR_BOLD = _find([r"C:\Windows\Fonts\malgunbd.ttf",
                 os.path.join(ASSETS_DIR, "fonts", "NotoSansKR-Bold.ttf"),
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                 "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"])
KR_REG = _find([r"C:\Windows\Fonts\malgun.ttf",
                os.path.join(ASSETS_DIR, "fonts", "NotoSansKR-Regular.ttf"),
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"])
KR_INDEX = 1 if (KR_BOLD.endswith(".ttc") and "NotoSansCJK" in KR_BOLD) else 0
FA_PATH = _find(["/usr/share/fonts/opentype/font-awesome/FontAwesome.otf",
                 "/usr/share/fonts-font-awesome/fonts/FontAwesome.otf",
                 os.path.join(ASSETS_DIR, "fonts", "FontAwesome.otf")])
NUM_PATH = _find([os.path.join(ASSETS_DIR, "fonts", "Poppins-Bold.ttf"),
                  "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
                  KR_BOLD])

# 기존 단일 카드 호환용(사용 안 해도 무방)
FONT_BOLD, FONT_REGULAR, FONT_INDEX_KR = KR_BOLD, KR_REG, KR_INDEX

# ── 계정(카테고리)별 메타 ────────────────────────────────────────────
CATEGORY_HANDLE = {
    "food_industry": "@food_industry_news",
    "startup": "@startup_insight_news",
    "ecommerce": "@ecommerce_insight",
}
# 표지/상세에 쓸 Font Awesome 아이콘 3종 (image_gen.FA_G 키)
CATEGORY_ICONS = {
    "food_industry": ["cutlery", "money", "chart"],
    "startup": ["briefcase", "lightbulb", "money"],
    "ecommerce": ["doc", "rocket", "chart"],
}
# 표지 후킹 문구 (계정 성격에 맞춘 고정 슬로건)
CATEGORY_HOOK = {
    "food_industry": "바쁜 사장님이 놓치면 안 될 3가지 핵심",
    "startup": "창업·자영업 오늘의 핵심 3가지",
    "ecommerce": "오늘 셀러가 놓치면 안 될 3가지 핵심 이슈",
}
DEFAULT_HOOK = "오늘 꼭 알아야 할 핵심 3가지"

# 카테고리별 브랜드 컬러 (계정마다 시각적 아이덴티티 구분)
CATEGORY_COLORS = {
    "food_industry": "#E8541F",
    "ecommerce": "#1F6FE8",
    "startup": "#1FA85C",
    "realestate": "#8B1FE8",
    "finance": "#C99A1F",
    "it_tech": "#1FA8C9",
    "beauty": "#E81F8B",
    "travel": "#1FC98E",
    "parenting": "#E88B1F",
    "auto": "#4A4A4A",
    "sports": "#1F4FE8",
    "entertainment": "#C91FE8",
    "game": "#6B1FE8",
    "health": "#1FE85C",
    "pet": "#E8A81F",
    "fashion": "#E81F4F",
    "education": "#1F8BE8",
    "job": "#1FC9A8",
    "interior": "#8E6B4A",
    "cooking": "#E8621F",
    "politics": "#3A3A6B",
    "economy": "#1F6B8E",
    "environment": "#2FA847",
    "culture": "#A81FC9",
    "law": "#4A4A8E",
}

# ── 실행 설정 ──────────────────────────────────────────────────────
NEWS_PER_CATEGORY = 3        # 카테고리당 매일 게시할 뉴스 건수
NAVER_DISPLAY_PER_QUERY = 10 # 키워드 1개당 가져올 뉴스 건수 (최대 100)
