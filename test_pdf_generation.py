#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试PDF生成功能
"""

from rss_article_fetcher_enhanced import RSSArticleFetcherEnhanced
import sqlite3
import sys
import os
from pathlib import Path

# 添加当前目录到路径，以便导入主脚本
sys.path.append('.')


def test_pdf_generation():
    """测试PDF生成功能"""

    # 创建测试实例
    fetcher = RSSArticleFetcherEnhanced()

    # 从数据库获取一篇最新的文章进行测试
    try:
        with fetcher.connect_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT message_id, from_user, title, url, raw_data, created_at, account_name
                FROM wechat_articles 
                WHERE raw_data IS NOT NULL AND raw_data != ''
                ORDER BY id DESC 
                LIMIT 1
            """)

            result = cursor.fetchone()
            if not result:
                print("数据库中没有找到包含HTML内容的文章")
                return

            # 构造测试文章数据
            test_article = {
                'message_id': result[0],
                'from_user': result[1],
                'title': result[2],
                'url': result[3],
                'raw_data': result[4],
                'created_at': result[5],
                'account_name': result[6]
            }

            print(f"测试文章: {test_article['title']}")
            print(f"公众号: {test_article['account_name']}")
            print(
                f"HTML长度: {len(test_article['raw_data']) if test_article['raw_data'] else 0}")

            # 生成PDF
            print("\n开始生成PDF...")
            pdf_path = fetcher.html_to_pdf(test_article)

            if pdf_path:
                print(f"✓ PDF生成成功: {pdf_path}")

                # 检查文件大小
                if os.path.exists(pdf_path):
                    size = os.path.getsize(pdf_path)
                    print(f"  文件大小: {size} bytes")

                    if size > 1000:  # 至少1KB
                        print("✓ PDF文件大小正常")
                    else:
                        print("⚠ PDF文件可能太小")
                else:
                    print("✗ PDF文件不存在")
            else:
                print("✗ PDF生成失败")

    except Exception as e:
        print(f"测试过程出错: {e}")


if __name__ == "__main__":
    test_pdf_generation()
