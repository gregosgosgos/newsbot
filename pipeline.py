"""전체 파이프라인: 뉴스수집 -> AI 재구성 -> 카드뉴스(표지+상세) -> (git 커밋/푸시) -> 인스타 캐러셀 게시

GitHub Actions 기반 무료 구조. Instagram Graph API는 공개 URL로 이미지를 가져가야 하므로,
1) 카테고리별 카드뉴스 이미지(표지 1 + 상세 3 = 4장)를 output/ 에 생성
2) git commit + push로 GitHub 레포에 반영 (public repo 전제)
3) raw.githubusercontent.com 공개 URL로 캐러셀 게시

로컬 테스트(dry_run=True)에서는 git/게시를 건너뛰고 이미지 생성까지만 검증한다.
"""
import os
import time
import subprocess
import argparse
import logging
from datetime import datetime, timezone, timedelta

from config import CATEGORIES, NEWS_PER_CATEGORY, CATEGORY_HOOK, DEFAULT_HOOK
from accounts import get_account_credentials, list_active_categories
from scripts.naver_news import collect_category_news, fetch_article_text
from scripts.rewriter import rewrite_news
from scripts.image_gen import generate_carousel
from scripts.instagram_poster import post_carousel, build_carousel_caption

logger = logging.getLogger("pipeline")
KST = timezone(timedelta(hours=9))

GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")
GITHUB_BRANCH = os.getenv("GITHUB_REF_NAME", "main")
IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS", "") == "true"


def build_image_public_url(fname: str) -> str:
    if not GITHUB_REPOSITORY:
        return f"http://localhost/output/{fname}"
    return f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_BRANCH}/output/{fname}"


def git_commit_and_push(message: str):
    if not IS_GITHUB_ACTIONS:
        logger.info("[git] GitHub Actions 환경이 아니라 커밋/푸시 스킵 (로컬 테스트)")
        return
    subprocess.run(["git", "config", "user.name", "newsbot-ci"], check=True)
    subprocess.run(["git", "config", "user.email", "newsbot-ci@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", "-f", "output/"], check=True)  # gitignore 무시하고 강제 추가
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        logger.info("[git] 변경된 이미지 없음, 커밋 스킵"); return
    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "push"], check=True)
    logger.info("[git] 이미지 커밋+푸시 완료")
    time.sleep(20)   # raw.githubusercontent CDN 전파 대기 (인스타 fetch 실패 방지)


def generate_content_for_category(category_id: str, dry_run: bool) -> dict:
    """뉴스 수집 + AI 재구성 + 카드뉴스(표지+상세) 생성. 게시는 하지 않음."""
    cat = CATEGORIES[category_id]; cat_name = cat["name_kr"]
    result = {"category": category_id, "paths": [], "items": [], "errors": []}

    creds = get_account_credentials(category_id)
    if not creds and not dry_run:
        result["errors"].append("계정 인증정보 없음 (아직 세팅 안 됨) -> 스킵"); return result

    candidates = collect_category_news(cat["keywords"])
    if not candidates:
        result["errors"].append("수집된 뉴스 없음"); return result

    items = []
    examined = 0
    MAX_EXAMINE = NEWS_PER_CATEGORY + 5   # 광고/스킵 대비 여유 후보 검토
    for item in candidates:
        if len(items) >= NEWS_PER_CATEGORY or examined >= MAX_EXAMINE:
            break
        examined += 1
        try:
            body = fetch_article_text(item.get("link", ""))
            content = rewrite_news(item["title"], item["description"], body, cat_name)
            if content.get("is_promotional"):
                result["errors"].append(f"[스킵] 광고/홍보성: {item['title']}"); continue
            if content.get("is_factual_risk"):
                result["errors"].append(f"[스킵] 팩트 리스크: {content.get('headline')}"); continue
            items.append({
                "headline": content.get("headline", ""),
                "subtitle": content.get("subtitle", ""),
                "lead": content.get("lead", ""),
                "facts": content.get("facts", []),
                "background": content.get("background", ""),
                "simple": content.get("simple", ""),
                "why": content.get("why", ""),
                "source": item.get("link", ""),
            })
        except Exception as e:
            result["errors"].append(f"{item['title']}: {e}")

    if not items:
        result["errors"].append("생성된 카드 없음"); return result

    date_str = datetime.now(KST).strftime("%Y.%m.%d")
    hook = CATEGORY_HOOK.get(category_id, DEFAULT_HOOK)
    prefix = f"{category_id}_{datetime.now(KST).strftime('%Y%m%d')}"
    result["paths"] = generate_carousel(category_id, cat_name, date_str, hook, items, "output", prefix)
    result["items"] = items
    return result


def publish_category(category_id: str, generated: dict) -> dict:
    """git push 이후, 캐러셀(표지+상세)을 하나의 게시물로 발행."""
    log = {"category": category_id, "posted": 0, "errors": list(generated["errors"])}
    creds = get_account_credentials(category_id)
    if not creds or not generated["paths"]:
        return log
    cat_name = CATEGORIES[category_id]["name_kr"]
    urls = [build_image_public_url(os.path.basename(p)) for p in generated["paths"]]
    caption = build_carousel_caption(cat_name, generated["items"])
    res = post_carousel(creds["ig_user_id"], creds["access_token"], urls, caption)
    if res["success"]:
        log["posted"] = 1
    else:
        log["errors"].append(res["error"])
    return log


def run_full_pipeline(dry_run: bool = False) -> dict:
    targets = list(CATEGORIES.keys()) if dry_run else list_active_categories()
    summary = {"started_at": datetime.now(KST).isoformat(), "dry_run": dry_run, "results": []}

    generated_map = {}
    for category_id in targets:
        logger.info(f"[{category_id}] 콘텐츠 생성 시작")
        generated_map[category_id] = generate_content_for_category(category_id, dry_run)

    if dry_run:
        for category_id, gen in generated_map.items():
            summary["results"].append({
                "category": category_id,
                "slides": len(gen["paths"]),   # 표지 1 + 상세 N
                "errors": gen["errors"],
            })
        return summary

    git_commit_and_push(f"news cards {datetime.now(KST).strftime('%Y-%m-%d')}")

    for category_id, gen in generated_map.items():
        logger.info(f"[{category_id}] 캐러셀 게시 시작")
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
    print(json.dumps(run_full_pipeline(dry_run=args.dry_run), ensure_ascii=False, indent=2))
