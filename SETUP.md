# 72시간 실험 프로젝트 셋업 가이드

목표: "Claude와의 바이브코딩만으로 인스타 뉴스 계정 25개가 얼마나 클 수 있는가" 실험
시작: 2026-07-19 20:00 / 마감: 2026-07-22 20:00

(전체 배경/현황은 PROJECT_BRIEF.md 먼저 참고)

---

## Day 1 — API 발급 + 계정 3~5개 파일럿

### 1. API 키 발급
- [x] 네이버: Client ID `kjDL2RHqNOC1zqQXMwOL` / Secret `XuGHn_B0Ac` (완료, .env 반영됨)
- [ ] Gemini: aistudio.google.com → API 키 발급 (무료, 카드 불필요)

### 2. Meta 개발자 앱 생성
- [ ] developers.facebook.com → 내 앱 → "비즈니스" 유형으로 앱 생성
- [ ] "Instagram Graph API" 제품 추가
- [ ] 앱은 **개발 모드(Development Mode)로 유지** — 심사 불필요, 테스터 25명 한도
- [ ] Business Verification, App Review는 하지 않음 (범위 밖)

### 3. 인스타그램 계정 3~5개 파일럿 생성
각 계정마다:
- [ ] 신규 계정 생성 (계정 사이 시간 간격 두기, 스팸탐지 주의)
- [ ] 설정 → 계정 → 프로페셔널 계정 전환 (비즈니스)
- [ ] 페이스북 페이지 연결 (없으면 새로 생성)
- [ ] Meta 앱 대시보드 → 역할(Roles) → 테스터 추가 → 초대
- [ ] 초대받은 계정에서 테스터 초대 수락

### 4. Access Token 발급
- [ ] Graph API Explorer에서 토큰 발급
      권한: instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement
- [ ] Long-Lived Token으로 교환 (60일 유효)
- [ ] `GET /me/accounts` → 페이지ID 확인 → `GET /{page-id}?fields=instagram_business_account` → IG User ID 확인
- [ ] `.env`에 `IG_TOKEN_<카테고리>`, `IG_ACCOUNT_ID_<카테고리>` 채우기

### 5. 로컬 파이프라인 검증
```bash
cd C:\projects\newsbot
pip install -r requirements.txt
$env:PYTHONPATH="."
python pipeline.py    # dry_run=True 기본, 이미지 생성까지만 테스트
```
`output/` 폴더에 카테고리별 카드뉴스 이미지 생기면 성공.

---

## Day 2 — Railway 배포 + 실게시 검증 + 계정 확장

- [ ] Railway 프로젝트 생성 → 레포 연결
- [ ] Railway Variables에 `.env` 내용 전부 등록
- [ ] 배포 후 발급된 도메인을 `PUBLIC_BASE_URL`에 재등록 (재배포 필요)
- [ ] `POST /run-pipeline?dry_run=false` (헤더 X-Admin-Token) 로 실게시 1회 테스트
- [ ] 실제 인스타 계정에 게시물 확인
- [ ] 나머지 계정 추가 생성 (Day1의 3~4단계 반복, 최대 25개)

## Day 3 — 전체 가동 + 모니터링

- [ ] 스케줄러(매일 08:00 KST) 정상 작동 확인 (Railway Logs)
- [ ] 계정별 팔로워/도달 스냅샷 기록 시작 (매월 리포트용)
- [ ] 에러 발생 계정 트러블슈팅

---

## 알아둘 것
- 25개 계정은 전부 본인이 admin/tester로 등록된 계정만 가능
- 토큰 60일 후 만료 → 3일 실험엔 문제없음, 장기 운영시 갱신 로직 필요
- 개발 모드 rate limit 낮음 → 카테고리당 하루 3건 게시 수준이면 안전
