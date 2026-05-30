"""数据采集 Demo — Jupyter Notebook 配套脚本

用法:
  python scripts/scrape_demo.py --keyword "东方甄选"
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def demo(keyword: str = "东方甄选"):
    # 示例 1: 微博搜索
    print("=" * 60)
    print(f"示例 1: 微博关键词搜索 ({keyword})")
    print("=" * 60)

    from src.scrapers.weibo import WeiboScraper
    from src.scrapers.cookie_manager import CookieManager

    cm = CookieManager()
    print(f"Cookie 池: {cm.status()}")

    if not cm.is_empty:
        with WeiboScraper(cookie_manager=cm) as wb:
            posts = wb.search_event(keyword, max_pages=2)
            print(f"获取到 {len(posts)} 条微博")
            for p in posts[:3]:
                print(f"  [{p.timestamp}] {p.author_name}: {p.text[:60]}...")
    else:
        print("Cookie 池为空，跳过微博搜索。请先放入 Cookie 文件。")
        cm.prompt_export_guide()

    # 示例 2: 新闻搜索
    print("\n" + "=" * 60)
    print(f"示例 2: 新闻网站搜索 ({keyword})")
    print("=" * 60)

    from src.scrapers.news import NewsScraper

    news = NewsScraper()
    try:
        posts = news.fetch_by_keyword(keyword, source="sina", max_articles=5)
        print(f"Sina 获取到 {len(posts)} 篇新闻")
        for p in posts[:3]:
            print(f"  [{p.timestamp}] {p.platform}: {p.text[:60]}...")

        posts = news.fetch_by_keyword(keyword, source="netease", max_articles=5)
        print(f"NetEase 获取到 {len(posts)} 篇新闻")
        for p in posts[:3]:
            print(f"  [{p.timestamp}] {p.platform}: {p.text[:60]}...")
    finally:
        news.close()

    print("\n" + "=" * 60)
    print("Demo 完成")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", "-k", type=str, default="中国")
    args = parser.parse_args()
    demo(keyword=args.keyword)
