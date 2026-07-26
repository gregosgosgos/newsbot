# OPERATIONS — 실행 · 배포 · 운영

## 매일 자동 실행 (GitHub Actions)

- 워크플로우: `.github/workflows/daily-post.yml` — 매일 cron(아침 KST) + 수동(`workflow_dispatch`).
- 폰트 설치(Noto CJK, Nanum, FontAwesome) + Poppins 다운로드 후 `python pipeline.py` 실행.
- **수동 실행**: GitHub → Actions → "Daily News Post" → Run workflow.
  - 입력 `dry_run`: `false`면 실제 게시, `true`면 이미지 생성까지만.
  - 약 6분 소요(사진 다운로드·그레이딩 포함). 3개 계정 전부 처리.

### 필요한 GitHub Secrets
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `GEMINI_API_KEY`
- 계정별 인스타 토큰/유저ID (accounts.py가 읽는 환경변수명 기준)

## 코드 변경을 GitHub에 올리는 법

로컬 개발 환경(Cowork 샌드박스)은 **GitHub 인증이 없어 직접 push 불가**.
→ 실제 push는 사용자의 Windows git(로그인 캐시됨)을 통해서만 된다.

### 권장: auto_sync.py (파일 변화 자동 커밋+푸시)
```powershell
cd C:\projects\newsbot
python auto_sync.py      # 안 되면 py auto_sync.py
```
- 창을 켜 두면 파일이 바뀔 때마다 변경이 멈춘 뒤 ~30초 안에 자동 commit+push.
- Actions가 올린 이미지 커밋과 충돌 안 나게 `pull --rebase --autostash` 처리.
- `tmpimg/`·`output/*.jpg`는 제외(.gitignore). 종료는 Ctrl+C.

### 대안: 터미널에서 수동 1회
```bash
# Git Bash
cd /c/projects/newsbot && git add -A && git commit -m "메시지" && git push origin main
```
> `.bat` 더블클릭은 이 PC의 보안 소프트웨어 때문에 실행 안 됨 — 터미널/Run 대화상자를 쓸 것.

## ⚠️ git 락(index.lock) 문제

**증상**: 커밋이 안 올라가고 `.git/index.lock`이 남아있음.
**원인**: 로컬 git과 auto_sync(또는 샌드박스 git)가 **같은 `.git`을 동시에** 만져 락이 꼬임.
같은 저장소를 두 OS 뷰(Windows + 리눅스 마운트)에서 동시에 조작하면 발생.

**해결**:
1. auto_sync 터미널에서 **Ctrl+C**로 정지
2. 락 삭제 (PowerShell):
   ```powershell
   Remove-Item -Force -ErrorAction SilentlyContinue C:\projects\newsbot\.git\index.lock
   ```
   (cmd면 `del /f /q C:\projects\newsbot\.git\index.lock`)
3. auto_sync 재시작: `python auto_sync.py`

**예방**: 개발 중에는 샌드박스에서 `git` 명령을 돌리지 말 것(상태 확인은 GitHub 웹/커밋 페이지로).
`.gitattributes`가 개행을 LF로 통일해 line-ending churn(무한 커밋)도 막아둠.

## 게시물 검증 방법

- GitHub Actions 실행 로그에서 성공/스킵 확인.
- 인스타 앱/웹에서 각 계정(`@food_industry_news`, `@ecommerce_insight`, `@startup_insight_news`)의
  최신 글 열어 표지·본문·캡션 확인.
- 로컬 렌더 미리보기: `PYTHONPATH=. python3 scripts/image_gen.py` → `output/ecommerce_test_*.jpg`.

## 카테고리/계정 추가하는 법

1. `config.py` `CATEGORIES`에 이미 25개 정의됨. 활성화하려면 해당 계정 인증정보를 시크릿/환경변수에 추가.
2. `CATEGORY_HANDLE`, `CATEGORY_COLORS`, `CATEGORY_HOOK`, `CATEGORY_ICONS`에 항목 추가.
3. `instagram_poster._CAPTION`에 계정 페르소나(hook/ask/tags) 추가(없으면 기본 캡션으로 폴백).
4. `accounts.py`가 새 계정 인증정보를 읽도록 확인.
> 인스타는 짧은 시간에 계정을 많이 만들면 스팸 탐지 위험 — 천천히 확장.

## 저작권 / 사진

- 원문 문장을 그대로 베끼지 않고 AI가 팩트만 재구성. 캡션에 **원문 링크** 명시(언론사 트래픽 유도).
- 자료사진은 원문 og:image(사용자가 이 트레이드오프 승인). `tmpimg/`에만 받고 **절대 커밋 안 함**;
  실제로 공개되는 건 렌더된 카드(`output/`)뿐.
