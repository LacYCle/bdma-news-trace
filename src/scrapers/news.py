"""新闻网站爬虫 — 基于 Scrapling Fetcher

功能:
  - 抓取新闻列表页 + 本地关键词过滤
  - 抓取新闻正文、配图、发布时间
  - 支持 新浪/网易 双源

依赖:
  Scrapling Fetcher.get(impersonate='chrome', stealthy_headers=True):
    - Chrome TLS 指纹模拟
    - 真实浏览器请求头
    - 自适应选择器 (adaptive=True)
"""

import hashlib
import re
from datetime import datetime
from typing import Optional

from scrapling.fetchers import Fetcher

from .base import BaseScraper
from ..storage.models import Post, NewsArticle


class NewsScraper(BaseScraper):
    """多源新闻采集器"""

    # 新闻列表页（按时间倒序，含最新文章链接）
    # 注意: 使用服务端渲染的主页，而非 JS 动态加载的子页
    LIST_PAGES = {
        "sina": [
            "https://news.sina.com.cn/",             # 新浪新闻首页（静态 HTML）
            "https://www.sina.com.cn/",              # 新浪门户首页
        ],
        "netease": [
            "https://news.163.com/",                 # 网易新闻首页
        ],
    }

    BASE_URLS = {
        "sina": "https://news.sina.com.cn",
        "netease": "https://news.163.com",
    }

    def __init__(self, adaptive_mode: bool = True, request_delay: float = 2.0,
                 max_retry: int = 3):
        super().__init__(adaptive_mode, request_delay, max_retry)

    def close(self):
        """NewsScraper 无长连接，close 为空操作"""
        pass

    # ========== 主接口 ==========

    def fetch_by_keyword(self, keyword: str, source: str = "sina",
                         max_articles: int = 50) -> list[Post]:
        """按关键词搜索新闻

        策略: 抓取新闻列表页 → 按标题关键词过滤 → 抓取正文

        Args:
            keyword: 搜索关键词
            source: 新闻来源 ('sina' | 'netease')
            max_articles: 最大文章数
        Returns:
            统一 Post 列表
        """
        print(f"[News] 搜索 '{keyword}' @ {source} (最多 {max_articles} 篇)...")

        # Step 1: 从列表页收集文章链接
        article_links = self._discover_articles(source, keyword, max_articles)
        print(f"[News] 发现 {len(article_links)} 篇候选文章")

        # Step 2: 逐个抓取正文
        posts = []
        for link in article_links[:max_articles]:
            try:
                article = self._fetch_article(link, source)
                if article and article.content:
                    post = self._article_to_post(article)
                    posts.append(post)
                    if len(posts) % 5 == 0:
                        print(f"[News]   {len(posts)}/{min(len(article_links), max_articles)}...")
            except Exception as e:
                print(f"[News] 抓取失败 {link[:60]}: {e}")
            self._delay()

        print(f"[News] '{keyword}' @ {source} 完成, 共 {len(posts)} 篇")
        return posts

    def fetch_headlines(self, source: str = "sina") -> list[dict]:
        """快速拉取头条列表（用于事件发现）"""
        base = self.BASE_URLS.get(source, "")
        if not base:
            return []

        print(f"[News] 拉取 {source} 头条...")
        headlines = []
        urls = self.LIST_PAGES.get(source, [f"{base}/"])

        for list_url in urls[:1]:  # 只取第一个列表页
            try:
                page = Fetcher.get(
                    list_url,
                    impersonate="chrome",
                    stealthy_headers=True,
                    timeout=15,
                )
            except Exception:
                continue

            for item in page.css('a, .news-item a, .item a, li a, h2 a, h3 a'):
                title = item.css('::text').get(default="")
                link = item.css('::attr(href)').get(default="")
                if not title or not link:
                    continue
                if not link.startswith("http"):
                    link = f"{base}{link}" if link.startswith("/") else f"{base}/{link}"

                title = title.strip()
                if len(title) >= 6:  # 过滤太短的标题
                    headlines.append({
                        "title": title,
                        "url": link,
                        "source": source,
                    })
                if len(headlines) >= 50:
                    break

        return headlines

    # ========== 内部实现 ==========

    def _discover_articles(self, source: str, keyword: str,
                           limit: int) -> list[str]:
        """从新闻列表页发现匹配关键词的文章链接

        抓取列表页 → CSS 提取所有链接 → 标题关键词匹配
        """
        links = []
        keywords = keyword.split()  # 支持多词匹配
        list_urls = self.LIST_PAGES.get(source, [])

        for list_url in list_urls:
            if len(links) >= limit * 2:  # 多取一些候选
                break

            try:
                page = Fetcher.get(
                    list_url,
                    impersonate="chrome",
                    stealthy_headers=True,
                    timeout=15,
                )
            except Exception:
                continue

            # 提取所有带链接的条目
            for item in page.css(
                'a, .news-item, .item, li, [class*="item"], [class*="news"]'):
                if len(links) >= limit * 2:
                    break

                # 提取链接和标题文本
                link = item.css('::attr(href)').get(default="")
                if not link:
                    link = item.css('a::attr(href)').get(default="")
                if not link:
                    continue

                title = item.css('::text').get(default="")
                if not title:
                    title = item.css('a::text').get(default="")
                title = title.strip()

                # 补全相对 URL
                base = self.BASE_URLS[source]
                if link.startswith("/"):
                    link = f"{base}{link}"
                elif not link.startswith("http"):
                    continue

                # 只保留新闻文章页（排除视频、专题等）
                if not self._is_article_url(link, source):
                    continue

                # 关键词匹配（标题或链接）
                if title and any(kw in title for kw in keywords):
                    if link not in links:
                        links.append(link)

            self._delay()

        return links

    def _is_article_url(self, url: str, source: str) -> bool:
        """判断 URL 是否为新闻文章页"""
        if source == "sina":
            # 新浪文章: https://news.sina.com.cn/c/2025-05-25/doc-xxxxx.shtml
            return bool(re.search(r'/doc-[\w]+\.s?html?', url))
        elif source == "netease":
            # 网易文章: https://www.163.com/news/article/XXXX.html
            return bool(re.search(r'/article/\w+\.html', url) or
                       re.search(r'/\d{4}/\d{2}/\d{2}/\w+\.html', url))
        return True  # 其他来源不做过滤

    def _fetch_article(self, url: str, source: str) -> Optional[NewsArticle]:
        """抓取单篇新闻正文"""
        try:
            page = Fetcher.get(
                url,
                impersonate="chrome",
                stealthy_headers=True,
                timeout=15,
            )
        except Exception:
            return None

        from .selector_registry import SelectorRegistry
        platform_key = f"{source}_news"

        try:
            # 标题
            title_css = SelectorRegistry.get_css(platform_key, "article_title")
            title = page.css(title_css).get(default="")
            if not title:
                title = page.xpath(
                    SelectorRegistry.get_xpath(platform_key, "article_title")
                ).get(default="")
            if not title:
                title = page.css('h1::text').get(default="")

            # 正文
            content_css = SelectorRegistry.get_css(platform_key, "article_content")
            content_paras = page.css(content_css).getall()
            if not content_paras:
                content_paras = page.xpath(
                    SelectorRegistry.get_xpath(platform_key, "article_content")
                ).getall()
            if not content_paras:
                content_paras = page.css('p::text').getall()
            content = "\n".join(p for p in content_paras if len(p.strip()) > 10)

            # 图片
            img_css = SelectorRegistry.get_css(platform_key, "article_images")
            image_urls = page.css(img_css).getall()
            if not image_urls:
                image_urls = page.css('img::attr(src)').getall()
            # 过滤小图/图标
            image_urls = [u for u in image_urls if not u.endswith(('.gif', '.svg', '.ico'))]

            # 发布时间
            time_css = SelectorRegistry.get_css(platform_key, "publish_time")
            time_str = page.css(time_css).get(default="")
            if not time_str:
                time_str = page.css('.time::text, .date::text, [class*="time"]::text').get(default="")
            publish_time = self._parse_news_time(time_str)

            raw_id = f"{source}:{url}"
            article_id = hashlib.md5(raw_id.encode()).hexdigest()[:12]

            return NewsArticle(
                article_id=article_id,
                title=title.strip() if title else "",
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

        # 常见格式
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y年%m月%d日 %H:%M:%S",
            "%Y年%m月%d日 %H:%M",
            "%Y/%m/%d %H:%M",
            "%m月%d日 %H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ]:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue

        # 正则提取
        match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", time_str)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M")
            except ValueError:
                pass

        return datetime.now()
