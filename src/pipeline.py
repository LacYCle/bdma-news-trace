"""端到端数据采集流水线

用法:
  python -m src.pipeline --keyword "东方甄选事件"
  python -m src.pipeline --keyword "某争议事件" --sources weibo,sina
"""

import sys
import json
import time
import hashlib
from datetime import datetime
from typing import Optional

from .scrapers.weibo import WeiboScraper
from .scrapers.news import NewsScraper
from .scrapers.cookie_manager import CookieManager
from .scrapers.base import BaseScraper
from .storage.database import Database
from .storage.models import Post, Event


class EventTracker:
    """新闻事件发现与追踪管理"""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def discover_or_create_event(self, keyword: str) -> str:
        """发现已有事件或创建新事件"""
        existing = self.db.find_event_by_keyword(keyword)
        if existing:
            print(f"[Event] 匹配已有事件: {existing['name']} ({existing['id']})")
            return existing["id"]

        event_id = f"event_{int(time.time())}_{hashlib.md5(keyword.encode()).hexdigest()[:8]}"
        event = Event(
            event_id=event_id,
            name=keyword,
            keywords=[keyword],
        )
        self.db.create_event(event)
        print(f"[Event] 新建事件: {keyword} ({event_id})")
        return event_id

    def crawl_event(self, event_id: str, sources: list[str] = None):
        """对指定事件触发全平台采集"""
        if sources is None:
            sources = ["weibo", "sina", "netease"]

        event = self.db.get_event(event_id)
        if not event:
            print(f"[Event] 事件不存在: {event_id}")
            return []

        keywords = json.loads(event.get("keywords", "[]"))
        print(f"[Event] 开始采集 '{event['name']}' (关键词: {keywords}), 来源: {sources}")

        all_posts: list[Post] = []

        for keyword in keywords:
            # 微博
            if "weibo" in sources:
                try:
                    with WeiboScraper() as wb:
                        posts = wb.search_event(keyword, max_pages=5)
                        for p in posts:
                            p.event_id = event_id
                        all_posts.extend(posts)
                except Exception as e:
                    print(f"[Event] 微博采集失败: {e}")

            # 新闻网站
            if any(s in sources for s in ["sina", "netease"]):
                news = NewsScraper()
                try:
                    for source in sources:
                        if source in ("sina", "netease"):
                            posts = news.fetch_by_keyword(keyword, source=source)
                            for p in posts:
                                p.event_id = event_id
                            all_posts.extend(posts)
                except Exception as e:
                    print(f"[Event] 新闻采集失败: {e}")
                finally:
                    news.close()

        # 保存
        saved = self.db.insert_posts_batch(all_posts)
        self.db.update_event_stats(event_id)
        print(f"[Event] 采集完成: 共 {len(all_posts)} 条, 入库 {saved} 条")
        return all_posts


class Pipeline:
    """数据采集流水线"""

    def __init__(self, db_path: str = "data/news_trace.db"):
        self.db = Database(db_path)
        self.tracker = EventTracker(self.db)
        self.cookie_manager = CookieManager()

    def run(self, keyword: str, sources: list[str] = None,
            max_pages: int = 5):
        """执行完整采集流水线

        Args:
            keyword: 搜索关键词
            sources: 数据源列表 ['weibo', 'sina', 'netease']
            max_pages: 微博最大翻页数
        """
        print(f"""
╔══════════════════════════════════════════╗
║   新闻传播溯源数据采集流水线             ║
║   关键词: {keyword:<30} ║
║   来源: {', '.join(sources or ['weibo','sina','netease']):<33} ║
╚══════════════════════════════════════════╝
""")

        # Step 1: 事件发现
        event_id = self.tracker.discover_or_create_event(keyword)

        # Step 2: 全平台采集
        self.tracker.crawl_event(event_id, sources)

        # Step 3: 统计
        stats = self.db.stats()
        print(f"""
采集完成:
  - 事件 ID: {event_id}
  - 数据库总帖子: {stats['post_count']}
  - 数据库总事件: {stats['event_count']}
  - 平台分布: {stats['by_platform']}
""")

        return event_id


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="新闻传播溯源数据采集")
    parser.add_argument("--keyword", "-k", type=str, required=True,
                        help="搜索关键词 (如 '东方甄选事件')")
    parser.add_argument("--sources", "-s", type=str, default="weibo,sina,netease",
                        help="数据源,逗号分隔 (默认: weibo,sina,netease)")
    parser.add_argument("--max-pages", "-p", type=int, default=5,
                        help="微博最大翻页数 (默认: 5)")

    args = parser.parse_args()
    sources = [s.strip() for s in args.sources.split(",")]

    pipeline = Pipeline()
    pipeline.run(keyword=args.keyword, sources=sources, max_pages=args.max_pages)
