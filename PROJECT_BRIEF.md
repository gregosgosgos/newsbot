# PROJECT BRIEF — 뉴스 인스타 자동화 실험 (읽고 시작할 것)

이 문서는 Cowork 세션이 이 프로젝트를 이어받을 때 참고할 전체 맥락/지침입니다.
작업 시작 전에 반드시 이 파일 전체를 먼저 읽고 진행하세요.

---

## 프로젝트 목적

"클로드가 3일만에 만든 사업은 어떨까" — 유튜브 콘텐츠용 실험 프로젝트.
바이브코딩만으로 뉴스 카테고리별 인스타그램 계정 25개를 만들고,
매일 아침 자동으로 뉴스 카드뉴스를 생성/게시하는 파이프라인을 구축한다.
런칭 후에는 매달 각 계정의 성장(팔로워/도달)을 리포트 영상으로 낸다.

**타임라인**: 2026-07-19 20:00 시작, 72시간(2026-07-22 20:00) 내 1차 런칭.

**중요**: 오늘(Day1) 25개 계정을 한번에 다 만들려고 하지 말 것.
인스타는 짧은 시간에 계정을 여러 개 만들면 스팸 탐지로 막힐 위험이 큼.
적게 시작해서 파이프라인이 실제로 작동하는지 검증 → 이후 확장하는 순서로 진행.

---

## 아키텍처 결정 사항 (왜 이렇게 했는지)

1. **네이버 뉴스 검색 API는 카테고리 파라미터가 없음** → 카테고리별로 키워드 세트를 만들어서
   여러 번 검색한 결과를 병합하는 방식으로 대체 (config.py의 CATEGORIES 참고)
2. **AI 리라이팅은 Claude API 대신 Gemini API 무료 티어 사용** — gemini-2.5-flash-lite,
   무료 티어로 25개 계정 분량 감당 가능. 총괄 설계/디버깅은 Claude(나)가 계속 담당.
3. **저작권 리스크 대응**: 원문을 그대로 베끼지 않고 AI가 팩트만 추출해서 새 문장으로 재구성.
   원문 링크를 캡션에 명시해서 언론사로 트래픽 유도. is_factual_risk 플래그 true면 게시 스킵.
4. **카드뉴스 이미지는 PIL로 템플릿 렌더링** (무료). 폰트는 로컬 Windows 맑은 고딕(malgun.ttf).
5. **인스타그램 게시는 Instagram API with Instagram Login(비즈니스 로그인) 사용**
   → 페이스북 페이지 연동 불필요. 엔드포인트는 graph.instagram.com.
   테스터 등록: Meta 대시보드에서 초대 → 해당 인스타 계정 자체 설정(웹사이트 권한 → 테스터 초대)에서 수락
   → 대시보드에서 바로 토큰/계정ID 발급. 페이스북 계정 신규 생성 불필요.
6. **배포는 Railway가 아니라 GitHub Actions (완전 무료로 전환, 2026-07-19 결정 변경)**
   - 이유: Railway는 상시 서버 구동이라 매달 비용 발생(최소 월 $5 수준). GitHub Actions는
     스케줄 실행(cron) 방식이라 상시 서버가 필요 없어 완전 무료로 운영 가능.
   - 구조: 매일 08:00 KST에 GitHub Actions가 깨어남 → 뉴스수집+AI재구성+카드뉴스 이미지 생성
     → 이미지를 레포에 git commit/push → raw.githubusercontent.com 공개 URL로 인스타 게시.
   - **전제조건: GitHub 레포가 Public이어야 함** (raw URL이 인증 없이 접근 가능해야 Instagram
     서버가 이미지를 가져갈 수 있음). 이미 인스타에 공개될 이미지들이라 문제 없음.
   - API 키/토큰은 절대 코드/레포에 커밋하지 않고 GitHub 레포 Settings → Secrets and variables
     → Actions 에 등록.
   - server.py, Procfile은 더 이상 안 씀 (DEPRECATED 표시만 해둠, 삭제해도 무방).

---

## 현재까지 진행 상황 (2026-07-19 기준)

