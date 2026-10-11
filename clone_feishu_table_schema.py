#!/usr/bin/env python3
import argparse
import json
from copy import deepcopy
from pathlib import Path

import requests


FEISHU_API = "https://open.feishu.cn/open-apis"


def load_config(config_path):
    return json.loads(Path(config_path).read_text())


def get_token(config):
    resp = requests.post(
        f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
        json={
            "app_id": config["feishu_appid"],
            "app_secret": config["feishu_appsecret"],
        },
        timeout=30,
    ).json()
    if resp.get("code") != 0:
        raise RuntimeError(resp)
    return resp["tenant_access_token"]


def request_json(method, url, headers, payload=None, timeout=60):
    resp = requests.request(method, url, headers=headers, json=payload, timeout=timeout)
    data = resp.json()
    if resp.status_code != 200 or data.get("code") != 0:
        raise RuntimeError({"status_code": resp.status_code, "response": data, "url": url, "payload": payload})
    return data


def list_fields(app_token, table_id, headers):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/fields?page_size=500"
    return (request_json("GET", url, headers).get("data") or {}).get("items") or []


def create_table(app_token, headers, table_name):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables"
    payload = {"table": {"name": table_name}}
    data = request_json("POST", url, headers, payload=payload)
    return (data.get("data") or {}).get("table_id")


def rename_table(app_token, table_id, headers, table_name):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}"
    return request_json("PATCH", url, headers, payload={"name": table_name})


def create_field(app_token, table_id, headers, field_spec):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
    return request_json("POST", url, headers, payload=field_spec)


def update_field(app_token, table_id, field_id, headers, field_spec):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}"
    return request_json("PUT", url, headers, payload=field_spec)


def field_spec_from_source(field):
    spec = {
        "field_name": field["field_name"],
        "type": field["type"],
    }
    property_data = deepcopy(field.get("property"))
    if property_data is not None:
        options = property_data.get("options")
        if options is not None:
            property_data["options"] = [
                {
                    "name": option.get("name", ""),
                    "color": option.get("color", 0),
                }
                for option in options
            ]
        spec["property"] = property_data
    return spec


def field_spec_without_options(field):
    spec = {
        "field_name": field["field_name"],
        "type": field["type"],
    }
    property_data = deepcopy(field.get("property"))
    if property_data is not None and "options" in property_data:
        property_data["options"] = []
    if property_data is not None:
        spec["property"] = property_data
    return spec


def clone_table_schema(config, source_table_id, target_table_name):
    token = get_token(config)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    app_token = config["feishu_apptoken"]

    source_fields = list_fields(app_token, source_table_id, headers)
    if not source_fields:
        raise RuntimeError(f"No fields found in source table: {source_table_id}")

    source_primary = next((field for field in source_fields if field.get("is_primary")), None)
    if not source_primary:
        raise RuntimeError(f"No primary field found in source table: {source_table_id}")

    target_table_id = create_table(app_token, headers, target_table_name)
    target_fields = list_fields(app_token, target_table_id, headers)
    if len(target_fields) != 1 or not target_fields[0].get("is_primary"):
        raise RuntimeError(f"Unexpected target bootstrap fields: {target_fields}")

    target_primary = target_fields[0]
    update_field(
        app_token,
        target_table_id,
        target_primary["field_id"],
        headers,
        field_spec_from_source(source_primary),
    )

    created_fields = []
    fallback_fields = []
    for field in source_fields:
        if field["field_id"] == source_primary["field_id"]:
            continue
        try:
            create_field(app_token, target_table_id, headers, field_spec_from_source(field))
        except RuntimeError as exc:
            if field["type"] not in {3, 4}:
                raise
            create_field(app_token, target_table_id, headers, field_spec_without_options(field))
            fallback_fields.append(field["field_name"])
        created_fields.append(field["field_name"])

    final_fields = list_fields(app_token, target_table_id, headers)
    return {
        "target_table_id": target_table_id,
        "target_table_name": target_table_name,
        "source_field_count": len(source_fields),
        "target_field_count": len(final_fields),
        "created_fields": created_fields,
        "fallback_fields": fallback_fields,
    }


def main():
    parser = argparse.ArgumentParser(description="Clone Feishu bitable schema into a new table.")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--source-table-id", required=True)
    parser.add_argument("--target-table-name", required=True)
    parser.add_argument("--rename-table-id")
    parser.add_argument("--rename-table-name")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.rename_table_id and args.rename_table_name:
        token = get_token(config)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        rename_table(config["feishu_apptoken"], args.rename_table_id, headers, args.rename_table_name)

    result = clone_table_schema(
        config=config,
        source_table_id=args.source_table_id,
        target_table_name=args.target_table_name,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
