#!/usr/bin/env bash
# 生成 rss_article_fetcher_enhanced.py 的 cron 配置（可选的历史部署辅助脚本）
#
# 路径与解释器都可用环境变量覆盖，默认取脚本所在目录与当前 python3：
#   SCRIPT_DIR   默认 = 本脚本所在目录
#   PYTHON_PATH  默认 = command -v python3
#   SCRIPT_NAME  默认 = rss_article_fetcher_enhanced.py
#   SCHEDULE     默认 = "0 * * * *"（每小时一次）
#   CRON_LOG     默认 = cron.log
#   OUT          默认 = rss_cron_job.txt
#
# 用法：
#   ./setup_cron.sh
#   PYTHON_PATH=/path/to/venv/bin/python SCHEDULE="*/15 * * * *" ./setup_cron.sh
set -euo pipefail

SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
PYTHON_PATH="${PYTHON_PATH:-$(command -v python3)}"
SCRIPT_NAME="${SCRIPT_NAME:-rss_article_fetcher_enhanced.py}"
CRON_LOG="${CRON_LOG:-cron.log}"
SCHEDULE="${SCHEDULE:-0 * * * *}"
OUT="${OUT:-rss_cron_job.txt}"

CRON_LINE="$SCHEDULE cd $SCRIPT_DIR && $PYTHON_PATH $SCRIPT_NAME >> $CRON_LOG 2>&1"

cat > "$OUT" <<EOF
# RSS公众号文章爬取定时任务（默认每小时一次，改 SCHEDULE 可调频率）
$CRON_LINE
EOF

echo "cron job 配置已生成到 $OUT："
echo "  $CRON_LINE"
echo ""
echo "安装："
echo "  (crontab -l 2>/dev/null; echo '$CRON_LINE') | crontab -"
echo "验证："
echo "  crontab -l"
echo "日志："
echo "  tail -f $CRON_LOG"
