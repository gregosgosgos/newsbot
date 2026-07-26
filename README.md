# newsbot — 한국어 뉴스 카드뉴스 인스타 자동화

> **새 채팅에서 이 프로젝트를 이어받는다면 이 파일부터 읽으세요.**
> 이 README가 현재 상태의 "단일 진실 원천(source of truth)"입니다.
> (`PROJECT_BRIEF.md`·`SETUP.md`는 초기 런칭 계획 기록 — 역사 참고용)

매일 아침 카테고리별 뉴스를 자동 수집 → AI로 쉽게 재구성 → 카드뉴스 이미지 생성
→ 인스타그램 캐러셀로 자동 게시하는 무료 파이프라인입니다.

- **운영 중 계정(3개 파일럿)**: `food_industry`(식품/외식업), `ecommerce`(이커머스), `startup`(창업/자영업)
- **배포**: GitHub Actions (매일 cron + 수동 실행). 상시 서버 없음 = 완전 무료.
- **레포**: 공개(public) — 이미지를 `raw.githubusercontent.com` 공개 URL로 인스타가 가져가야 하므로.

---

## 30초 요약 — 어떻게 도는가

```
[네이버 뉴스 API]  키워드로 카테고리별 수집
      │           → 화제성(보도량) 클러스터링 + 중복 제거(당일 + 어제)
      ▼
[trafilatura]      기사 본문 + 대표사진(og:image) 추출
      │           → 로고/저품질 이미지는 필터(_is_photographic)
      ▼
[Gemini]           팩트만 뽑아 쉬운 카드용 문장으로 재구성(저작권 회피)
      │           → 광고성/팩트리스크/엉터리수치면 스킵
      ▼
[PIL 렌더]         표지 1 + 뉴스별 3면 = 최대 10장 카드 이미지
      │           → 코드로 고정(매일 동일 재현, AI 이미지 생성 안 씀)
      ▼
[git push]         이미지를 레포에 커밋 → raw 공개 URL 확보
      ▼
[Instagram API]    캐러셀 게시 + 벤치마킹 반영한 캡션(저장·팔로우·해시태그)
```

전체 오케스트레이션은 `pipeline.py`. 매일 GitHub Actions(`.github/workflows/daily-post.yml`)가 실행.

---

## 문서 지도 (docs/)

| 문서 | 내용 |
|------|------|
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | 파이프라인 흐름, 모듈별 역할, 데이터 구조, 중복제거 로직 |
| **[docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md)** | 카드 디자인 시스템(표지/1·2·3면), 폰트·색, 렌더 함수, **레이아웃 수정하는 법** |
| **[docs/OPERATIONS.md](docs/OPERATIONS.md)** | 실행·배포·시크릿, **auto_sync 사용법 + git 락 문제 해결**, 계정/카테고리 추가 |
| **[docs/DECISIONS.md](docs/DECISIONS.md)** | 주요 결정과 "왜 그렇게 했는지" + 하면 안 되는 것(안티패턴) |
| **[docs/ROADMAP.md](docs/ROADMAP.md)** | 다음 할 일 후보 · 알려진 한계 |

---

## 파일 구조

```
newsbot/
├── README.md              ← 여기부터
├── pipeline.py            오케스트레이션(수집→재구성→필터→렌더→푸시→게시)
├── config.py             카테고리·키워드·색·표지문구·폰트·핸들·아이콘
├── accounts.py           계정별 인증정보(환경변수/시크릿에서 로드)
├── auto_sync.py          로컬 파일 변화 감시 → 자동 commit+push (Windows에서 실행)
├── server.py, Procfile   (구 Railway 흔적 — 현재 미사용)
├── requirements.txt
├── .github/workflows/daily-post.yml   매일 실행 워크플로우
├── scripts/
│   ├── naver_news.py     뉴스 수집·화제성 정렬·중복제거·기사/사진 추출
│   ├── rewriter.py       Gemini 프롬프트 + 재구성
│   ├── image_gen.py      카드 렌더링 전부(표지·1·2·3면·헬퍼) — 가장 큰 파일
│   ├── instagram_poster.py  캐러셀 게시 + 캡션 생성(페르소나·해시태그)
│   └── post_history.py   cross-day(어제) 중복 방지 기록(state/posted.json)
├── assets/               폰트·히어로 PNG 등
├── output/               생성된 카드 이미지(게시 때 강제 커밋됨)
├── tmpimg/               내려받은 원문 raw 사진(gitignore — 절대 커밋 안 함)
└── state/posted.json     최근 게시 뉴스 토큰 기록(cross-day 중복 방지)
```

---

## 지금 바로 알아야 할 것 (요점)

- **코드 수정 → 배포**: 로컬 샌드박스는 GitHub 인증이 없어 push 불가. `auto_sync.py`를
  Windows 터미널에서 켜두면 파일 변화 시 자동 commit+push 됨. → [OPERATIONS](docs/OPERATIONS.md)
- **게시 실행**: GitHub Actions → "Daily News Post" → Run workflow (dry_run=false). 약 6분.
- **⚠️ git 락 주의**: 로컬 git과 auto_sync가 같은 `.git`을 동시에 만지면 `index.lock`이 꼬임.
  해결법은 [OPERATIONS](docs/OPERATIONS.md#git-락index-lock-문제)에.
- **카드 디자인 바꾸려면**: `scripts/image_gen.py`. 페이지 구조·수정 포인트는 [DESIGN_SYSTEM](docs/DESIGN_SYSTEM.md).
- **뉴스 문장 품질(말투·팩트)**: `scripts/rewriter.py`의 `SYSTEM_PROMPT`.
- **캡션/해시태그**: `scripts/instagram_poster.py`의 `_CAPTION` + `build_carousel_caption`.

## 현재 진행 상태 (2026-07 기준)

- 파일럿 3계정에 매일 자동 게시 정상 작동. 사진 표지·자료사진·중복제거·캡션 전략 반영됨.
- 다음 후보: 표지 후킹 호기심형, 계정 프로필(bio/하이라이트) 세팅, 성과 분석 연동, 계정 확장.
  → [ROADMAP](docs/ROADMAP.md)
