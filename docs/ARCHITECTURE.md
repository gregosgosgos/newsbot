# ARCHITECTURE — 파이프라인 & 모듈

전체 진입점은 `pipeline.py`의 `run_full_pipeline(dry_run)`.
매일 GitHub Actions가 `python pipeline.py`(실게시) 또는 `--dry-run`(생성만)으로 호출한다.

## 실행 흐름 (pipeline.py)

```
run_full_pipeline(dry_run)
 ├─ 대상 카테고리 결정 (dry_run이면 전체, 아니면 accounts.list_active_categories())
 ├─ 카테고리별 generate_content_for_category()
 │    ├─ collect_category_news(keywords)         # 뉴스 후보(화제성 순, 중복 제거됨)
 │    ├─ 후보 루프 (최대 NEWS_PER_CATEGORY=3건 채울 때까지)
 │    │    ├─ fetch_article(link) → (본문, og:image)
 │    │    ├─ rewrite_news(...) → 카드 콘텐츠 dict
 │    │    ├─ 스킵 판정: is_promotional / is_factual_risk
 │    │    ├─ 중복 판정: 당일 topic_overlaps(accepted) / 어제 topic_overlaps(prev_days, 엄격)
 │    │    ├─ download_image(og:image) → tmpimg/ (사진 아니면 '')
 │    │    └─ items.append(카드 데이터)
 │    ├─ append_today(category, items 토큰)       # 어제-중복 방지용 기록
 │    └─ generate_carousel(...) → output/ 에 이미지 N장
 ├─ (dry_run이면 여기서 종료)
 ├─ git_commit_and_push()                         # output/ + state/ 커밋 후 push, CDN 대기 20s
 └─ 카테고리별 publish_category()
      └─ post_carousel(ig_user_id, token, 공개URL들, 캡션)
```

## 모듈별 역할

### config.py
- `CATEGORIES`: 25개 카테고리 정의. 각 `{name_kr, keywords[]}`. 네이버 API는 카테고리 파라미터가
  없어서 **키워드 여러 개로 검색 → 병합**하는 방식. 파일럿은 food_industry/ecommerce/startup만 활성.
- `CATEGORY_COLORS`: 계정별 브랜드 accent 색.
- `CATEGORY_HOOK`: 표지 후킹 슬로건. `CATEGORY_HANDLE`: 인스타 핸들. `CATEGORY_ICONS`: 표지 아이콘.
- 폰트 경로 자동감지(`_find`): 로컬 Windows(맑은고딕) / GitHub Actions(Noto CJK). 숫자=Poppins, 아이콘=FontAwesome.
- `NEWS_PER_CATEGORY=3`, `NAVER_DISPLAY_PER_QUERY=30`.

### accounts.py
- 카테고리별 인증정보(`ig_user_id`, `access_token`)를 환경변수/시크릿에서 로드.
- `get_account_credentials(cat)`, `list_active_categories()`.

### scripts/naver_news.py — 수집 & 중복제거
- `search_news(query)`: 네이버 뉴스 검색 API 호출(sort=date).
- `collect_category_news(keywords, hours_window=20)`:
  - 최근 20시간 기사만 후보. 여러 키워드 결과를 모음.
  - **화제성(보도량) 클러스터링**: 유사 제목(`_similar`)끼리 묶고, 클러스터 크기(보도량)가 큰 순 정렬.
    화제 뉴스일수록 여러 매체가 동시 보도 → 클러스터 크기가 화제성의 근사치. 대표=클러스터 내 최신.
  - `_similar(a,b)`: 제목 글자유사도 + 핵심명사 겹침으로 "같은 사건" 판정(제목만 다른 재탕 제거).
- `fetch_article(url)`: trafilatura로 (본문, og:image URL) 한 번에 추출.
- `download_image(url, dest)`: 내려받아 저장. **로고/저품질은 `_is_photographic`(image_gen)로 걸러 '' 반환**.
- `_content_tokens(text)`, `topic_overlaps(a, b, jac_thr, strong_n)`: **주제 겹침** 판정(아래 중복제거 참고).

### scripts/rewriter.py — Gemini 재구성
- `SYSTEM_PROMPT`: JSON 출력 강제. 필드: `headline, subtitle, key_stat{value,label}, lead, facts[3],
  background, simple, why, is_promotional, is_factual_risk`.
- 주의사항에 **말투 규칙**(뚝뚝 끊지 말고 연결어미·쉼표), **facts 규칙**(완결 문장·서술어 자르지 말 것·
  중복 금지·어미 다양), **숫자 상식 검증**(GDP 초과 등 엉터리 수치 배제) 포함.
- 모델: `gemini-3.1-flash-lite` (무료 티어).

### scripts/image_gen.py — 렌더링 (가장 큰 파일)
- 카드 이미지 전부. 페이지 구조·수정법은 **[DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)** 참고.
- 핵심: `generate_carousel`(전체 조립), `render_cover_photo`/`render_cover`(표지),
  `render_p1/p2/p3`(뉴스별 3면), 헬퍼(`_photo_band`, `_grade_photo`, `_is_photographic`,
  `_cover_crop`, `_wrap_smart`, `_para_hl`, `_section`, `_draw_hl` 등).

### scripts/instagram_poster.py — 게시 & 캡션
- `post_carousel`: 자식 컨테이너 → 부모 캐러셀 → publish (graph.instagram.com v21).
- `build_carousel_caption` + `_CAPTION`(계정별 페르소나): 공감 오프닝 → 뉴스 리스트 → 참여 질문
  → 저장·팔로우 CTA → 원문 링크 → 타깃 해시태그. (카드뉴스 계정 벤치마킹 반영)

### scripts/post_history.py — 어제-중복 방지(cross-day)
- `state/posted.json`에 카테고리별 [{date, headline, tokens}] 저장. 게시 때 레포에 커밋됨(다음날 실행이 읽음).
- `recent_token_sets(cat)`: **어제~며칠 전만**(오늘=0일차 제외) 반환. 하루 여러 번 실행해도 과필터 안 되게.
- `append_today(cat, entries)`: 오늘 채택분 기록 + 오래된 항목 정리.

## 중복 제거 3중 구조 (중요)

1. **같은 사건, 제목만 다름** → `naver_news._similar` (수집 단계 클러스터링에서 제거)
2. **당일 주제 겹침** (제목엔 공통어 없지만 본문 핵심어가 겹침, 예: 유통업계 위기 vs 홈플러스 회생)
   → 파이프라인에서 `topic_overlaps(느슨: jac≥0.18 or 3자+핵심어 2개)`로 채택된 뉴스와 비교해 스킵
3. **어제와 거의 판박이** → `topic_overlaps(엄격: jac≥0.34 or 4개)`로 최근 기록과 비교.
   **진전 있는 후속 기사는 통과**(엄격 임계값이라). 심야엔 뉴스 풀이 얇아 1~2건만 남을 수 있음(정상).

## 데이터 구조 — 카드 1건(item)
```python
{
  "headline": str, "subtitle": str,
  "key_stat": {"value": "9,314억 원", "label": "EU가 알리에 부과한 과징금"} 또는 {},
  "lead": str,            # 무슨 일(≈110자)
  "facts": [str, str, str],  # 핵심 포인트(완결 문장, ≤22자)
  "background": str,      # 배경(≈110자)
  "simple": str,          # 쉽게 풀어보면(≈170자)
  "why": str,             # 💡 관전 포인트(힌트 톤, ≤45자)
  "photo": str,           # tmpimg 경로 또는 ''(사진 없음/필터됨)
  "source": str,          # 원문 링크
}
```
