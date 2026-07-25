"""
Instagram API (Instagram Login / Business Login 방식)로 이미지 게시.

주의: 이 프로젝트는 페이스북 페이지 연동이 필요 없는 최신 방식
("Instagram API with Instagram Login")을 사용한다.
따라서 엔드포인트는 graph.facebook.com이 아니라 graph.instagram.com이고,
ig_user_id는 페이스북 페이지 경유로 얻는 IG Business Account ID가 아니라
Meta 대시보드의 "액세스 토큰 생성" 단계에서 직접 발급되는 Instagram 계정 ID다.

흐름:
  1) POST /{ig-user-id}/media  -> image_url + caption 전달, 컨테이너 ID 발급
  2) POST /{ig-user-id}/media_publish -> 컨테이너 ID로 실제 발행

image_url은 공개적으로 접근 가능한 URL이어야 함 (server.py의 /output 라우트로 서빙).
"""
import time
import requests

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.instagram.com/{GRAPH_API_VERSION}"


def post_image(ig_user_id: str, access_token: str, image_url: str, caption: str) -> dict:
    create_resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    create_data = create_resp.json()

    if "id" not in create_data:
        return {"success": False, "post_id": None, "error": f"컨테이너 생성 실패: {create_data}"}

    container_id = create_data["id"]
    time.sleep(2)

    publish_resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": access_token,
        },
        timeout=30,
    )
    publish_data = publish_resp.json()

    if "id" not in publish_data:
        return {"success": False, "post_id": None, "error": f"발행 실패: {publish_data}"}

    return {"success": True, "post_id": publish_data["id"], "error": None}


def post_carousel(ig_user_id: str, access_token: str, image_urls: list, caption: str) -> dict:
    """여러 장(표지+상세)을 하나의 캐러셀 게시물로 발행.
    1) 각 이미지를 is_carousel_item 컨테이너로 생성
    2) media_type=CAROUSEL 부모 컨테이너 생성 (children=자식ID들)
    3) media_publish 로 발행
    """
    child_ids = []
    for url in image_urls:
        # raw.githubusercontent CDN 전파 지연으로 인한 일시적 fetch 실패에 대비해 재시도
        r = {}
        for attempt in range(4):
            r = requests.post(
                f"{GRAPH_BASE}/{ig_user_id}/media",
                data={"image_url": url, "is_carousel_item": "true", "access_token": access_token},
                timeout=30,
            ).json()
            if "id" in r:
                break
            time.sleep(8)   # 전파 대기 후 재시도
        if "id" not in r:
            return {"success": False, "post_id": None, "error": f"자식 컨테이너 실패: {r}"}
        child_ids.append(r["id"])
        time.sleep(2)

    parent = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        data={"media_type": "CAROUSEL", "children": ",".join(child_ids),
              "caption": caption, "access_token": access_token},
        timeout=30,
    ).json()
    if "id" not in parent:
        return {"success": False, "post_id": None, "error": f"캐러셀 컨테이너 실패: {parent}"}

    time.sleep(2)
    pub = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": parent["id"], "access_token": access_token},
        timeout=30,
    ).json()
    if "id" not in pub:
        return {"success": False, "post_id": None, "error": f"발행 실패: {pub}"}
    return {"success": True, "post_id": pub["id"], "error": None}


def build_caption(headline: str, comment: str, source_note: str = "") -> str:
    tags = "#뉴스 #오늘의뉴스 #이슈"
    return f"{headline}\n\n{comment}\n\n{source_note}\n\n{tags}"


# 계정별 캡션 페르소나(공감 오프닝 · 참여 질문 · 해시태그) — 카드뉴스 계정 벤치마킹 반영
_CAPTION = {
    "이커머스": {
        "hook": "쿠팡·네이버·알리까지, 이커머스 판은 매일 바뀌죠.\n바빠서 다 못 챙기는 셀러님을 위해 오늘의 핵심만 모았어요 👇",
        "ask": "오늘 소식 중 내 사업에 제일 영향 줄 것 같은 건 뭔가요? 댓글로 알려주세요 💬",
        "tags": "#이커머스 #쿠팡 #스마트스토어 #온라인쇼핑몰 #셀러 #오픈마켓 #이커머스창업 #쇼핑몰 #전자상거래 #오늘의뉴스",
    },
    "식품/외식업": {
        "hook": "메뉴 고민에 재료값까지, 사장님은 뉴스 볼 틈도 없죠.\n외식·식품업계 오늘의 핵심만 딱 정리했어요 👇",
        "ask": "요즘 매장에서 제일 고민되는 건 뭔가요? 댓글로 나눠주세요 💬",
        "tags": "#외식업 #자영업 #식품업계 #프랜차이즈 #배달앱 #식자재 #외식창업 #사장님 #요식업 #오늘의뉴스",
    },
    "창업/자영업": {
        "hook": "시작하는 것도, 버티는 것도 쉽지 않죠.\n소상공인·자영업 사장님이 챙겨야 할 오늘의 핵심만 모았어요 👇",
        "ask": "지금 제일 절실한 지원이나 정보는 뭔가요? 댓글로 알려주세요 💬",
        "tags": "#창업 #자영업 #소상공인 #사업자대출 #창업지원 #1인창업 #상권분석 #자영업자 #소상공인지원 #오늘의뉴스",
    },
}


def build_carousel_caption(cat_name: str, items: list) -> str:
    """캐러셀 캡션: 공감 오프닝 → 뉴스 3건 → 참여 질문 → 저장·팔로우 CTA → 원문 → 해시태그."""
    c = _CAPTION.get(cat_name)
    L = []
    if c:
        L += [c["hook"], ""]
    L.append(f"📌 오늘의 {cat_name} 뉴스")
    for i, it in enumerate(items, 1):
        L.append(f"{i}. {it['headline']}")
    L.append("")
    if c:
        L += [c["ask"], ""]
    L.append("🔖 나중에 다시 볼 수 있게 저장하고,\n매일 아침 핵심만 받아보려면 팔로우 해두세요 👍")
    srcs = [it.get("source", "") for it in items if it.get("source")]
    if srcs:
        L.append("\n원문 ⬇️")
        L += [f"· {s}" for s in srcs]
    L.append("\n" + (c["tags"] if c else "#뉴스 #오늘의뉴스 #" + cat_name.replace("/", " #")))
    return "\n".join(L)
