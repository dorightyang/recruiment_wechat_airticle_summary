import csv
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime

import requests

from common import csv_columns
from sqldb import User, UserTagSubscription, get_user_subscribed_accounts, process_user_batch, session

logger = logging.getLogger("pdfsummary")


class UserInfo:
    def __init__(self, name="用户", email="", need_recruiment=False, subscribed_wechats=None):
        self.name = name
        self.email = email
        self.need_recruiment = need_recruiment
        self.subscribed_wechats = subscribed_wechats
        self.prefer_style = None

    def __str__(self):
        return (
            f"Name: {self.name}, Email: {self.email}, "
            f"Need Recruiment: {self.need_recruiment}, "
            f"Subscribed Wechats: {self.subscribed_wechats}"
        )


def _normalize_base_url(config):
    base_url = (config.get("nocodb_base_url") or "http://127.0.0.1:18080").strip()
    return base_url.rstrip("/")


def _get_nocodb_token(config):
    return (config.get("nocodb_token") or os.getenv("NOCODB_TOKEN") or "").strip()


def _create_nocodb_session(config):
    token = _get_nocodb_token(config)
    if not token:
        logger.error("NocoDB token is missing. Set nocodb_token in config or NOCODB_TOKEN env.")
        return None

    s = requests.Session()
    s.headers.update(
        {
            "xc-token": token,
            "Content-Type": "application/json",
        }
    )
    return s


def _stable_record_id(seed):
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
    return 800000000000000 + int(digest, 16)


def _to_publish_time(date_str):
    date_str = (date_str or "").strip()
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"{date_str} 00:00:00"


def _build_nocodb_recruitment_record(row):
    title = (row.get(csv_columns[0]) or "").strip()
    account = (row.get(csv_columns[1]) or "").strip()
    publish_date = (row.get(csv_columns[2]) or "").strip()
    link = (row.get(csv_columns[3]) or "").strip()
    summary = (row.get(csv_columns[4]) or "").strip()
    batch = (row.get(csv_columns[5]) or "").strip()
    location = (row.get(csv_columns[6]) or "").strip()
    when_text = (row.get(csv_columns[7]) or "").strip()
    tags = (row.get(csv_columns[8]) or "").strip()

    if not title:
        return None

    publish_time = _to_publish_time(publish_date)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record_seed = link if link else f"{title}|{publish_date}|{account}"

    raw_data = json.dumps(
        {
            "公众号": account,
            "招聘批次": batch,
            "地点": location,
            "时间": when_text,
            "标签": tags,
        },
        ensure_ascii=False,
    )

    return {
        "id": _stable_record_id(record_seed),
        "title": title,
        "content": summary,
        "summary": summary,
        "url": link or None,
        "company_name": account or None,
        "info_type": "招聘",
        "source_detail": "recruiment_article_summary",
        "publish_time": publish_time,
        "created_at": now_str,
        "updated_at": now_str,
        "raw_data": raw_data,
        "uploaded": 1,
        "uploaded_at": now_str,
        "info_category": "recruitment",
    }


def _is_duplicate_error(resp_json_or_text):
    if isinstance(resp_json_or_text, dict):
        content = json.dumps(resp_json_or_text, ensure_ascii=False)
    else:
        content = str(resp_json_or_text)
    return "23505" in content or "duplicate key value violates unique constraint" in content.lower()


def upload_to_nocodb(csv_file_path, batch_size=200, config=None):
    if config is None:
        logger.error("No config provided for NocoDB upload")
        return

    table_id = (config.get("nocodb_recruitment_table_id") or config.get("nocodb_table_id") or "").strip()
    if not table_id:
        logger.error("nocodb_recruitment_table_id (or nocodb_table_id) is missing in config")
        return

    base_url = _normalize_base_url(config)
    s = _create_nocodb_session(config)
    if s is None:
        return

    url = f"{base_url}/api/v2/tables/{table_id}/records"

    success_count = 0
    duplicate_count = 0
    failed_count = 0

    with open(csv_file_path, "r", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)
        for idx, row in enumerate(reader, start=1):
            record = _build_nocodb_recruitment_record(row)
            if record is None:
                continue

            try:
                resp = s.post(url, json=record, timeout=20)
            except Exception as e:
                failed_count += 1
                logger.error(f"NocoDB request failed at row {idx}: {e}")
                continue

            if resp.status_code in (200, 201):
                success_count += 1
            else:
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text

                if _is_duplicate_error(body):
                    duplicate_count += 1
                else:
                    failed_count += 1
                    logger.error(
                        f"NocoDB write failed at row {idx}, "
                        f"status={resp.status_code}, body={body}"
                    )

            # Keep request rate stable for NocoDB
            if idx % max(1, batch_size) == 0:
                time.sleep(0.1)

    logger.info(
        f"NocoDB upload finished: success={success_count}, "
        f"duplicate={duplicate_count}, failed={failed_count}"
    )