- [x] 코드 전체 작성 완료 (GitHub Actions 구조로 재작성됨)
- [x] 카드뉴스 이미지 생성 로컬 테스트 완료 (정상 렌더링 확인)
- [x] 네이버 API 키 발급 완료 (.env 반영됨)
- [x] Gemini API 키 발급 완료 (.env 반영됨)
- [x] Meta 개발자 앱 생성 완료 (cncn-IG, App ID: 4556777411224156)
- [x] 인스타그램 계정 3개 생성 + 테스터 등록 + 토큰 발급 완료 (.env, workflow 반영됨)
      - food_industry_news (이메일: osy96123+food)
      - startup_insight_news (이메일: osy96123+startup)
      - ecommerce_insight (이메일: osy96123+ecommerce)
- [ ] GitHub 레포 아직 안 만듦 — 새로 만들어야 함 (public repo)
- [ ] GitHub Secrets 등록 아직 안 함
- [ ] 로컬 dry_run 테스트 아직 안 해봄 (Cowork에서 실행 필요)
- [ ] 나머지 22개 계정 아직 미생성

---

## 파일 구조 (C:\projects\newsbot)

```
config.py           # 25개 카테고리별 키워드/컬러 설정 (이미 다 채워져 있음)
accounts.py          # 카테고리↔인스타계정 매핑 (환경변수 기반, 세팅된 것만 자동 인식)
pipeline.py           # 전체 오케스트레이션 (생성→git 커밋/푸시→게시), CLI: python pipeline.py [--dry-run]
scripts/naver_news.py       # 네이버 뉴스 수집
scripts/rewriter.py          # Gemini로 재구성/분류
scripts/image_gen.py         # PIL로 카드뉴스 이미지 생성
scripts/instagram_poster.py  # graph.instagram.com API로 게시
.github/workflows/daily-post.yml   # 매일 08:00 KST 자동 실행 + 수동 실행(workflow_dispatch)
requirements.txt / .gitignore
.env                  # 로컬 테스트용 실제 키 값 (절대 커밋 금지, GitHub Secrets에 별도 등록 필요)
server.py, Procfile   # DEPRECATED — 삭제해도 됨 (Railway 방식 잔재)
```

25개 카테고리 목록: food_industry, ecommerce, startup, realestate, finance, it_tech,
beauty, travel, parenting, auto, sports, entertainment, game, health, pet, fashion,
education, job, interior, cooking, politics, economy, environment, culture, law

---

## 다음에 할 일 (순서대로)

1. **로컬 dry_run 테스트** (Cowork 터미널에서):
   ```
   cd C:\projects\newsbot
   pip install -r requirements.txt
   $env:PYTHONPATH="."
   python pipeline.py --dry-run
   ```
   → 인스타 게시 없이 뉴스수집+AI재구성+이미지생성까지 검증. output/ 폴더에 이미지 생기면 성공.

2. **GitHub 레포 생성** (public으로!) → 이 프로젝트 코드 push
   ```
   cd C:\projects\newsbot
   git init
   git add .
   git commit -m "initial commit"
   git branch -M main
   git remote add origin https://github.com/<본인계정>/newsbot.git
   git push -u origin main
   ```
   (.env는 .gitignore에 있어서 자동으로 안 올라감 — 반드시 확인)

3. **GitHub 레포 Settings → Secrets and variables → Actions → New repository secret** 으로
   `.env`에 있는 값들을 하나씩 등록 (NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, GEMINI_API_KEY,
   IG_TOKEN_FOOD_INDUSTRY, IG_ACCOUNT_ID_FOOD_INDUSTRY)

4. **GitHub Actions 탭 → Daily News Post → Run workflow (수동 실행)** 로 dry_run=true 먼저 테스트
   → 성공하면 dry_run=false 로 실제 게시 1건 테스트

5. 정상 게시 확인되면 나머지 계정 순차 확장 (계정 만들 때마다 daily-post.yml의 env 목록과
   GitHub Secrets에 동일 패턴으로 추가)

---

## 지켜야 할 것

- API 키/토큰은 코드에 하드코딩 금지, `.env`(로컬)와 GitHub Secrets(배포)로만 관리.
- 원문 기사 문장 그대로 복사 금지, 반드시 AI 재구성 거칠 것 (저작권 리스크).
- 인스타 계정을 짧은 시간에 대량 생성하지 말 것 (스팸 탐지 위험, 계정 사이 시간 간격 두기).
- GitHub 레포는 반드시 Public 유지 (raw URL 접근을 위해 필요).
- 토큰 만료(60일)는 3일 실험에는 문제없지만 장기 운영 시 갱신 로직 필요.
