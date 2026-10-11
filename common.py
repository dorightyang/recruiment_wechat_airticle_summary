import json
import os


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")


csv_columns = ['标题', '公众号', '发布日期', '原文链接', '摘要', '招聘批次', '地点', '时间', '标签']


def read_config(config_path):
    try:
        print(f"Reading config from {config_path}")
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)
            return config
    except FileNotFoundError:
        print(f"Error: The file {config_path} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: The file {config_path} could not be parsed.")
        return None


def load_app_config(config_path=None):
    """加载应用配置。

    优先级：显式传入的路径 > 环境变量 PDFSUMMARY_CONFIG > 仓库根目录 config.json。
    读不到或解析失败时返回 {}（调用方按各自的缺省值处理），不抛异常。
    """
    path = config_path or os.getenv("PDFSUMMARY_CONFIG") or DEFAULT_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as config_file:
            return json.load(config_file) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def setting(name, config=None, env_name=None, default=""):
    """读一项配置，优先级：环境变量 > config.json 字段 > default。

    name 默认按大写当作环境变量名（notify_email → NOTIFY_EMAIL）。
    空字符串一律视为「未设置」，继续往下回落。
    """
    env_name = env_name or name.upper()
    value = os.getenv(env_name, "")
    if not str(value).strip():
        value = (config or {}).get(name, "")
    return str(value).strip() or default
