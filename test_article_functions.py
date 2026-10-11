import pytest
from datetime import datetime, timedelta
import os
import csv
from sqldb import session, WxArticle, ProcessedArticle, fetch_processed_articles_by_id
from pdfsummary import save_recruitment_articles_to_csv, save_articles_to_csv, get_pdf_text
import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置一个测试文件夹路径（默认写到仓库内的 test_output/，可用环境变量覆盖）
TEST_OUTPUT_FOLDER = os.environ.get(
    "TEST_OUTPUT_FOLDER",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_output"),
)
os.makedirs(TEST_OUTPUT_FOLDER, exist_ok=True)

# 1. 创建测试数据（用于测试 fetch_processed_articles_by_id）
_INSERTED_WX_IDS = []


@pytest.fixture(scope="module")
def test_articles():
    # 插入两篇文章：一篇是今天，一篇是昨天
    today = datetime.utcnow()
    yesterday = today - timedelta(days=1)

    # 获取有效的 WxArticle 数据
    # 假设 wx_article 表中有数据
    wx_article_today = WxArticle(
        title="今日招聘信息",
        content="内容A",
        create_time=today,
        author="作者A",
        content_url="http://example.com/article1"
    )

    wx_article_yesterday = WxArticle(
        title="昨日招聘信息",
        content="内容B",
        create_time=yesterday,
        author="作者B",
        content_url="http://example.com/article2"
    )

    # 添加到 session 并提交
    session.add(wx_article_today)
    session.add(wx_article_yesterday)
    session.commit()
    _INSERTED_WX_IDS.extend([wx_article_today.id, wx_article_yesterday.id])

    # 获取插入后的文章ID（original_id）
    article_today = ProcessedArticle(
        original_id=wx_article_today.id,  # 设置有效的 original_id
        title="今日招聘信息",
        content="内容A",
        processed_summary="摘要A",
        processed_key_info={"岗位类别": "软件工程师", "工作地点": "北京"},
        file_path="/path/to/file",
        processed_time=today,
        article_type="recruitment",
        content_url="http://example.com/article1",
        account="公众号A",
        publish_date=today.date()
    )

    article_yesterday = ProcessedArticle(
        original_id=wx_article_yesterday.id,  # 设置有效的 original_id
        title="昨日招聘信息",
        content="内容B",
        processed_summary="摘要B",
        processed_key_info={"岗位类别": "产品经理", "工作地点": "上海"},
        file_path="/path/to/file",
        processed_time=yesterday,
        article_type="recruitment",
        content_url="http://example.com/article2",
        account="公众号B",
        publish_date=yesterday.date()
    )

    # 添加到 session 并提交
    session.add(article_today)
    session.add(article_yesterday)
    session.commit()

    return [article_today, article_yesterday]


# 2. 测试 fetch_processed_articles_by_id 函数


def test_fetch_processed_articles_by_id(test_articles):
    # 使用 fetch_processed_articles_by_id 查询今天的文章
    today_articles = fetch_processed_articles_by_id([], only_today=True)

    # 验证查询返回的文章是今天的文章
    assert len(today_articles) == 1
    # 确保是今天的文章
    assert today_articles[0].publish_date == datetime.utcnow().date()
    assert today_articles[0].title == "今日招聘信息"

# 3. 测试 save_recruitment_articles_to_csv 函数


