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


def build_carousel_caption(cat_name: str, items: list) -> str:
    """캐러셀 캡션: 오늘의 뉴스 3건 + 원문 링크 + 해시태그."""
    lines = [f"📢 오늘의 {cat_name} 뉴스"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it['headline']}")
    srcs = [it.get("source", "") for it in items if it.get("source")]
    if srcs:
        lines.append("\n원문:")
        lines += [f"· {s}" for s in srcs]
    lines.append("\n#뉴스 #오늘의뉴스 #" + cat_name.replace("/", " #"))
    return "\n".join(lines)
