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
        raise RuntimeError({"status_code": resp.status_code, "response": data})
    return data


def list_fields(app_token, table_id, headers):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/fields?page_size=200"
    return (request_json("GET", url, headers).get("data") or {}).get("items") or []


def list_views(app_token, table_id, headers):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/views?page_size=200"
    return (request_json("GET", url, headers).get("data") or {}).get("items") or []


def get_view(app_token, table_id, view_id, headers):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/views/{view_id}"
    return (request_json("GET", url, headers).get("data") or {}).get("view") or {}


def create_field(app_token, table_id, headers, field_spec):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
    return request_json("POST", url, headers, payload=field_spec)


def create_view(app_token, table_id, headers, view_name, view_type):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/views"
    payload = {"view_name": view_name, "view_type": view_type}
    return (request_json("POST", url, headers, payload=payload).get("data") or {}).get("view") or {}


def update_view(app_token, table_id, view_id, headers, payload):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/views/{view_id}"
    return request_json("PATCH", url, headers, payload=payload)


def delete_view(app_token, table_id, view_id, headers):
    url = f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/views/{view_id}"
    return request_json("DELETE", url, headers)


def build_field_maps(fields):
    by_name = {}
    by_id = {}
    option_id_to_name = {}
    option_name_to_id = {}

    for field in fields:
        field_name = field.get("field_name")
        field_id = field.get("field_id")
        by_name[field_name] = field
        by_id[field_id] = field

        options = ((field.get("property") or {}).get("options") or [])
        if options:
            name_map = {}
            for option in options:
                option_name = option.get("name")
                option_id = option.get("id")
                if option_name:
                    name_map[option_name] = option_id
                if option_id:
                    option_id_to_name[(field_id, option_id)] = option_name
            option_name_to_id[field_name] = name_map

    return {
        "by_name": by_name,
        "by_id": by_id,
        "option_id_to_name": option_id_to_name,
        "option_name_to_id": option_name_to_id,
    }


def field_spec_from_source(field):
    spec = {
        "field_name": field["field_name"],
        "type": field["type"],
    }
    property_data = deepcopy(field.get("property"))
    if property_data:
        options = property_data.get("options")
        if options is not None:
            property_data["options"] = [
                {"name": opt.get("name"), "color": opt.get("color")}
                for opt in options
                if opt.get("name")
            ]
        spec["property"] = property_data
    return spec


def ensure_missing_fields(app_token, source_fields, target_fields, headers, table_id):
    target_names = {field["field_name"] for field in target_fields}
    created = []
    for field in source_fields:
        name = field["field_name"]
        if name in target_names:
            continue
        if name == "多行文本":
            continue
        create_field(app_token, table_id, headers, field_spec_from_source(field))
        created.append(name)
        target_names.add(name)
    return created


def transform_filter_value(source_field, target_field, source_maps, target_maps, raw_value):
    if raw_value is None:
        return None

    if source_field["type"] not in {3, 4}:
        return raw_value

    try:
        old_option_ids = json.loads(raw_value)
    except Exception:
        return raw_value

    option_names = []
    for option_id in old_option_ids:
        option_name = source_maps["option_id_to_name"].get((source_field["field_id"], option_id))
        if option_name:
            option_names.append(option_name)

    if target_field["type"] in {3, 4}:
        target_option_ids = []
        target_name_map = target_maps["option_name_to_id"].get(target_field["field_name"], {})
        for option_name in option_names:
            target_option_id = target_name_map.get(option_name)
            if target_option_id:
                target_option_ids.append(target_option_id)
        return json.dumps(target_option_ids, ensure_ascii=False)

    if target_field["type"] == 1:
        return json.dumps(option_names, ensure_ascii=False)

    return raw_value


