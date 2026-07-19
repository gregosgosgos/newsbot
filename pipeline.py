"""
전체 파이프라인: 뉴스수집 -> AI 재구성 -> 카드뉴스 생성 -> (git 커밋/푸시) -> 인스타 게시

GitHub Actions 기반 무료 구조로 동작한다 (Railway 상시 서버 방식 아님).
Instagram Graph API는 공개 URL로 이미지를 가져가야 하므로,
1) 먼저 카테고리별 카드뉴스 이미지를 전부 생성해서 output/ 에 저장
2) git commit + push로 GitHub 레포에 반영 (public repo 전제)
3) raw.githubusercontent.com 공개 URL이 살아있는 걸 확인한 뒤 인스타 게시 API 호출

로컬 테스트(dry_run=True)에서는 git 커밋/푸시를 건너뛰고 이미지 생성까지만 검증한다.
"""
import os
import time
import subprocess
import argparse
import logging
from datetime import datetime

from config import CATEGORIES, NEWS_PER_CATEGORY
from accounts import get_account_credentials, list_active_categories
from scripts.naver_news import collect_category_news
from scripts.rewriter import rewrite_news
from scripts.image_gen import generate_card
from scripts.instagram_poster import post_image, build_caption

logger = logging.getLogger("pipeline")

# GitHub Actions가 자동으로 넣어주는 환경변수. 로컬 실행 시에는 비어있음.
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")  # 예: "osy9612/newsbot"
GITHUB_BRANCH = os.getenv("GITHUB_REF_NAME", "main")
IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS", "") == "true"


def build_image_public_url(fname: str) -> str:
    """GitHub raw 콘텐츠 공개 URL 생성 (public repo 필요)"""
    if not GITHUB_REPOSITORY:
        return f"http://localhost/output/{fname}"  # 로컬 테스트용 더미
    return f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_BRANCH}/output/{fname}"


def git_commit_and_push(message: str):
    """생성된 카드뉴스 이미지를 레포에 커밋 + 푸시. GitHub Actions 안에서만 실행."""
    if not IS_GITHUB_ACTIONS:
        logger.info("[git] GitHub Actions 환경이 아니라 커밋/푸시 스킵 (로컬 테스트)")
        return

    subprocess.run(["git", "config", "user.name", "newsbot-ci"], check=True)
    subprocess.run(["git", "config", "user.email", "newsbot-ci@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", "output/"], check=True)

    diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff_check.returncode == 0:
        logger.info("[git] 변경된 이미지 없음, 커밋 스킵")
        return

    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "push"], check=True)
    logger.info("[git] 이미지 커밋+푸시 완료")

    # raw.githubusercontent.com 반영까지 짧은 대기 (CDN 전파 여유)
    time.sleep(5)


def generate_content_for_category(category_id: str, dry_run: bool) -> dict:
    """1단계: 뉴스 수집 + AI 재구성 + 이미지 생성까지. 게시는 하지 않음."""
    cat = CATEGORIES[category_id]
    cat_name = cat["name_kr"]
    result = {"category": category_id, "posts": [], "errors": []}

    creds = get_account_credentials(category_id)
    if not creds and not dry_run:
        result["errors"].append("계정 인증정보 없음 (아직 세팅 안 됨) -> 스킵")
        return result

    news_items = collect_category_news(cat["keywords"])[:NEWS_PER_CATEGORY]
    if not news_items:
        result["errors"].append("수집된 뉴스 없음")
        return result

    for idx, item in enumerate(news_items):
        try:
            content = rewrite_news(item["title"], item["description"], cat_name)

            if content.get("is_factual_risk"):
                result["errors"].append(f"[스킵] 팩트 리스크 플래그: {content['headline']}")
                continue

            fname = f"{category_id}_{datetime.now().strftime('%Y%m%d')}_{idx}.jpg"
            out_path = f"output/{fname}"
            generate_card(content, category_id, cat_name, out_path)

            result["posts"].append({
                "fname": fname,
                "content": content,
                "source_link": item["link"],
            })
        except Exception as e:
            result["errors"].append(f"{item['title']}: {e}")

    return result


def publish_category(category_id: str, generated: dict) -> dict:
    """2단계: git push 이후, 실제로 인스타에 게시"""
    log = {"category": category_id, "posted": 0, "errors": list(generated["errors"])}

    creds = get_account_credentials(category_id)
    if not creds:
        return log

    for post in generated["posts"]:
        image_url = build_image_public_url(post["fname"])
        caption = build_caption(post["content"]["headline"], post["content"]["comment"],
                                 source_note=f"원문: {post['source_link']}")
        result = post_image(creds["ig_user_id"], creds["access_token"], image_url, caption)

        if result["success"]:
            log["posted"] += 1
        else:
            log["errors"].append(result["error"])

        time.sleep(3)

    return log


def run_full_pipeline(dry_run: bool = False) -> dict:
    targets = list(CATEGORIES.keys()) if dry_run else list_active_categories()
    summary = {"started_at": datetime.now().isoformat(), "dry_run": dry_run, "results": []}

    # 1단계: 전체 카테고리 콘텐츠+이미지 생성
    generated_map = {}
    for category_id in targets:
        logger.info(f"[{category_id}] 콘텐츠 생성 시작")
        generated_map[category_id] = generate_content_for_category(category_id, dry_run)

    if dry_run:
        # dry_run은 게시 없이 생성 결과만 반환
        for category_id, gen in generated_map.items():
            summary["results"].append({
                "category": category_id,
                "generated": len(gen["posts"]),
                "errors": gen["errors"],
            })
        return summary

    # 2단계: 이미지 전체를 한 번에 커밋+푸시 (raw URL 활성화)
    git_commit_and_push(f"news cards {datetime.now().strftime('%Y-%m-%d')}")

    # 3단계: 게시
    for category_id, gen in generated_map.items():
        logger.info(f"[{category_id}] 게시 시작")
        result = publish_category(category_id, gen)
        summary["results"].append(result)
        logger.info(f"[{category_id}] 완료: {result}")

    return summary


if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="게시 없이 생성까지만 테스트")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    result = run_full_pipeline(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