def _split_subscribed_accounts(raw_value):
    if raw_value is None:
        return []

    if isinstance(raw_value, list):
        values = [str(v).strip() for v in raw_value if str(v).strip()]
        return values

    text = str(raw_value)
    parts = re.split(r"[\n\s,，;；]+", text)
    return [item.strip() for item in parts if item.strip()]


def _parse_need_recruitment(raw_value):
    if raw_value is None:
        return False
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, list):
        text = " ".join(str(item) for item in raw_value)
    else:
        text = str(raw_value)

    normalized = text.strip().lower()
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    if any(marker in normalized for marker in ["否", "不需要", "不订阅", "不要", "退订", "取消", "unsubscribe", "no pandora"]):
        return False
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    return ("是" in normalized) or any(marker in normalized for marker in ["需要", "订阅", "subscribe"])


def _record_time_value(record):
    for key in ("updated_at", "last_modified_time", "created_at", "created_time"):
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            continue
        try:
            return float(text)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
    return None


def _record_to_user_info(record, config):
    email_field = config.get("nocodb_user_email_field", "邮箱")
    name_field = config.get("nocodb_user_name_field", "您希望我们怎么称呼您？【beta，还在灰度测试】")
    need_field = config.get("nocodb_user_need_field", "是否需要【Pandora招聘信息分享】订阅？")
    accounts_field = config.get(
        "nocodb_user_accounts_field",
        "请输入要个性化订阅的公众号名称【多个请换行或用空格分开】 （目前限制在30个以内，因需要一定的手动操作，暂不保证及时生效）",
    )
    style_field = config.get("nocodb_user_style_field", "您希望看到哪种风格的报告？【beta，还在灰度测试】")

    email = (record.get(email_field) or "").strip().lower()
    if not email:
        return None

    user = UserInfo()
    user.name = (record.get(name_field) or "用户").strip()
    user.email = email
    user.need_recruiment = _parse_need_recruitment(record.get(need_field))
    user.subscribed_wechats = _split_subscribed_accounts(record.get(accounts_field))
    user.prefer_style = (record.get(style_field) or "通用").strip()
    return user


def fetch_user_info_from_nocodb(config=None):
    if config is None:
        logger.error("No config provided for NocoDB user fetch")
        return []

    user_table_id = (config.get("nocodb_user_table_id") or "").strip()
    if not user_table_id:
        logger.info("nocodb_user_table_id is empty, skip NocoDB user sync")
        return []

    base_url = _normalize_base_url(config)
    s = _create_nocodb_session(config)
    if s is None:
        return []

    limit = 200
    offset = 0
    indexed_users = []
    index = 0

    while True:
        url = f"{base_url}/api/v2/tables/{user_table_id}/records?limit={limit}&offset={offset}"
        try:
            resp = s.get(url, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.error(f"Fetch NocoDB users failed: {e}")
            break

        rows = payload.get("list") or []
        for row in rows:
            user = _record_to_user_info(row, config)
            if user:
                indexed_users.append((index, _record_time_value(row), user))
                index += 1

        page_info = payload.get("pageInfo") or {}
        if page_info.get("isLastPage", True):
            break
        offset += limit

    if any(timestamp is not None for _, timestamp, _ in indexed_users):
        indexed_users.sort(key=lambda item: (item[1] or 0, item[0]))

    latest_users_by_email = {}
    for _, _, user in indexed_users:
        latest_users_by_email[user.email] = user

    return list(latest_users_by_email.values())


def _fetch_user_info_from_local_database():
    users = []
    query = (
        session.query(User)
        .join(UserTagSubscription, UserTagSubscription.user_id == User.id)
        .filter(UserTagSubscription.tag_id == 1)
        .all()
    )
    for db_user in query:
        if not db_user.email:
            continue
        user = UserInfo(
            name=db_user.name or "用户",
            email=db_user.email,
            need_recruiment=True,
            subscribed_wechats=get_user_subscribed_accounts(db_user.email),
        )
        users.append(user)
    return users


def fetch_user_info_from_nocodb_and_update_database(config=None):
    users = fetch_user_info_from_nocodb(config=config)
    if users:
        process_user_batch(users)
        return users

    logger.info("Falling back to local DB users because NocoDB user table is unavailable")
    return _fetch_user_info_from_local_database()
