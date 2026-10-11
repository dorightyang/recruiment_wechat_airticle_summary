#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS公众号文章爬取脚本
从RSS地址获取公众号文章信息，存储到数据库中
支持增量更新、错误处理和日志记录
"""

import sqlite3
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import logging
import sys
import argparse
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import json

# RSS源配置（走环境变量，避免把带 token 的地址写进仓库）
RSS_URL = os.environ.get("RSS_URL", "")
DB_PATH = os.environ.get("WECHAT_SQLITE_DB_PATH", "data/message_monitor.db")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rss_fetcher.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class RSSArticleFetcher:
    def __init__(self, db_path=DB_PATH, rss_url=RSS_URL):
        self.db_path = db_path
        self.rss_url = rss_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def connect_db(self):
        """连接数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def fetch_rss(self):
        """获取RSS内容"""
        try:
            logger.info(f"正在获取RSS内容: {self.rss_url}")
            response = self.session.get(self.rss_url, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'

            logger.info(f"RSS获取成功，内容长度: {len(response.text)}")
            return response.text
        except Exception as e:
            logger.error(f"RSS获取失败: {e}")
            raise

    def parse_rss(self, rss_content):
        """解析RSS内容"""
        try:
            root = ET.fromstring(rss_content)
            items = []

            # 查找所有item
            for item in root.findall('.//item'):
                article_data = {}

                # 提取基本信息
                title_elem = item.find('title')
                article_data['title'] = title_elem.text if title_elem is not None else None

                link_elem = item.find('link')
                article_data['url'] = link_elem.text if link_elem is not None else None

                # dc:creator 需要使用命名空间
                creator_elem = item.find(
                    './/{http://purl.org/dc/elements/1.1/}creator')
                article_data['account_name'] = creator_elem.text if creator_elem is not None else None
                # 同样的值
                article_data['from_user'] = article_data['account_name']

                # guid作为message_id
                guid_elem = item.find('guid')
                article_data['message_id'] = guid_elem.text if guid_elem is not None else None

                # 发布时间
                pubdate_elem = item.find('pubDate')
                if pubdate_elem is not None:
                    try:
                        # 解析RSS时间格式：Sat, 19 Jul 2025 22:58:00 +0800
                        pubdate_str = pubdate_elem.text
                        # 移除时区信息简化解析
                        pubdate_clean = re.sub(
                            r'\s+[+-]\d{4}$', '', pubdate_str)
                        dt = datetime.strptime(
                            pubdate_clean, '%a, %d %b %Y %H:%M:%S')
                        article_data['created_at'] = dt.strftime(
                            '%Y-%m-%d %H:%M:%S')
                    except Exception as e:
                        logger.warning(f"时间解析失败: {pubdate_elem.text}, 错误: {e}")
                        article_data['created_at'] = datetime.now().strftime(
                            '%Y-%m-%d %H:%M:%S')
                else:
                    article_data['created_at'] = datetime.now().strftime(
                        '%Y-%m-%d %H:%M:%S')

                # 描述内容 (HTML)
                desc_elem = item.find('description')
                if desc_elem is not None:
                    article_data['raw_data'] = desc_elem.text
                    # 从HTML中提取纯文本
                    article_data['content'] = self.extract_text_from_html(
                        desc_elem.text)
                else:
                    article_data['raw_data'] = None
                    article_data['content'] = None

                # 设置默认值
                article_data['processed'] = False
                article_data['pandora_processed'] = False
                article_data['article_type'] = 'wechat'
                article_data['summary'] = None
                article_data['cover_url'] = None
                article_data['pdf_path'] = None
                article_data['images'] = None
                article_data['process_time'] = None

                # 验证必要字段
                if article_data['message_id'] and article_data['title']:
                    items.append(article_data)
                    logger.debug(f"解析文章: {article_data['title'][:50]}...")
                else:
                    logger.warning(f"跳过无效文章，缺少必要字段: {article_data}")

            logger.info(f"成功解析 {len(items)} 篇文章")
            return items

        except ET.ParseError as e:
            logger.error(f"RSS XML解析失败: {e}")
            raise
        except Exception as e:
            logger.error(f"RSS解析过程出错: {e}")
            raise

    def extract_text_from_html(self, html_content):
        """从HTML中提取纯文本内容"""
        if not html_content:
            return None

        try:
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(html_content, 'html.parser')

            # 移除script和style标签
            for script in soup(["script", "style"]):
                script.decompose()

            # 获取纯文本
            text = soup.get_text()

            # 清理多余的空白
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip()
                      for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)

            return text[:5000] if text else None  # 限制长度

        except Exception as e:
            logger.warning(f"HTML文本提取失败: {e}")
            return html_content[:1000] if html_content else None

    def get_existing_message_ids(self, conn):
        """获取数据库中已存在的message_id集合"""
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT message_id FROM wechat_articles WHERE message_id IS NOT NULL")
            existing_ids = {row[0] for row in cursor.fetchall()}
            logger.info(f"数据库中已有 {len(existing_ids)} 篇文章")
            return existing_ids
        except Exception as e:
            logger.error(f"获取已存在文章ID失败: {e}")
            return set()

    def insert_articles(self, conn, articles):
        """批量插入文章到数据库"""
        if not articles:
            logger.info("没有新文章需要插入")
            return 0

        try:
            cursor = conn.cursor()

            insert_sql = """
                INSERT INTO wechat_articles (
                    message_id, from_user, title, url, summary, cover_url, 
                    content, pdf_path, images, created_at, raw_data, 
                    processed, process_time, account_name, pandora_processed, article_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            insert_data = []
            for article in articles:
                insert_data.append((
                    article['message_id'],
                    article['from_user'],
                    article['title'],
                    article['url'],
                    article['summary'],
                    article['cover_url'],
                    article['content'],
                    article['pdf_path'],
                    article['images'],
                    article['created_at'],
                    article['raw_data'],
                    article['processed'],
                    article['process_time'],
                    article['account_name'],
                    article['pandora_processed'],
                    article['article_type']
                ))

            cursor.executemany(insert_sql, insert_data)
            conn.commit()

            inserted_count = cursor.rowcount
            logger.info(f"成功插入 {inserted_count} 篇新文章")
            return inserted_count

        except Exception as e:
            logger.error(f"文章插入失败: {e}")
            conn.rollback()
            raise

    def run(self, dry_run=False):
        """运行RSS爬取流程"""
        try:
            logger.info("=== RSS文章爬取开始 ===")

            # 1. 获取RSS内容
            rss_content = self.fetch_rss()

            # 2. 解析RSS
            articles = self.parse_rss(rss_content)

            if not articles:
                logger.info("没有解析到任何文章")
                return

            # 3. 连接数据库
            with self.connect_db() as conn:

                # 4. 获取已存在的文章ID（增量更新）
                existing_ids = self.get_existing_message_ids(conn)

                # 5. 筛选新文章
                new_articles = [
                    article for article in articles
                    if article['message_id'] not in existing_ids
                ]

                logger.info(
                    f"总共解析 {len(articles)} 篇文章，其中 {len(new_articles)} 篇是新文章")

                if dry_run:
                    logger.info("=== DRY RUN 模式，不实际插入数据库 ===")
                    for article in new_articles[:3]:  # 只显示前3篇
                        logger.info(
                            f"新文章: {article['title']} | {article['account_name']} | {article['created_at']}")
                    return

                # 6. 插入新文章
                inserted_count = self.insert_articles(conn, new_articles)

                logger.info(f"=== RSS文章爬取完成，新增 {inserted_count} 篇文章 ===")

        except Exception as e:
            logger.error(f"RSS爬取流程失败: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(description='RSS公众号文章爬取脚本')
    parser.add_argument('--dry-run', action='store_true',
                        help='试运行模式，不实际插入数据库')
    parser.add_argument('--rss-url', default=RSS_URL,
                        help='RSS地址（必填；也可用环境变量 RSS_URL 提供）')
    parser.add_argument('--db-path', default=DB_PATH, help='数据库路径')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 创建并运行爬取器
    fetcher = RSSArticleFetcher(db_path=args.db_path, rss_url=args.rss_url)

    try:
        fetcher.run(dry_run=args.dry_run)
    except KeyboardInterrupt:
        logger.info("用户中断执行")
    except Exception as e:
        logger.error(f"执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
