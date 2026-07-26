# DESIGN_SYSTEM — 카드 디자인 (image_gen.py)

카드는 전부 **코드로 렌더링**한다(PIL). AI 이미지 생성 안 씀 → 매일/몇 년이 지나도 동일하게 재현.
파일: `scripts/image_gen.py`. 캔버스 `W=1080, H=1350` (인스타 4:5).

## 캐러셀 구성 (generate_carousel)

```
슬라이드 0   : 표지 (cover)
뉴스 1 → 3면 : P1, P2, P3
뉴스 2 → 3면 : P1, P2, P3
뉴스 3 → 3면 : P1, P2, P3
```
뉴스 3건이면 총 10장. 심야엔 1~2건만 나올 수 있음.

## 표지 (cover)

- **사진 표지** `render_cover_photo`: 그날 뉴스 중 **좋은 자료사진이 있는 첫 뉴스**의 사진을 전면 배경으로
  깔고(브랜드 네이비로 컬러그레이드), 하단 스크림 위에 제목("오늘의 {cat} 뉴스") + 후킹 + 헤드라인 3건 + CTA.
  → 매일 표지 이미지가 달라져 피드에서 시선을 끈다.
- **폴백** `render_cover`: 좋은 사진이 없으면 확성기(3D 히어로) 표지.
- 어느 쪽을 쓸지는 `generate_carousel`에서 `cover_photo` 유무로 자동 분기.

## 뉴스 1건 = 3면 구조

렌더 순서와 채우는 전략(현재 기준):

### P1 — `render_p1(cat, name, idx, npages, headline, lead, key_stat, photo, out)`
- **사진 있음**: 상단 자료사진 밴드(`_photo_band`) + 헤드라인(밑줄) + 리드(standfirst).
- **사진 없음**: 헤드라인 + 큰 수치 히어로(값 위/라벨 아래) + 리드 → **블록 세로 중앙 정렬**.
  - 수치 라벨은 반드시 숫자 **아래**에(옆에 붙이면 긴 수치일 때 화면 밖으로 잘림).

### P2 — `render_p2(cat, name, idx, npages, key_stat, facts, background, out)`
- **상단부터** 채움: [수치 패널(사진 있을 때만)] + 핵심 팩트(1·2·3) + 배경.
- 수치 패널: 값+라벨을 **실제 글자 높이 측정(textbbox)** 해서 박스 세로 정중앙에 배치(안 그러면 아래로 쏠림).
- 팩트 번호: 첫 줄 높이를 측정해 `anchor="lm"`으로 세로 중앙 정렬. 구분선 없이 여백으로 분리(FGAP).

### P3 — `render_p3(cat, name, idx, npages, background, simple, why, is_last, out)`
- **상단 정렬**: 배경(있으면) + "쉽게 풀어보면"(simple, ≈170자) + 💡 관전 포인트 박스.
- 💡 박스 문구는 박스 **세로 중앙**(`(box_h-text_h)//2`).
- **마지막 카드(`is_last`)**: 하단에 **저장 CTA**(북마크 아이콘 `` + "저장해두면 필요할 때 다시 볼 수 있어요")
  + 푸터 "팔로우하고 매일 아침 받기 →". (뉴닉 벤치마킹 — 저장·재방문 유도)

> 배포 이력상 P2/P3의 배경 배치·중앙정렬 방식은 여러 번 바뀌었음. 지금은 "P2가 배경까지 담아 꽉 차고,
> P3는 쉽게풀어보면(길게)+💡"이 기본. "핵심 팩트 페이지가 썰렁"하면 배경이 P2에 있는지 확인.

## 폰트 · 색

- 한글: `_kf(bold, size)` (Windows 맑은고딕 / Actions Noto CJK, config에서 자동감지).
- 숫자: `_nf(size)` (Poppins-Bold). 아이콘: `_fa(size)` (FontAwesome 4.7, 글리프는 `FA_G`).
- 배경: 딥네이비 그라디언트(`_DBG_T/M/B`) + accent 글로우. 본문색 `_DBODY`(near-white).
- accent = 카테고리 색(`CATEGORY_COLORS`)을 밝게(`_lighten`).

## 핵심 헬퍼 (수정 시 알아둘 것)

| 헬퍼 | 역할 |
|------|------|
| `_wrap_smart(d, text, font, maxw)` | **본문 줄바꿈**. 줄을 채우되 60%+ 찼을 때 쉼표·마침표에서 끊고, 마지막 줄 외톨이 단어 방지. lead/background/simple에 사용. |
| `_para_hl(...)` | 문단 그리기(내부에서 `_wrap_smart`) + 숫자 하이라이트. |
| `_draw_hl(...)` / `_HL_RE` | 한 줄에서 수치 토큰(9,314억·8%·32명 등)만 accent색으로. |
| `_section(d, M, label, y, acc)` | 섹션 라벨(얇은 틱 + 톤다운 라벨). "핵심 팩트/배경/쉽게 풀어보면". |
| `_photo_band(img, box, path)` | 자료사진: 커버크롭 + 컬러그레이드 + 하단 스크림 + 테두리 + "관련 이미지" 태그. |
| `_grade_photo(ph)` | 사진을 네이비 듀오톤으로 통일(로고든 현장사진이든 같은 무드). |
| `_is_photographic(im)` | 로고/저품질(흰배경·저채도·너무 작음·극단비율) 판별 → 아니면 사진 안 씀. |
| `_cover_crop(ph, w, h)` | 비율 유지 커버-핏 중앙 크롭. |
| `_glass`, `_grad_round`, `_glow`, `_fa_icon` | 글래스 패널·그라디언트 버튼·글로우·아이콘. |

## 자주 하는 수정 레시피

- **본문 폰트 크기**: `render_p1/p2/p3` 안의 `LF/BF/SF = _kf(False, 37)` 등. 줄 수·측정값도 같이 확인.
- **줄바꿈 규칙**: `_wrap_smart` (구두점 임계값 `maxw*0.6`, 외톨이 방지 블록).
- **섹션 라벨 이름**: `render_p3`의 `_section(..., "쉽게 풀어보면", ...)` 및 P2 하단 안내문구.
- **저장/팔로우 문구**: `render_p3`의 `is_last` 블록 + `_dfoot(...)` tail.
- **표지 후킹 문구**: `config.CATEGORY_HOOK`.
- **말투·팩트·수치 품질**: 이미지가 아니라 `rewriter.py`의 프롬프트에서.

## 로컬에서 렌더 미리보기

```bash
cd <repo>
PYTHONPATH=. python3 scripts/image_gen.py   # __main__의 테스트 아이템으로 output/ecommerce_test_*.jpg 생성
```
`scripts/image_gen.py` 맨 아래 `__main__`에 테스트용 item 3건(사진/무사진/무수치 케이스)이 있음.
디자인 바꾸면 이걸로 먼저 렌더 → 이미지 확인 후 배포하는 게 안전.
