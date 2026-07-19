"""
카테고리 <-> 인스타그램 비즈니스 계정 매핑.

환경변수 네이밍 규칙 (.env 또는 Railway Variables):
  IG_TOKEN_<CATEGORY_ID>      예: IG_TOKEN_FOOD_INDUSTRY
  IG_ACCOUNT_ID_<CATEGORY_ID>  예: IG_ACCOUNT_ID_FOOD_INDUSTRY
"""
import os
from config import CATEGORIES


def get_account_credentials(category_id: str):
    key = category_id.upper()
    token = os.getenv(f"IG_TOKEN_{key}")
    account_id = os.getenv(f"IG_ACCOUNT_ID_{key}")
    if not token or not account_id:
        return None
    return {"access_token": token, "ig_user_id": account_id}


def list_active_categories() -> list:
    return [cid for cid in CATEGORIES if get_account_credentials(cid)]
