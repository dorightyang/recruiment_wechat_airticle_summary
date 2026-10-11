#!/usr/bin/env python3
"""发送运行状态邮件：notify.py <subject> [body]
收件人取 config.json 的 notify_email，可用环境变量 NOTIFY_EMAIL 覆盖。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtp import send_email
from common import load_app_config, setting


def main():
    if len(sys.argv) < 2:
        print("usage: notify.py <subject> [body]")
        return 2
    subject = sys.argv[1]
    body = sys.argv[2] if len(sys.argv) > 2 else subject
    recipient = setting("notify_email", load_app_config(), "NOTIFY_EMAIL")
    if not recipient:
        print("notify: 未配置收件人（config.json 的 notify_email 或环境变量 NOTIFY_EMAIL）",
              file=sys.stderr)
        return 2
    send_email(subject, body, recipient, text_type="plain")
    print(f"notify sent to {recipient}: {subject}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
