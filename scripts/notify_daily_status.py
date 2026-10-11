#!/usr/bin/env python3
"""每日检查招聘汇总运行状态（launchd 10:00 / Docker cron 10:30）。
成功/失败/无数据都会发邮件到 config.json 的 notify_email（可用环境变量 NOTIFY_EMAIL 覆盖）。
"""

import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtp import send_email
from common import load_app_config, setting

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(PROJECT, "data", "message_monitor.db")
LOG = os.path.join(PROJECT, "logs", "summary.log")


def read_tail(path, limit=400000):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit))
            return f.read().decode("utf-8", "ignore")
    except Exception:
        return ""


def main():
    recipient = setting("notify_email", load_app_config(), "NOTIFY_EMAIL")
    if not recipient:
        print("notify_daily_status: 未配置收件人（config.json 的 notify_email 或环境变量 NOTIFY_EMAIL）",
              file=sys.stderr)
        return 2
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tail = read_tail(LOG)

    conn = sqlite3.connect(DB)
    arts = conn.execute(
        "SELECT COUNT(*) FROM wechat_articles "
        "WHERE created_at >= ? AND created_at <= ?",
        (yesterday + " 00:00:00", yesterday + " 23:59:59"),
    ).fetchone()[0]
    proc = conn.execute(
        "SELECT COUNT(*) FROM processed_articles WHERE date(processed_time) = ?",
        (today,),
    ).fetchone()[0]
    conn.close()

    # 管道级错误（影响整次运行）才判 FAIL；单收件人发送失败单独统计，
    # 只有“全部收件人都没发出去”时才按失败处理，避免失效订阅邮箱误报。
    errors = [
        p for p in [
            "插入记录失败", "上传失败",
            "Traceback (most recent call last)", "CRITICAL",
        ]
        if p in tail
    ]
    send_fail_count = tail.count("发送邮件失败")
    send_ok_count = tail.count("发送邮件成功")
    feishu = re.findall(r"Feishu upload summary: (\{[^}]+\})", tail)
    feishu_line = feishu[-1] if feishu else "（无）"
    running = False
    stuck = False
    _pids = subprocess.run(
        ["pgrep", "-f", "pdfsummary.py"], capture_output=True, text=True,
    ).stdout.strip()
    if _pids:
        running = True
        _pid = _pids.splitlines()[0]
        _et = subprocess.run(
            ["ps", "-p", _pid, "-o", "etime="],
            capture_output=True, text=True,
        ).stdout.strip()
        # 粗解析 etime（h:mm:ss / d-hh:mm:ss）判断是否超过 3 小时
        try:
            if "-" in _et:
                days, rest = _et.strip().split("-", 1)
                hours = int(days) * 24
            else:
                rest = _et.strip()
                hours = 0
            parts = [int(x) for x in rest.split(":")]
            hours += parts[0] if len(parts) == 3 else 0
            if hours > 3:
                stuck = True
        except Exception:
            pass

    body = "\n".join([
        f"日期：{today}",
        f"昨天文章数：{arts}",
        f"今日已入库汇总记录：{proc}",
        f"飞书上传：{feishu_line}",
        f"错误标记：{errors or '无'}",
        f"邮件发送：成功 {send_ok_count} 次 / 失败 {send_fail_count} 次",
    ])

    if stuck:
        status, subject = "FAIL", f"【招聘汇总】{today} 汇总进程疑似卡死"
        body += "\n\n8:30 的汇总进程已运行超过 3 小时，疑似卡死，请检查。"
    elif running:
        status, subject = "INFO", f"【招聘汇总】{today} 仍在运行中"
        body += "\n\n8:30 的汇总进程还在运行，请稍后再确认。"
    elif arts == 0 and not errors:
        status, subject = "INFO", f"【招聘汇总】{today} 昨日无文章"
        body += "\n\n昨天没有抓到文章（可能是假期或数据源无更新），流程本身正常。"
    elif errors or (arts > 0 and proc == 0):
        status, subject = "FAIL", f"【招聘汇总】{today} 运行失败"
        body += "\n\n请检查 logs/summary.log 与 logs/backfill.log。"
    elif send_fail_count > 0 and send_ok_count == 0:
        status, subject = "FAIL", f"【招聘汇总】{today} 运行失败"
        body += "\n\n今日汇总邮件全部发送失败（无任何收件人发送成功），请检查 SMTP 与订阅列表。"
    else:
        status, subject = "OK", f"【招聘汇总】{today} 运行成功"
        if send_fail_count > 0:
            body += "\n\n今日汇总已正常发布（飞书表格 + 订阅邮件）；有部分收件人发送失败，多为失效订阅邮箱，不影响整体。"
        else:
            body += "\n\n今日汇总已正常发布（飞书表格 + 订阅邮件）。"

    send_email(subject, body, recipient, text_type="plain")
    print(f"[{status}] {subject}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
