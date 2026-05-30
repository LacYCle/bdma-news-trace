"""新闻网站爬虫 — 基于 Scrapling Fetcher + JSON API

功能:
  - 新浪: 通过 JSON API 获取文章列表（多字段关键词匹配，直接从API获取内容）
  - 网易: 通过 JSON API + 列表页回退
  - 抓取新闻正文、配图、发布时间、互动数据

依赖:
  Scrapling Fetcher.get(impersonate='chrome', stealthy_headers=True):
    - Chrome TLS 指纹模拟
    - 真实浏览器请求头
"""

import hashlib
import json
import re
import urllib.request
from datetime import datetime
from typing import Optional

from scrapling.fetchers import Fetcher

from .base import BaseScraper
from ..storage.models import Post, NewsArticle


class NewsScraper(BaseScraper):
    """多源新闻采集器"""

    # 新浪新闻 roll API — 返回 JSON 文章列表（服务端渲染，无需 JS）
    # lid 留空 + 多频道覆盖
    SINA_API = (
        "https://feed.mix.sina.com.cn/api/roll/get"
        "?pageid=153&lid={lid}&k=&num=50&page={page}"
    )

    # 网易头条列表 API
    NETEASE_HEADLINE_API = (
        "https://c.m.163.com/nc/article/headline/"
        "T1348647853363-{offset}-20.html"
    )

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

        策略: 抓取新闻列表页 → 多字段关键词匹配 → 直接从API获取内容(省去逐篇请求)

        Args:
            keyword: 搜索关键词
            source: 新闻来源 ('sina' | 'netease')
            max_articles: 最大文章数
        Returns:
            统一 Post 列表
        """
        print(f"[News] 搜索 '{keyword}' @ {source} (最多 {max_articles} 篇)...")

        # Step 1: 从列表API收集候选文章（含完整元数据）
        candidates = self._discover_articles(source, keyword, max_articles)
        print(f"[News] 发现 {len(candidates)} 篇候选文章")

        # Step 2: 直接从 API 数据创建 Post（大部分文章无需额外请求）
        posts = []
        for cand in candidates[:max_articles]:
            try:
                post = self._api_item_to_post(cand, source, keyword)
                if post and post.text.strip():
                    posts.append(post)
            except Exception as e:
                print(f"[News] 解析失败 {cand.get('url', '')[:60]}: {e}")

        # Step 3: 对内容过短的文章，抓取完整正文
        short_posts = [p for p in posts if len(p.text) < 100]
        if short_posts:
            print(f"[News] {len(short_posts)} 篇内容较短，抓取完整正文...")
            for i, post in enumerate(short_posts):
                try:
                    article = self._fetch_article(post.url, source)
                    if article and len(article.content) > len(post.text):
                        post.text = f"{article.title}\n{article.content}" if article.title else article.content
                        if article.images:
                            post.image_urls = article.images
                except Exception:
                    pass
                if (i + 1) % 5 == 0:
                    print(f"[News]   正文补全 {i+1}/{len(short_posts)}...")
                self._delay()

        # Step 4: 尝试获取互动数据
        for post in posts[:5]:  # 只对前5篇尝试获取互动数据
            try:
                engagement = self._fetch_engagement(post.url, source)
                if engagement:
                    post.comment_count = engagement.get("comments", 0)
                    post.repost_count = engagement.get("reposts", 0)
                    post.like_count = engagement.get("likes", 0)
                    post.engagement_count = post.comment_count + post.repost_count + post.like_count
            except Exception:
                pass
            self._delay()

        print(f"[News] '{keyword}' @ {source} 完成, 共 {len(posts)} 篇")
        return posts

    def fetch_headlines(self, source: str = "sina") -> list[dict]:
        """快速拉取头条列表（用于事件发现）"""
        if source not in self.BASE_URLS:
            return []

        print(f"[News] 拉取 {source} 头条...")
        headlines = []

        if source == "sina":
            try:
                api_url = self.SINA_API.format(lid="2509", page=1)
                req = urllib.request.Request(
                    api_url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
                        ),
                        "Referer": "https://news.sina.com.cn/",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("result", {}).get("data", []):
                    title = item.get("title", "")
                    url = item.get("url", "")
                    if title and url and len(title) >= 6:
                        headlines.append({"title": title, "url": url, "source": source})
            except Exception:
                pass
        else:
            base = self.BASE_URLS[source]
            try:
                page = Fetcher.get(
                    f"{base}/", impersonate="chrome",
                    stealthy_headers=True, timeout=15,
                )
                for item in page.css('a, h2 a, h3 a'):
                    title = item.css('::text').get(default="").strip()
                    link = item.css('::attr(href)').get(default="")
                    if not title or not link or len(title) < 6:
                        continue
                    if not link.startswith("http"):
                        link = f"{base}{link}" if link.startswith("/") else f"{base}/{link}"
                    headlines.append({"title": title, "url": link, "source": source})
                    if len(headlines) >= 50:
                        break
            except Exception:
                pass

        return headlines

    # ========== 内部实现 ==========

    def _discover_articles(self, source: str, keyword: str,
                           limit: int) -> list[dict]:
        """根据 source 选择最优发现策略，返回候选文章列表 [{title, url, intro, ...}]"""
        if source == "sina":
            return self._discover_sina_api(keyword, limit)
        elif source == "netease":
            return self._discover_netease(keyword, limit)
        return []

    def _discover_sina_api(self, keyword: str, limit: int) -> list[dict]:
        """新浪新闻 JSON API — 多字段关键词匹配

        匹配 title + intro + keywords + summary + stitle + wapsummary，
        显著提高召回率。
        """
        candidates = []
        # 扩展频道覆盖: 国内, 国际, 社会, 财经, 军事, 教育, 科技, 体育
        lids = ["2509", "2510", "2511", "2512", "2515", "2516", "266", "2514"]

        for lid in lids:
            if len(candidates) >= limit * 2:
                break

            for page in range(1, 3):  # 每个频道翻 2 页
                if len(candidates) >= limit * 2:
                    break
                try:
                    api_url = self.SINA_API.format(lid=lid, page=page)
                    req = urllib.request.Request(
                        api_url,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/125.0.0.0 Safari/537.36"
                            ),
                            "Referer": "https://news.sina.com.cn/",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode("utf-8"))

                    if data.get("result", {}).get("status", {}).get("code") != 0:
                        continue

                    for item in data["result"]["data"]:
                        title = item.get("title", "")
                        url = item.get("url", "")
                        if not title or not url:
                            continue

                        # 多字段匹配 — 在 title/intro/keywords/summary/stitle 中搜索
                        search_text = " ".join([
                            title,
                            item.get("intro", ""),
                            item.get("keywords", ""),
                            item.get("summary", ""),
                            item.get("stitle", ""),
                            item.get("wapsummary", ""),
                        ])

                        if keyword in search_text and url not in {c["url"] for c in candidates}:
                            candidates.append({
                                "title": title,
                                "url": url,
                                "intro": item.get("intro", ""),
                                "summary": item.get("summary", ""),
                                "keywords": item.get("keywords", ""),
                                "media_name": item.get("media_name", ""),
                                "ctime": item.get("ctime", ""),
                                "images": item.get("images", []),
                                "commentid": item.get("commentid", ""),
                            })
                except Exception:
                    continue
                self._delay()

        print(f"[News] 新浪 API: 多字段匹配 '{keyword}' 发现 {len(candidates)} 篇")
        return candidates

    def _discover_netease(self, keyword: str, limit: int) -> list[dict]:
        """网易新闻发现 — 头条 API + 首页兜底"""
        candidates = []

        # 策略1: 头条 API（获取最新新闻列表）
        try:
            api_url = self.NETEASE_HEADLINE_API.format(offset=0)
            req = urllib.request.Request(
                api_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                    "Referer": "https://news.163.com/",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                headline_data = json.loads(resp.read().decode("utf-8"))

            # 格式: { "T1348647853363": [...] }
            for key, items in headline_data.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    title = item.get("title", "")
                    url = item.get("url", "") or item.get("docurl", "")
                    digest = item.get("digest", "")
                    if not title or not url:
                        continue
                    if keyword in title or keyword in digest:
                        candidates.append({
                            "title": title,
                            "url": url,
                            "intro": digest,
                            "summary": digest,
                            "keywords": keyword,
                            "media_name": item.get("source", ""),
                            "ctime": item.get("ptime", ""),
                            "images": [],
                        })
            print(f"[News] 网易头条 API: 发现 {len(candidates)} 篇")
        except Exception as e:
            print(f"[News] 网易头条 API 失败: {e}")

        if len(candidates) >= limit:
            return candidates

        # 策略2: 首页兜底 — 用 Fetcher 抓取，从所有可点击元素中提取链接标题
        list_urls = [
            "https://www.163.com/",
            "https://news.163.com/domestic/",
        ]

        for list_url in list_urls:
            if len(candidates) >= limit * 2:
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

            seen_urls = {c["url"] for c in candidates}

            # 宽泛获取: 从所有有文本的 <a> 标签中提取
            for a_tag in page.css('a'):
                if len(candidates) >= limit * 2:
                    break
                link = a_tag.css('::attr(href)').get(default="")
                # 获取链接的完整文本内容，而不仅仅是直接文本
                title_text = a_tag.css('::text').get(default="").strip()
                # 如果 ::text 拿不到（嵌套元素场景），用 XPath 提取所有文本节点
                if not title_text:
                    all_texts = a_tag.xpath('.//text()').getall()
                    title_text = ' '.join(t.strip() for t in all_texts if t.strip())

                if not link or not title_text or len(title_text) < 6:
                    continue

                # 补全相对 URL
                if link.startswith("//"):
                    link = f"https:{link}"
                elif link.startswith("/"):
                    link = f"https://www.163.com{link}"
                elif not link.startswith("http"):
                    continue

                # 关键词匹配 + 去重
                if keyword in title_text and link not in seen_urls:
                    candidates.append({
                        "title": title_text,
                        "url": link,
                        "intro": "",
                        "summary": "",
                        "keywords": keyword,
                        "media_name": "netease",
                        "ctime": "",
                        "images": [],
                    })
                    seen_urls.add(link)

            self._delay()

        print(f"[News] 网易: 共发现 {len(candidates)} 篇匹配 '{keyword}' 的文章")
        return candidates

    def _api_item_to_post(self, item: dict, source: str, keyword: str) -> Optional[Post]:
        """从 API 条目直接创建 Post（避免逐篇请求）"""
        title = item.get("title", "")
        intro = item.get("intro", "") or item.get("summary", "")
        url = item.get("url", "")
        if not title or not url:
            return None

        # 内容: 标题 + 简介
        text = f"{title}\n{intro}" if intro else title

        # 图片: API 可能返回空列表或 None
        images = item.get("images", [])
        if not isinstance(images, list):
            images = []

        # 时间:
        timestamp = datetime.now()
        ctime = item.get("ctime", "")
        if ctime:
            try:
                if ctime.isdigit():
                    timestamp = datetime.fromtimestamp(int(ctime))
                else:
                    timestamp = self._parse_news_time(ctime)
            except (ValueError, OSError):
                pass

        raw_id = f"{source}:{url}"
        article_id = hashlib.md5(raw_id.encode()).hexdigest()[:12]

        author = item.get("media_name", "") or source

        return Post(
            post_id=article_id,
            platform=source,
            post_type="article",
            text=text,
            image_urls=images,
            author_name=author,
            timestamp=timestamp,
            url=url,
            metadata={
                "keywords": item.get("keywords", keyword),
                "category": "",
                "commentid": item.get("commentid", ""),
            },
        )

    def _fetch_article(self, url: str, source: str) -> Optional[NewsArticle]:
        """抓取单篇新闻正文（仅当 API intro 内容不足时使用）"""
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

    def _fetch_engagement(self, url: str, source: str) -> dict:
        """尝试获取文章的互动数据（评论数等）"""
        result = {"comments": 0, "reposts": 0, "likes": 0}

        if source == "sina":
            # 新浪文章页面通常有评论数
            try:
                page = Fetcher.get(url, impersonate="chrome",
                                   stealthy_headers=True, timeout=10)
                # 多种可能的选择器
                comment_text = page.css(
                    '.comment-count::text, .cmt-count::text, '
                    '[class*="comment"] em::text, [class*="comment"] span::text, '
                    '.num::text'
                ).get(default="")
                if comment_text:
                    nums = re.findall(r'(\d[\d,]*)', comment_text)
                    if nums:
                        result["comments"] = int(nums[0].replace(",", ""))
            except Exception:
                pass

        elif source == "netease":
            # 网易文章有 "跟贴" 数
            try:
                page = Fetcher.get(url, impersonate="chrome",
                                   stealthy_headers=True, timeout=10)
                tie_text = page.css(
                    '.post_comment_tiecount::text, .js-tiecount::text, '
                    '.end-text::text, [class*="tie"]::text'
                ).get(default="")
                if tie_text:
                    nums = re.findall(r'(\d[\d,]*)', tie_text)
                    if nums:
                        result["comments"] = int(nums[0].replace(",", ""))
                else:
                    # 正则兜底
                    body = page.css('body').get(default="")
                    match = re.search(r'跟贴[：:\s]*(\d[\d,]*)', body) if body else None
                    if match:
                        result["comments"] = int(match.group(1).replace(",", ""))
            except Exception:
                pass

        return result

    def _article_to_post(self, article: NewsArticle) -> Post:
        """NewsArticle → 统一 Post（仅用于完整文章抓取场景）"""
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

        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y年%m月%d日 %H:%M:%S",
            "%Y年%m月%d日 %H:%M",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
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
