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


def build_caption(headline: str, comment: str, source_note: str = "") -> str:
    tags = "#뉴스 #오늘의뉴스 #이슈"
    return f"{headline}\n\n{comment}\n\n{source_note}\n\n{tags}"