def test_save_recruitment_articles_to_csv(test_articles):
    # 从数据库中获取今天的文章
    today_articles = fetch_processed_articles_by_id([], only_today=True)

    # 保存文章到CSV
    csv_file, excel_filename = save_recruitment_articles_to_csv(
        today_articles, TEST_OUTPUT_FOLDER)

    # 检查CSV文件是否生成
    print(csv_file)
    assert os.path.exists(csv_file)
    assert csv_file.endswith('.csv')

    # 检查CSV文件内容
    with open(csv_file, mode='r', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        header = next(reader)  # 获取标题行
        # 检查标题行
        assert "标题" in header
        assert "公众号" in header
        assert "发布日期" in header

        # 检查文章数据行
        row = next(reader)
        assert len(row) > 0
        assert row[0] == "今日招聘信息"  # 确保内容与插入的数据一致
        assert row[2] == today_articles[0].publish_date.strftime(
            '%Y-%m-%d')  # 确保日期是今天

    # 检查 Excel 文件是否生成
    assert os.path.exists(excel_filename)
    assert excel_filename.endswith('.xlsx')


def test_save_articles_to_csv(test_articles):
    # 从数据库中获取今天的文章
    today_articles = fetch_processed_articles_by_id([], only_today=True)

    # 保存文章到CSV
    csv_file, excel_filename = save_articles_to_csv(
        today_articles, TEST_OUTPUT_FOLDER)

    # 检查CSV文件是否生成
    print(csv_file)
    assert os.path.exists(csv_file)
    assert csv_file.endswith('.csv')

    # 检查CSV文件内容
    with open(csv_file, mode='r', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        header = next(reader)  # 获取标题行
        # 检查标题行
        assert "标题" in header
        assert "公众号" in header
        assert "发布日期" in header

        # 检查文章数据行
        row = next(reader)
        assert len(row) > 0
        assert row[0] == "今日招聘信息"  # 确保内容与插入的数据一致
        assert row[2] == today_articles[0].publish_date.strftime(
            '%Y-%m-%d')  # 确保日期是今天

    # 检查 Excel 文件是否生成
    assert os.path.exists(excel_filename)
    assert excel_filename.endswith('.xlsx')

# 4. 清理测试数据


@pytest.fixture(scope="module", autouse=True)
def cleanup(request):
    # 只删本测试自己插入的行；绝不能无条件清表（历史上这里会 delete 全表）
    def _cleanup():
        if not _INSERTED_WX_IDS:
            return
        session.query(ProcessedArticle).filter(
            ProcessedArticle.original_id.in_(_INSERTED_WX_IDS)
        ).delete(synchronize_session=False)
        session.query(WxArticle).filter(
            WxArticle.id.in_(_INSERTED_WX_IDS)
        ).delete(synchronize_session=False)
        session.commit()

    request.addfinalizer(_cleanup)


def get_pdf_paths_from_db():
    """Fetch PDF file paths from wechat_articles table in SQLite database"""
    db_path = os.environ.get("WECHAT_SQLITE_DB_PATH", "data/message_monitor.db")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query to get PDF file paths
        query = """
        SELECT pdf_path 
        FROM wechat_articles 
        WHERE pdf_path LIKE '%.pdf'
        ORDER BY process_time DESC
        LIMIT 5
        """

        cursor.execute(query)
        pdf_paths = [row[0] for row in cursor.fetchall()]

        conn.close()
        return pdf_paths

    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        return []


def test_get_pdf_text():
    """Test the get_pdf_text function with PDF paths from database"""
    pdf_paths = get_pdf_paths_from_db()

    if not pdf_paths:
        logger.error("No PDF paths found in database")
        return

    logger.info(f"Found {len(pdf_paths)} PDF files to test")

    for pdf_path in pdf_paths:
        logger.info(f"\nTesting PDF: {pdf_path}")

        if not os.path.exists(pdf_path):
            logger.error(f"PDF file does not exist: {pdf_path}")
            continue

        try:
            title, account, publish_date, link, full_text = get_pdf_text(
                pdf_path)

            logger.info("Extraction results:")
            logger.info(f"Title: {title}")
            logger.info(f"Account: {account}")
            logger.info(f"Publish Date: {publish_date}")
            logger.info(f"Link: {link}")
            logger.info(f"Text length: {len(full_text) if full_text else 0}")

            if None in (title, account, publish_date, link, full_text):
                logger.warning("Some fields are None")

        except Exception as e:
            logger.error(f"Error processing PDF {pdf_path}: {e}")


if __name__ == "__main__":
    test_get_pdf_text()
