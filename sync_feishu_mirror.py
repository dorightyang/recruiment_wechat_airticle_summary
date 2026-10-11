#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from up2feishu import backfill_feishu_from_local_csvs


def _load_config(config_path):
    return json.loads(Path(config_path).read_text())


def main():
    parser = argparse.ArgumentParser(description="Compare local recruitment CSVs against Feishu and optionally backfill.")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--data-dir", default="data", help="Directory containing *_招聘信息汇总.csv files")
    parser.add_argument("--start-date", help="Only include CSVs on or after YYYY-MM-DD")
    parser.add_argument("--end-date", help="Only include CSVs on or before YYYY-MM-DD")
    parser.add_argument("--max-records", type=int, help="Cap the number of missing records to upload")
    parser.add_argument("--batch-size", type=int, default=500, help="Feishu batch_create size, capped at 500")
    parser.add_argument("--dry-run", action="store_true", help="Only compare, do not upload")
    args = parser.parse_args()

    config = _load_config(args.config)
    result = backfill_feishu_from_local_csvs(
        data_dir=args.data_dir,
        config=config,
        start_date=args.start_date,
        end_date=args.end_date,
        max_records=args.max_records,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