def transform_view_property(source_view, source_maps, target_maps):
    property_data = deepcopy(source_view.get("property"))
    if not property_data:
        return None

    transformed = {}

    hidden_fields = property_data.get("hidden_fields")
    if hidden_fields is not None:
        mapped_hidden = []
        for field_id in hidden_fields:
            source_field = source_maps["by_id"].get(field_id)
            if not source_field:
                continue
            target_field = target_maps["by_name"].get(source_field["field_name"])
            if target_field:
                mapped_hidden.append(target_field["field_id"])
        transformed["hidden_fields"] = mapped_hidden

    filter_info = property_data.get("filter_info")
    if filter_info:
        conditions = []
        for condition in filter_info.get("conditions") or []:
            source_field = source_maps["by_id"].get(condition["field_id"])
            if not source_field:
                continue
            target_field = target_maps["by_name"].get(source_field["field_name"])
            if not target_field:
                continue

            conditions.append(
                {
                    "field_id": target_field["field_id"],
                    "operator": condition["operator"],
                    "value": transform_filter_value(
                        source_field,
                        target_field,
                        source_maps,
                        target_maps,
                        condition.get("value"),
                    ),
                }
            )
        transformed["filter_info"] = {
            "conditions": conditions,
            "conjunction": (filter_info.get("conjunction") or "and"),
        }

    hierarchy_config = property_data.get("hierarchy_config")
    if hierarchy_config is not None:
        transformed["hierarchy_config"] = hierarchy_config

    return transformed


def sync_views(config, source_table_id, target_table_id, delete_default=False):
    token = get_token(config)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    app_token = config["feishu_apptoken"]

    source_fields = list_fields(app_token, source_table_id, headers)
    target_fields = list_fields(app_token, target_table_id, headers)

    created_fields = ensure_missing_fields(
        app_token,
        source_fields,
        target_fields,
        headers,
        target_table_id,
    )
    target_fields = list_fields(app_token, target_table_id, headers)

    source_maps = build_field_maps(source_fields)
    target_maps = build_field_maps(target_fields)

    source_views = list_views(app_token, source_table_id, headers)
    target_views = list_views(app_token, target_table_id, headers)
    target_view_by_name = {view["view_name"]: view for view in target_views}

    created_views = []
    updated_views = []

    for source_view_brief in source_views:
        view_name = source_view_brief["view_name"]
        view_type = source_view_brief["view_type"]
        try:
            source_view = get_view(app_token, source_table_id, source_view_brief["view_id"], headers)
        except Exception:
            source_view = {
                "view_name": view_name,
                "view_type": view_type,
                "property": None,
            }

        target_view = target_view_by_name.get(view_name)
        if not target_view:
            target_view = create_view(app_token, target_table_id, headers, view_name, view_type)
            created_views.append({"view_name": view_name, "view_type": view_type})
            target_view_by_name[view_name] = target_view

        property_payload = transform_view_property(source_view, source_maps, target_maps)
        if property_payload is not None:
            update_view(
                app_token,
                target_table_id,
                target_view["view_id"],
                headers,
                payload={
                    "view_name": view_name,
                    "property": property_payload,
                },
            )
            updated_views.append({"view_name": view_name, "view_type": view_type})

    deleted_default = None
    if delete_default:
        target_views_after = list_views(app_token, target_table_id, headers)
        for view in target_views_after:
            if view["view_name"] == "表格视图 1":
                delete_view(app_token, target_table_id, view["view_id"], headers)
                deleted_default = view["view_id"]
                break

    return {
        "created_fields": created_fields,
        "created_views": created_views,
        "updated_views": updated_views,
        "deleted_default_view_id": deleted_default,
        "target_views_total": len(list_views(app_token, target_table_id, headers)),
    }


def main():
    parser = argparse.ArgumentParser(description="Copy Feishu bitable views from one table to another.")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--source-table-id", required=True)
    parser.add_argument("--target-table-id", required=True)
    parser.add_argument("--delete-default", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    result = sync_views(
        config=config,
        source_table_id=args.source_table_id,
        target_table_id=args.target_table_id,
        delete_default=args.delete_default,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
