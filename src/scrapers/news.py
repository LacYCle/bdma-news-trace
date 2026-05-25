"""新闻网站爬虫 — 基于 Scrapling FetcherSession

功能:
  - 按关键词搜索新闻
  - 抓取新闻正文、配图、发布时间
  - 快速拉取头条列表

依赖:
  Scrapling FetcherSession 提供:
    - Chrome TLS 指纹模拟 (impersonate='chrome')
    - 隐身请求头
    - 自适应选择器
"""

import os
import hashlib
import re
from datetime import datetime
from typing import Optional

from scrapling.fetchers import Fetcher, FetcherSession

from .base import BaseScraper
from ..storage.models import Post, NewsArticle


class NewsScraper(BaseScraper):
    """多源新闻采集器"""

    # 各来源的 RSS/API 入口
    RSS_ENDPOINTS = {
        "sina": "https://feed.mix.sina.com.cn/api/roll/get",
        "netease": None,  # 网易用 HTML 首页
    }

    BASE_URLS = {
        "sina": "https://news.sina.com.cn",
        "netease": "https://news.163.com",
    }

    def __init__(self, adaptive_mode: bool = True, request_delay: float = 2.0,
                 max_retry: int = 3):
        super().__init__(adaptive_mode, request_delay, max_retry)
        self._session: Optional[FetcherSession] = None

    @property
    def session(self) -> FetcherSession:
        """延迟初始化 FetcherSession，模拟 Chrome TLS 指纹"""
        if self._session is None:
            self._session = FetcherSession(impersonate="chrome")
        return self._session

    def close(self):
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    # ========== 主接口 ==========

    def fetch_by_keyword(self, keyword: str, source: str = "sina",
                         max_articles: int = 50) -> list[Post]:
        """按关键词搜索新闻

        Args:
            keyword: 搜索关键词
            source: 新闻来源 ('sina' | 'netease')
            max_articles: 最大文章数
        Returns:
            统一 Post 列表
        """
        print(f"[News] 搜索 '{keyword}' @ {source} (最多 {max_articles} 篇)...")
        articles = self._search_articles(keyword, source, max_articles)

        posts = []
        for article in articles:
            try:
                if article.content:
                    post = self._article_to_post(article)
                    posts.append(post)
            except Exception as e:
                print(f"[News] 转换文章失败: {e}")

        print(f"[News] '{keyword}' @ {source} 完成, 共 {len(posts)} 篇")
        return posts

    def fetch_headlines(self, source: str = "sina") -> list[dict]:
        """快速拉取头条列表（用于事件发现）"""
        base = self.BASE_URLS.get(source, "")
        if not base:
            return []

        print(f"[News] 拉取 {source} 头条...")
        try:
            page = self.session.get(base, stealthy_headers=True)
        except Exception:
            return []

        headlines = []
        for item in page.css('.news-item, .feed-card, .item, li', adaptive=True):
            title = item.css('a::text, h2::text, .title::text').get(default="")
            link = item.css('a::attr(href)').get(default="")
            if title and link:
                headlines.append({
                    "title": title.strip(),
                    "url": link if link.startswith("http") else f"{base}{link}",
                    "source": source,
                })

        return headlines

    # ========== 内部实现 ==========

    def _search_articles(self, keyword: str, source: str,
                         max_articles: int) -> list[NewsArticle]:
        """按来源搜索文章列表"""
        articles = []

        if source == "sina":
            # 新浪: 通过 RSS 接口搜索
            rss_url = f"{self.RSS_ENDPOINTS[source]}?q={keyword}&count={max_articles}"
            try:
                feed = Fetcher.get(rss_url, stealthy_headers=True)
            except Exception:
                return articles

            news_items = feed.css('.news-item, .item',
                                  adaptive=self.adaptive_mode)[:max_articles]
            for item in news_items:
                link = item.css('a::attr(href)').get(default="")
                title = item.css('a::text').get(default="")
                if not link:
                    continue
                if not link.startswith("http"):
                    link = f"{self.BASE_URLS[source]}{link}"

                article = self._fetch_article(link, source)
                if article:
                    article.title = title or article.title
                    articles.append(article)
                self._delay()

        elif source == "netease":
            # 网易: 从首页搜索
            search_url = f"https://search.163.com/search?q={keyword}"
            try:
                page = self.session.get(search_url, stealthy_headers=True)
            except Exception:
                return articles

            for item in page.css('.search-item, .result-item',
                                 adaptive=True)[:max_articles]:
                link = item.css('a::attr(href)').get(default="")
                if link:
                    article = self._fetch_article(link, source)
                    if article:
                        articles.append(article)
                    self._delay()

        return articles

    def _fetch_article(self, url: str, source: str) -> Optional[NewsArticle]:
        """抓取单篇新闻正文"""
        try:
            page = self.session.get(url, stealthy_headers=True)
        except Exception:
            # 降级: 尝试直接用 Fetcher
            try:
                page = Fetcher.get(url, stealthy_headers=True)
            except Exception:
                return None

        from .selector_registry import SelectorRegistry
        platform_key = f"{source}_news"

        try:
            # 标题
            title_css = SelectorRegistry.get_css(platform_key, "article_title")
            title = page.css(title_css, adaptive=self.adaptive_mode).get(default="")
            if not title:
                title = page.xpath(SelectorRegistry.get_xpath(platform_key, "article_title")).get(default="")

            # 正文
            content_css = SelectorRegistry.get_css(platform_key, "article_content")
            content = "\n".join(page.css(content_css, adaptive=self.adaptive_mode).getall())
            if not content:
                content = "\n".join(page.xpath(SelectorRegistry.get_xpath(platform_key, "article_content")).getall())

            # 图片
            img_css = SelectorRegistry.get_css(platform_key, "article_images")
            image_urls = page.css(img_css, adaptive=self.adaptive_mode).getall()

            # 发布时间
            time_css = SelectorRegistry.get_css(platform_key, "publish_time")
            time_str = page.css(time_css, adaptive=True).get(default="")
            publish_time = self._parse_news_time(time_str)

            raw_id = f"{source}:{url}"
            article_id = hashlib.md5(raw_id.encode()).hexdigest()[:12]

            return NewsArticle(
                article_id=article_id,
                title=title.strip(),
                content=content.strip(),
                images=image_urls,
                source=source,
                url=url,
                publish_time=publish_time,
            )
        except Exception as e:
            print(f"[News] 解析文章失败 {url[:60]}: {e}")
            return None

    def _article_to_post(self, article: NewsArticle) -> Post:
        """NewsArticle → 统一 Post"""
        return Post(
            post_id=article.article_id,
            platform=article.source,
            post_type="article",
            text=f"{article.title}\n{article.content}" if article.title else article.content,
            image_urls=article.images,
            author_name=article.source,
            timestamp=article.publish_time,
            url=article.url,
            metadata={"category": article.category},
        )

    def _parse_news_time(self, time_str: str) -> datetime:
        """解析新闻时间格式"""
        if not time_str:
            return datetime.now()

        time_str = time_str.strip()
        # 常见中文新闻时间格式
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y年%m月%d日 %H:%M:%S",
            "%Y年%m月%d日 %H:%M",
            "%Y/%m/%d %H:%M",
            "%m月%d日 %H:%M",
        ]:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue

        # 尝试正则提取: "2025-05-25 14:30"
        match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", time_str)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M")
            except ValueError:
                pass

        return datetime.now()
