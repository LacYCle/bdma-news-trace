"""微博爬虫 — 基于 Scrapling StealthySession

功能:
  - 按关键词搜索微博
  - 解析帖子内容、图片、互动数据
  - 获取转发链
  - 下载帖子图片

依赖:
  Scrapling StealthySession 提供:
    - 真实浏览器指纹模拟
    - Cloudflare Turnstile 自动绕过
    - 隐身请求头
    - 自适应选择器 (网站改版不中断)
"""

import os
import json
import hashlib
import re
from datetime import datetime
from typing import Optional

from scrapling.fetchers import StealthySession, StealthyFetcher

from .base import BaseScraper
from .cookie_manager import CookieManager
from ..storage.models import Post


class WeiboScraper(BaseScraper):
    """微博数据采集器"""

    SEARCH_URL = "https://s.weibo.com/weibo"
    REPOST_URL = "https://weibo.com/ajax/statuses/repostTimeline"

    def __init__(self, cookie_manager: Optional[CookieManager] = None,
                 adaptive_mode: bool = True, request_delay: float = 3.0,
                 max_retry: int = 3):
        super().__init__(adaptive_mode, request_delay, max_retry)
        self.cookie_manager = cookie_manager or CookieManager()
        self.session: Optional[StealthySession] = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.session:
            try:
                self.session.__exit__(None, None, None)
            except Exception:
                pass
        self.session = None

    def _ensure_session(self, cookies_list: Optional[list[dict]] = None):
        """创建 StealthySession 并进入 context manager"""
        if self.session is not None:
            return
        kwargs = dict(headless=True, solve_cloudflare=True)
        if cookies_list:
            kwargs["cookies"] = cookies_list
        session = StealthySession(**kwargs)
        session.__enter__()
        self.session = session

    # ========== 主接口 ==========

    def search_event(self, keyword: str, max_pages: int = 10) -> list[Post]:
        """按关键词搜索微博帖子

        Args:
            keyword: 搜索关键词
            max_pages: 最大翻页数 (每页约 20 条)
        Returns:
            帖子列表
        """
        posts: list[Post] = []
        cookie_entry = self.cookie_manager.get_next()
        if not cookie_entry:
            print("[Weibo] Cookie 池为空，尝试无登录搜索（可能受限）")
            cookies_list = None
        else:
            cookies_list = cookie_entry["cookies"]

        for page in range(1, max_pages + 1):
            print(f"[Weibo] 搜索 '{keyword}' 第 {page}/{max_pages} 页...")

            try:
                page_posts = self.execute_with_retry(
                    self._fetch_search_page,
                    keyword, page, cookies_list,
                    error_msg=f"搜索页 p{page}",
                )
                posts.extend(page_posts)
            except Exception:
                print(f"[Weibo] 第 {page} 页失败，跳过")
                self.close()  # 关闭异常会话，下次重试时重建
                continue

            self._delay()
            self.mark_first_run_complete()

        print(f"[Weibo] '{keyword}' 搜索完成, 共 {len(posts)} 条")
        return posts

    def get_repost_chain(self, post_id: str,
                         cookies_list: Optional[list[dict]] = None) -> list[Post]:
        """获取某条微博的转发链"""
        print(f"[Weibo] 获取转发链: {post_id}")
        try:
            reposts = self.execute_with_retry(
                self._fetch_repost_chain,
                post_id, cookies_list,
                error_msg=f"转发链 {post_id}",
            )
            return reposts
        except Exception:
            return []

    # ========== 内部实现 ==========

    def _fetch_search_page(self, keyword: str, page: int,
                           cookies_list: Optional[list[dict]]) -> list[Post]:
        """抓取并解析单页搜索结果"""
        url = f"{self.SEARCH_URL}?q={keyword}&page={page}"
        # 每次调用关闭旧会话重建，避免 "Context manager has been closed"
        self.close()
        self._ensure_session(cookies_list)
        page_content = self.session.fetch(url, google_search=False)

        cards = page_content.css(
            '.card-wrap, .m-wrap',
            **self._adaptive_kwargs("search_card"),
        )

        posts = []
        for card in cards:
            try:
                post = self._parse_search_card(card)
                if post:
                    posts.append(post)
            except Exception as e:
                print(f"[Weibo] 解析卡片失败: {e}")
                continue

        return posts

    def _parse_search_card(self, card) -> Optional[Post]:
        """解析单条搜索结果卡片"""
        from .selector_registry import SelectorRegistry
        sel = SelectorRegistry.SELECTORS["weibo"]

        # 文本
        text = ""
        for css in sel["post_text"]["css"].split(", "):
            t = card.css(css).get(default="")
            if t:
                text = t
                break

        if not text:
            return None

        # 图片
        image_urls = []
        for css in sel["post_images"]["css"].split(", "):
            urls = card.css(css).getall()
            image_urls.extend(urls)

        # 用户
        user_name = ""
        for css in sel["user_name"]["css"].split(", "):
            name = card.css(css).get(default="")
            if name:
                user_name = name.strip()
                break

        # 统计
        repost_count = self._parse_count(card, sel["repost_count"]["css"])
        comment_count = self._parse_count(card, sel["comment_count"]["css"])
        like_count = self._parse_count(card, sel["like_count"]["css"])

        # 时间
        time_str = ""
        for css in sel["timestamp"]["css"].split(", "):
            ts = card.css(css).get(default="")
            if ts and ts.strip():
                time_str = ts.strip()
                break

        timestamp = self._parse_weibo_time(time_str)

        # ID
        post_id = card.attrib.get("mid", "") if hasattr(card, "attrib") else ""
        if not post_id:
            post_id = hashlib.md5(text[:50].encode()).hexdigest()[:12]

        return Post(
            post_id=post_id,
            platform="weibo",
            post_type="original",
            text=text.strip(),
            image_urls=image_urls,
            author_name=user_name,
            timestamp=timestamp,
            repost_count=repost_count,
            comment_count=comment_count,
            like_count=like_count,
            engagement_count=repost_count + comment_count + like_count,
            url=f"https://weibo.com/{post_id}" if post_id else "",
        )

    def _parse_count(self, card, css: str) -> int:
        """解析互动计数（处理 '1.2万', '转赞人数超过3800' 等格式）"""
        import re
        text = card.css(css).get(default="0")
        if not text:
            return 0
        text = text.strip()
        # 只提取数字部分
        num_match = re.search(r'(\d[\d,.]*(?:万)?)', text)
        if num_match:
            num_str = num_match.group(1)
        else:
            return 0
        try:
            if "万" in num_str:
                return int(float(num_str.replace("万", "")) * 10000)
            return int(num_str.replace(",", ""))
        except ValueError:
            return 0

    def _parse_weibo_time(self, time_str: str) -> datetime:
        """解析微博时间格式"""
        from datetime import timedelta
        if not time_str:
            return datetime.now()
        time_str = time_str.strip()
        now = datetime.now()
        # 相对时间: "5分钟前", "2小时前", "昨天"
        if "分钟前" in time_str:
            mins = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(minutes=mins)
        if "小时前" in time_str:
            hours = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(hours=hours)
        if "昨天" in time_str:
            return now - timedelta(days=1)
        # 标准格式（带年份）
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y年%m月%d日 %H:%M", "%Y年%m月%d日"]:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        # 无年份格式: 补当前年份
        for fmt in ["%m月%d日 %H:%M", "%m月%d日", "%m-%d %H:%M", "%m-%d"]:
            try:
                dt = datetime.strptime(time_str, fmt)
                return dt.replace(year=now.year)
            except ValueError:
                continue
        return now

    def _fetch_repost_chain(self, post_id: str,
                            cookies_list: Optional[list[dict]]) -> list[Post]:
        """抓取转发链"""
        url = f"{self.REPOST_URL}?id={post_id}"
        self.close()
        self._ensure_session(cookies_list)
        page = self.session.fetch(url, google_search=False)

        repost_items = page.css(
            '.repost-item, [class*="repost"]',
            **self._adaptive_kwargs("repost_item"),
        )

        reposts = []
        for item in repost_items:
            text = item.css('.repost-text::text, [class*="text"]::text').get(default="")
            user = item.css('.repost-user::text, [class*="name"]::text').get(default="")
            if not user:
                similar = item.find_similar()
                if similar:
                    user = similar.css('[class*="name"]::text').get(default="")

            reposts.append(Post(
                post_id=f"repost_{post_id}_{len(reposts)}",
                platform="weibo",
                post_type="repost",
                text=text.strip(),
                author_name=user.strip(),
                parent_id=post_id,
                timestamp=datetime.now(),
            ))

        return reposts

    # ========== 辅助 ==========

    def download_images(self, post: Post, save_dir: str = "data/images/") -> list[str]:
        """下载帖子中的图片 — 使用 StealthyFetcher

        Returns:
            下载后的本地文件路径列表
        """
        os.makedirs(save_dir, exist_ok=True)
        local_paths = []

        for img_url in post.image_urls:
            try:
                response = StealthyFetcher.fetch(
                    img_url,
                    headless=True,
                )
                img_data = response.content
                filename = f"{post.post_id}_{hashlib.md5(img_url.encode()).hexdigest()[:8]}.jpg"
                filepath = os.path.join(save_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(img_data)
                local_paths.append(filepath)
                post.images.append(filepath)
            except Exception as e:
                print(f"[Weibo] 图片下载失败 {img_url[:60]}: {e}")

        return local_paths
