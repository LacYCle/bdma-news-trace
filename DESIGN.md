# 基于多源数据融合的新闻事件传播路径溯源与情感演化分析 — 系统设计文档

> Version: 1.0
> Date: 2026-05-25
> Course: 大数据分析与挖掘

---

## 1. 概述

### 1.1 项目背景

社交媒体时代，新闻事件的传播路径日益复杂：一条突发新闻从微博首发，被转发至知乎、被新闻网站引用、再被用户截图发回微博——信息在多平台间快速流动并不断变异。随之而来的是两个核心挑战：

1. **源头难辨**：同一事件在多个平台同时出现时，谁是首发？信息如何跨平台流动？
2. **情感演化**：一条中性新闻在传播过程中，公众情绪如何被放大、偏移甚至反转？

现有研究多聚焦单一平台（仅微博或仅 Twitter）的文本传播分析，缺乏**跨平台多源融合**和**多模态（文本+图像）联合建模**的视角。本系统构建一个融合实时爬虫、多模态特征提取、传播图建模与情感演化分析的完整框架。

### 1.2 系统目标

构建一个多源数据驱动的新闻传播分析系统，实现：

| 目标 | 描述 | 核心技术 |
|------|------|----------|
| **多源实时采集** | 从微博、新闻网站等平台实时采集新闻事件相关数据 | Scrapling 隐身模式、Cookie 池 |
| **多模态特征提取** | 对文本和图像进行联合特征提取与跨平台匹配 | Chinese-CLIP、感知哈希、OCR |
| **传播路径溯源** | 构建跨平台传播图，推断信息源头和传播路径 | 有向图建模、根节点定位 |
| **情感演化分析** | 追踪情感沿传播链的变化趋势 | Chinese-RoBERTa 细粒度情感 |
| **可视化呈现** | 交互式传播图谱与情感时间线 | Plotly、ECharts、NetworkX |

### 1.3 设计原则

- **多源融合**：微博（社交传播）+ 新闻网站（官方报道）+ 知乎（深度讨论）三源融合
- **多模态对齐**：文本传播链 + 图像指纹作为互补信号进行跨平台事件关联
- **实时 + 历史混合**：实时爬虫验证系统能力，历史公开数据集保证数据量
- **自适应采集**：基于 Scrapling 的 `adaptive` 机制，网站结构变化时自动重新定位目标元素，爬虫不会因目标平台改版而失效
- **单机可运行**：全系统在单台 PC（RTX 3060 级别 GPU）上可完整运行

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    数据采集层 (Data Layer — Scrapling)            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ 微博爬虫      │  │ 新闻爬虫      │  │ 公开数据集     │           │
│  │ StealthySess │  │ FetcherSess  │  │ FakeNewsNet  │           │
│  │ +adaptive    │  │ +impersonate │  │              │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                 │                    │
│         └─────────────────┼─────────────────┘                    │
│                           ▼                                      │
│              ┌───────────────────────┐                           │
│              │   数据存储 (SQLite + FS) │                           │
│              └───────────┬───────────┘                           │
├──────────────────────────┼───────────────────────────────────────┤
│                      特征提取层 (Feature Layer)                    │
│  ┌──────────────────┐    │    ┌──────────────────┐               │
│  │   文本特征        │    │    │   图像特征        │               │
│  │  · RoBERTa 768d  │◄───┼───►│  · CLIP 512d     │               │
│  │  · 细粒度情感 8d  │         │  · pHash 64d     │               │
│  │  · 语言特征 6d    │         │  · dHash 64d     │               │
│  │  · 命名实体 5d    │         │  · OCR 文本      │               │
│  └────────┬─────────┘         │  · 色彩情感 3d    │               │
│           │                   └────────┬─────────┘               │
│           └───────────┬───────────────┘                         │
│                       ▼                                          │
├──────────────────────────────────────────────────────────────────┤
│                      分析层 (Analysis Layer)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ 传播图构建    │  │ 源头溯源      │  │ 情感演化      │           │
│  │ · 有向图     │  │ · 根节点定位  │  │ · 路径情感曲线 │           │
│  │ · 跨平台边   │  │ · 图像指纹匹配│  │ · 情感转折点   │           │
│  │ · 时序标注   │  │ · 置信度排序  │  │ · 平台差异     │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         └─────────────────┼─────────────────┘                    │
│                           ▼                                      │
├──────────────────────────────────────────────────────────────────┤
│                    应用层 (Application Layer)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ 传播图谱可视化 │  │ 情感演化时间线 │  │ 溯源报告导出   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈概览

| 层级 | 技术选型 |
|------|----------|
| 爬虫框架 | **Scrapling** — 核心组件见下表 |
| 数据存储 | SQLite + 本地文件系统 |
| 文本特征 | HuggingFace Transformers (`bert-base-chinese`, `chinese-roberta-wwm-ext`) |
| 图像特征 | Chinese-CLIP (ViT-B/32), pHash/dHash, PaddleOCR |
| 图计算 | NetworkX |
| 深度学习 | PyTorch 2.x |
| 可视化 | Plotly, ECharts (pyecharts) |
| 配置管理 | Hydra (OmegaConf) |
| 实验追踪 | Weights & Biases (可选) |

**Scrapling 组件在本系统中的分工：**

| Scrapling 组件 | 本系统用途 | 关键参数 |
|----------------|-----------|----------|
| `StealthySession` | 微博/知乎爬虫主引擎 | `headless=True`, `solve_cloudflare=True` |
| `FetcherSession` | 新闻网站长连接采集 | `impersonate='chrome'` |
| `StealthyFetcher` | 单次隐身请求（图片下载等） | `headless=True` |
| `Fetcher` | 新闻 RSS/API 直连（无反爬） | — |
| `.css(..., adaptive=True)` | 所有解析逻辑 | `auto_save=True` 首次保存特征 |
| `.xpath(...)` | 复杂嵌套结构提取 | 回退方案 |
| `find_similar()` | 页面结构变化时定位元素 | 自适应容错 |
| Scrapling CLI | 快速原型验证、手动调试 | `scrapling extract stealthy-fetch` |

---

## 3. 数据层

### 3.1 数据源定义

#### 3.1.1 实时采集源

| 平台 | 数据类型 | 采集方式 | 更新频率 |
|------|----------|----------|----------|
| **微博** | 原帖、转发链、图片、时间戳、用户信息 | `StealthySession(solve_cloudflare=True, adaptive=True)` + Cookie 池 | 按事件关键词触发 |
| **新浪新闻** | 新闻正文、配图、发布时间、来源 | `FetcherSession(impersonate='chrome')` + `adaptive=True` | 按事件关键词触发 |
| **网易新闻** | 新闻正文、配图、评论 | `FetcherSession(impersonate='chrome')` + `adaptive=True` | 按事件关键词触发 |
| **知乎** | 问答、文章、图片 | `StealthySession(adaptive=True)` | 按需 |

#### 3.1.2 公开数据集补充

| 数据集 | 内容 | 用途 |
|--------|------|------|
| **FakeNewsNet** | Twitter + PolitiFact/GossipCop 新闻传播数据 | 历史传播图验证 |
| **Weibo-Fake-News** | 微博虚假新闻数据（含转发链） | 中文传播图基准 |
| **CHEF** | 中文突发事件数据集 | 情感演化基准 |

### 3.2 数据采集模块设计

#### 3.2.0 Scrapling CLI 快速原型

在编写完整爬虫代码前，可使用 Scrapling 命令行进行快速验证和手动调试：

```bash
# 快速抓取微博搜索结果（隐身模式 + 绕过 Cloudflare）
scrapling extract stealthy-fetch \
  'https://s.weibo.com/weibo?q=东方甄选事件' \
  weibo_preview.md \
  --solve-cloudflare

# 抓取新闻页面（指定 CSS 选择器）
scrapling extract get \
  'https://news.sina.com.cn/c/2025-05-25/doc-xxxxx.shtml' \
  article.txt \
  --css-selector '#article-content'

# 启动交互式 Shell 进行选择器调试
scrapling shell
```



#### 3.2.1 微博爬虫（基于 Scrapling StealthySession + 自适应选择器）

```python
from scrapling.fetchers import StealthySession, StealthyFetcher
from dataclasses import dataclass
from datetime import datetime

@dataclass
class WeiboPost:
    post_id: str
    user_id: str
    user_name: str
    text: str
    images: list[str]          # 图片 URL 列表
    repost_of: str | None      # 被转发帖 ID（None = 原帖）
    repost_chain: list[str]    # 完整转发链
    timestamp: datetime
    repost_count: int
    comment_count: int
    like_count: int

class WeiboScraper:
    """微博数据采集器 — 基于 Scrapling 隐身模式 + 自适应选择器

    Scrapling 关键特性利用：
    - StealthySession: 模拟真实浏览器指纹,绕过 Cloudflare
    - solve_cloudflare=True: 自动处理验证页面
    - adaptive=True: 页面结构变化时自动重新定位元素
    - auto_save=True: 首次采集时保存元素特征供后续自适应匹配
    """

    def __init__(self, cookie_file: str = "cookies/weibo.json",
                 adaptive_mode: bool = True):
        self.cookies = self._load_cookies(cookie_file)
        self.session = None
        self.adaptive_mode = adaptive_mode

    def _load_cookies(self, path: str) -> list[dict]:
        """加载预先手动登录导出的 Cookie"""
        import json
        with open(path) as f:
            return json.load(f)

    def __enter__(self):
        # headless=True: 无头模式省资源
        # solve_cloudflare=True: 自动绕过 CF 挑战页面
        self.session = StealthySession(
            headless=True,
            solve_cloudflare=True,
        )
        return self

    def __exit__(self, *args):
        if self.session:
            self.session.close()

    def search_event(self, keyword: str, max_pages: int = 10) -> list[WeiboPost]:
        """按关键词搜索相关微博"""
        posts = []
        first_page = True
        for page in range(1, max_pages + 1):
            url = f"https://s.weibo.com/weibo?q={keyword}&page={page}"

            # google_search=False 避免触发反爬检测
            page_content = self.session.get(
                url,
                cookies=self.cookies,
                stealthy_headers=True,
                google_search=False,
            )

            # Scrapling 自适应选择器:
            #   首次(auto_save=True) 保存元素特征
            #   后续(adaptive=True) 页面结构变了也能自动匹配
            cards = page_content.css(
                '.card-wrap',
                auto_save=first_page,
                adaptive=self.adaptive_mode,
            )
            first_page = False

            for card in cards:
                try:
                    post = self._parse_card(card)
                    if post:
                        posts.append(post)
                except Exception:
                    continue
        return posts

    def _parse_card(self, card) -> WeiboPost | None:
        """解析单条微博卡片 — 使用 Scrapling 多选择器风格"""

        # CSS 选择器（主方案）
        text = card.css('.txt::text').get()

        # XPath 回退（CSS 失败时可用）
        if not text:
            text = card.xpath('.//p[@class="txt"]/text()').get()

        # 图片提取 — Scrapling 支持链式调用
        images = card.css('.media').css('img::attr(src)').getall()

        # 用户信息
        user_name = card.css('.name::text').get(default='')

        # 互动数据提取
        repost_count = int(card.css('.repost-count::text').get(default='0'))
        comment_count = int(card.css('.comment-count::text').get(default='0'))

        # find_by_text 定位包含特定文字的元素
        like_el = card.find_by_text('赞', tag='span')
        like_count = int(like_el.css('em::text').get(default='0')) if like_el else 0

        # 时间戳
        time_str = card.css('.from a::text').get()
        if not time_str:
            return None

        return WeiboPost(
            post_id=card.attrib.get('mid', ''),
            user_id='',
            user_name=user_name,
            text=text,
            images=images,
            repost_of=None,
            repost_chain=[],
            timestamp=datetime.strptime(time_str, '%Y-%m-%d %H:%M'),
            repost_count=repost_count,
            comment_count=comment_count,
            like_count=like_count,
        )

    def get_repost_chain(self, post_id: str) -> list[WeiboPost]:
        """获取某条微博的完整转发链"""
        url = f"https://weibo.com/{post_id}/repost"
        page = self.session.get(
            url, cookies=self.cookies,
            stealthy_headers=True, google_search=False,
        )

        # adaptive=True: 即使微博前端改版也能定位到转发列表
        repost_items = page.css('.repost-item', adaptive=True)
        return self._parse_repost_items(repost_items)

    def _parse_repost_items(self, items) -> list[WeiboPost]:
        """解析转发链 — 使用 Scrapling 元素导航"""
        reposts = []
        for item in items:
            text = item.css('.repost-text::text').get()
            user = item.css('.repost-user::text').get()

            # find_similar(): 页面结构微调后自动匹配相近元素
            if not user:
                similar = item.find_similar()
                if similar:
                    user = similar.css('.repost-user::text').get()

            reposts.append(WeiboPost(
                post_id='', user_id='', user_name=user,
                text=text, images=[], repost_of=None,
                repost_chain=[], timestamp=datetime.now(),
                repost_count=0, comment_count=0, like_count=0,
            ))
        return reposts

    def download_images(self, post: WeiboPost, save_dir: str) -> list[str]:
        """下载帖子中的图片 — 使用 StealthyFetcher（单次隐身请求）"""
        local_paths = []
        for img_url in post.images:
            try:
                # StealthyFetcher：不需要完整 session 的轻量隐身请求
                # 适合图片下载等一次性操作
                response = StealthyFetcher.fetch(img_url, headless=True)
                img_data = response.content  # 原始字节
                filename = f"{post.post_id}_{hashlib.md5(img_url.encode()).hexdigest()[:8]}.jpg"
                filepath = f"{save_dir}/{filename}"
                with open(filepath, 'wb') as f:
                    f.write(img_data)
                local_paths.append(filepath)
            except Exception:
                continue
        return local_paths
```

#### 3.2.2 新闻网站爬虫（基于 Scrapling FetcherSession + TLS 指纹）

```python
from scrapling.fetchers import Fetcher, FetcherSession
import hashlib

@dataclass
class NewsArticle:
    article_id: str
    title: str
    content: str
    images: list[str]
    source: str                 # 来源媒体名称
    url: str
    publish_time: datetime
    category: str               # 新闻分类

class NewsScraper:
    """多源新闻采集器

    Scrapling 关键特性利用：
    - FetcherSession(impersonate='chrome'): 模拟 Chrome TLS 指纹，
      避免被新闻网站的 CDN 识别为爬虫
    - adaptive=True: 新闻网站改版时自动适应新选择器
    - Fetcher.get: 直接请求 RSS/API（无反爬保护）
    """

    SOURCES = {
        "sina": {
            "rss": "https://feed.mix.sina.com.cn/api/roll/get",
            "base": "https://news.sina.com.cn",
        },
        "netease": {
            "rss": "https://news.163.com/special/xxxx/",
            "base": "https://news.163.com",
        },
    }

    def __init__(self, adaptive_mode: bool = True):
        self.adaptive_mode = adaptive_mode
        # FetcherSession: 长连接会话,模拟 Chrome 指纹
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = FetcherSession(impersonate='chrome')
        return self._session

    def close(self):
        if self._session:
            self._session.close()
            self._session = None

    def fetch_by_keyword(self, keyword: str, source: str = "sina",
                         max_articles: int = 50) -> list[NewsArticle]:
        """按关键词拉取新闻 — RSS 接口直接 Fetcher.get"""
        articles = []
        rss_url = self.SOURCES[source]["rss"]

        # RSS 接口通常无反爬，用 Fetcher 直接拿（比 FetcherSession 更轻）
        feed = Fetcher.get(
            f"{rss_url}?q={keyword}&count={max_articles}",
            stealthy_headers=True,
        )

        # 自适应选择器定位新闻列表项
        news_items = feed.css('.news-item', adaptive=self.adaptive_mode)[:max_articles]

        for item in news_items:
            link = item.css('a::attr(href)').get()
            if link:
                article = self._fetch_article(link, source)
                if article:
                    articles.append(article)
        return articles

    def _fetch_article(self, url: str, source: str) -> NewsArticle | None:
        """抓取单篇新闻正文 — FetcherSession 模拟 Chrome"""
        try:
            # 使用 FetcherSession 模拟真实浏览器 TLS 指纹
            page = self.session.get(url, stealthy_headers=True)

            # 自适应选择器: 首次(auto_save)保存特征，后续(adaptive)自动适应
            title = page.css('h1::text', adaptive=True).get()
            content_paras = page.css(
                '#article-content p::text',
                auto_save=True,
                adaptive=self.adaptive_mode,
            ).getall()
            content = '\n'.join(content_paras)
            images = page.css(
                '#article-content img::attr(src)',
                adaptive=self.adaptive_mode,
            ).getall()

            # XPath 回退方案
            if not title:
                title = page.xpath('//h1/text()').get()
            if not content:
                content = '\n'.join(
                    page.xpath('//div[contains(@class,"article")]//p/text()').getall()
                )

            time_str = page.css('.pub-time::text', adaptive=True).get()

            raw_id = f"{source}:{url}"
            article_id = hashlib.md5(raw_id.encode()).hexdigest()[:12]

            return NewsArticle(
                article_id=article_id,
                title=title or '',
                content=content,
                images=images,
                source=source,
                url=url,
                publish_time=datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                    if time_str else datetime.now(),
                category='',
            )
        except Exception:
            return None

    def fetch_headlines(self, source: str = "sina") -> list[dict]:
        """快速拉取新闻头条列表（用于事件发现）"""
        base = self.SOURCES[source]["base"]
        page = self.session.get(base, stealthy_headers=True)

        headlines = []
        for item in page.css('.news-item, .feed-card', adaptive=True):
            title = item.css('a::text').get()
            link = item.css('a::attr(href)').get()
            if title and link:
                headlines.append({"title": title, "url": link, "source": source})
        return headlines
```

#### 3.2.3 Cookie 管理与 Scrapling 反爬策略

```python
class CookieManager:
    """多账号 Cookie 池管理 — 与 Scrapling Session 协同"""

    def __init__(self, cookie_dir: str = "cookies/"):
        self.pool: list[dict] = []
        self._load_all(cookie_dir)

    def _load_all(self, dir_path: str):
        """加载所有预先导出的 Cookie 文件"""
        import json, glob
        for f in glob.glob(f"{dir_path}/*.json"):
            with open(f) as fp:
                self.pool.append(json.load(fp))

    def get_next(self) -> dict:
        """轮询获取下一个可用 Cookie"""
        cookie = self.pool.pop(0)
        self.pool.append(cookie)
        return cookie

    def mark_expired(self, cookie: dict):
        """标记失效 Cookie 并从池中移除"""
        if cookie in self.pool:
            self.pool.remove(cookie)

    def refresh_pool(self):
        """Cookie 批量过期时触发手动重新登录提醒"""
        if len(self.pool) < 2:
            print("[WARN] Cookie 池不足 2 个账号，请重新登录微博导出 Cookie")
            print("[TIP] 使用 browser-cookie3 或 EditThisCookie 插件导出")


# ============================================================
# Scrapling 反爬策略分层架构
# ============================================================

"""
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Scrapling 自动反爬                              │
│  ─────────────────────────────────────                   │
│  · StealthySession(headless=True)                        │
│    - 模拟真实浏览器指纹 (WebGL, Canvas, 字体枚举)         │
│    - 注入 stealth.js 隐藏自动化特征                       │
│  · solve_cloudflare=True                                 │
│    - 自动检测并绕过 Cloudflare Turnstile 验证             │
│  · stealthy_headers=True                                 │
│    - 使用真实浏览器请求头 (Accept-Language, Sec-* 等)     │
│  · google_search=False                                   │
│    - 不通过 Google 搜索跳转，避免来源追踪                 │
│  · impersonate='chrome' (FetcherSession)                 │
│    - TLS 握手指纹与 Chrome 一致                           │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Cookie + 频控 + 自适应                          │
│  ─────────────────────────────────────                   │
│  · Cookie 池轮询 (多账号分担请求量)                       │
│  · adaptive=True 选择器 (页面改版不中断采集)              │
│  · auto_save=True 元素指纹 (首次保存，后续自动匹配)       │
│  · 请求间隔 3-5 秒 + 指数退避重试                        │
│  · 已抓取内容本地缓存 24 小时 (避免重复请求)              │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 3: 退化策略                                       │
│  ─────────────────────────────────────                   │
│  · 微博爬取失败 → 切换至公开数据集                        │
│  · FetcherSession 被限 → 降级为 Fetcher (直连)          │
│  · 新闻网站改版 → find_similar() 自动匹配                │
│  · Cookie 全失效 → 发送重新登录提醒                       │
└─────────────────────────────────────────────────────────┘
"""

class ScraplingRetryHandler:
    """Scrapling 请求重试与退化处理"""

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    def execute_with_retry(self, fetch_fn, *args, **kwargs):
        """指数退避重试包装器"""
        import time
        for attempt in range(self.max_retries):
            try:
                return fetch_fn(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                delay = self.base_delay * (2 ** attempt)
                print(f"[RETRY] 第 {attempt+1} 次重试, 等待 {delay:.0f}s: {e}")
                time.sleep(delay)
```

#### 3.2.4 Scrapling 自适应选择器配置

Scrapling 的 `adaptive` 机制是本系统爬虫稳健性的核心保障。它通过以下流程实现"页面结构改变后自动重新定位元素"：

```
首次采集 (auto_save=True)
    │
    ▼
┌──────────────────────────────┐
│ 1. 定位目标元素               │
│ 2. 提取元素的"指纹特征":       │
│    - 标签名、class、id        │
│    - 文本内容摘要              │
│    - 父子层级关系              │
│    - 相邻兄弟元素特征          │
│ 3. 保存至 .scrapling/ 目录   │
└──────────┬───────────────────┘
           │
           ▼  网站改版后
┌──────────────────────────────┐
│ 后续采集 (adaptive=True)     │
│ 1. 先用保存的 CSS 选择器尝试  │
│ 2. 定位失败 → 用指纹匹配      │
│ 3. 匹配成功 → 更新选择器缓存  │
│ 4. 匹配失败 → find_similar() │
│ 5. 全部失败 → 回退到 XPath    │
└──────────────────────────────┘
```

```python
class ScraplingAdaptiveConfig:
    """Scrapling 自适应机制的系统级配置

    所有爬虫类统一通过以下模式使用自适应选择器：
    """

    @staticmethod
    def configure_first_run():
        """首次运行：保存所有目标元素特征"""
        return {"auto_save": True, "adaptive": False}

    @staticmethod
    def configure_subsequent():
        """后续运行：启用自适应匹配"""
        return {"adaptive": True}

    # 使用示例（集成到各爬虫中）:
    #
    # # 微博搜索结果卡片
    # cards = page.css('.card-wrap', auto_save=is_first_run, adaptive=not is_first_run)
    #
    # # 新闻文章内容
    # content = page.css('#article-content p::text', adaptive=True)
    #
    # # find_similar() 兜底:
    # if not content:
    #     similar_section = page.css('#article-content').find_similar()
    #     if similar_section:
    #         content = similar_section.css('p::text').getall()


class ScraplingSelectorRegistry:
    """Scrapling 多平台选择器注册表

    集中管理所有目标平台的选择器，
    每个平台维护 CSS 主方案 + XPath 回退方案。
    """

    SELECTORS = {
        "weibo": {
            "search_card": {
                "css": ".card-wrap",
                "xpath": '//div[contains(@class,"card")]',
            },
            "post_text": {
                "css": ".txt::text, .WB_text::text",
                "xpath": './/div[contains(@class,"WB_text")]/text()',
            },
            "post_images": {
                "css": ".media img::attr(src), .WB_media_a img::attr(src)",
                "xpath": './/img[contains(@class,"media")]/@src',
            },
            "repost_item": {
                "css": ".repost-item, .comment-list .item",
                "xpath": '//div[contains(@class,"repost")]',
            },
        },
        "sina_news": {
            "article_title": {
                "css": "h1::text, .article-title::text",
                "xpath": '//h1/text()',
            },
            "article_content": {
                "css": "#article-content p::text, #artibody p::text",
                "xpath": '//div[@id="artibody"]//p/text()',
            },
            "article_images": {
                "css": "#article-content img::attr(src)",
                "xpath": '//div[@id="artibody"]//img/@src',
            },
        },
        "netease_news": {
            "article_title": {
                "css": "h1::text, .post_title::text",
                "xpath": '//h1/text()',
            },
            "article_content": {
                "css": ".post_content p::text, #content p::text",
                "xpath": '//div[@class="post_content"]//p/text()',
            },
        },
    }

    @classmethod
    def get_css(cls, platform: str, element: str) -> str:
        return cls.SELECTORS[platform][element]["css"]

    @classmethod
    def get_xpath(cls, platform: str, element: str) -> str:
        return cls.SELECTORS[platform][element]["xpath"]
```

### 3.4 数据存储方案

```sql
-- 统一存储所有平台的帖子/文章
CREATE TABLE posts (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,           -- 'weibo', 'sina', 'netease', 'zhihu'
    post_type TEXT NOT NULL,          -- 'original', 'repost', 'article'
    text TEXT NOT NULL,
    images TEXT,                      -- JSON array of image paths
    author_id TEXT,
    author_name TEXT,
    parent_id TEXT,                   -- 被转发/引用的帖子 ID
    event_id TEXT,                    -- 所属新闻事件 ID
    timestamp DATETIME NOT NULL,
    engagement_count INTEGER DEFAULT 0,
    metadata TEXT                     -- JSON: 平台特定字段
);

CREATE TABLE images (
    id TEXT PRIMARY KEY,
    post_id TEXT REFERENCES posts(id),
    local_path TEXT NOT NULL,
    url TEXT,
    phash TEXT,                       -- 64-bit 感知哈希
    dhash TEXT,                       -- 64-bit 差异哈希
    clip_embedding BLOB,              -- 512-dim float32
    ocr_text TEXT,
    width INTEGER,
    height INTEGER,
    file_size INTEGER
);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    keywords TEXT,                    -- JSON: 事件关键词列表
    first_seen DATETIME,
    last_updated DATETIME,
    post_count INTEGER DEFAULT 0,
    source_candidates TEXT            -- JSON: 候选源头列表
);

CREATE TABLE propagation_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT REFERENCES posts(id),
    target_id TEXT REFERENCES posts(id),
    edge_type TEXT NOT NULL,          -- 'repost', 'cite', 'image_match'
    confidence REAL DEFAULT 1.0,      -- 边置信度 (0-1)
    timestamp_diff INTEGER,           -- 两端时间差（秒）
    metadata TEXT
);

CREATE TABLE sentiment_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT REFERENCES posts(id),
    sentiment_label TEXT,             -- 'anger','sadness','surprise','joy','fear','disgust','neutral'
    sentiment_score REAL,             -- -1 (负面) 到 +1 (正面)
    arousal_score REAL,               -- 情感唤起度 (0-1)
    model_version TEXT
);
```

### 3.5 事件发现与追踪

```python
class EventTracker:
    """新闻事件发现与追踪管理"""

    def __init__(self, db_path: str = "data/news_trace.db"):
        self.db = sqlite3.connect(db_path)
        self.scrapers = {}

    def discover_event(self, keyword: str) -> str:
        """发现新事件或匹配已有事件（按关键词 + 时间窗口聚合）"""
        # 1. 检查是否已有相近关键词的事件
        existing = self.db.execute(
            "SELECT id, keywords FROM events WHERE json_extract(keywords, '$[0]') LIKE ?",
            (f"%{keyword}%",)
        ).fetchone()

        if existing:
            return existing[0]

        # 2. 新建事件
        event_id = f"event_{int(time.time())}_{hashlib.md5(keyword.encode()).hexdigest()[:8]}"
        self.db.execute(
            "INSERT INTO events (id, name, keywords, first_seen) VALUES (?, ?, ?, ?)",
            (event_id, keyword, json.dumps([keyword]), datetime.now())
        )
        self.db.commit()
        return event_id

    def crawl_event(self, event_id: str):
        """对指定事件触发全平台采集"""
        event = self.db.execute(
            "SELECT keywords FROM events WHERE id=?", (event_id,)
        ).fetchone()
        keywords = json.loads(event[0])

        all_posts = []

        # 微博搜索
        with WeiboScraper() as weibo:
            for kw in keywords:
                posts = weibo.search_event(kw, max_pages=5)
                all_posts.extend(posts)

        # 新闻网站搜索
        news = NewsScraper()
        for kw in keywords:
            for source in ["sina", "netease"]:
                articles = news.fetch_by_keyword(kw, source=source)
                # NewsArticle → 统一 Post 格式
                all_posts.extend(self._articles_to_posts(articles, source))

        # 保存至数据库
        self._save_posts(all_posts, event_id)
        return all_posts

    def _articles_to_posts(self, articles: list, source: str) -> list:
        """新闻文章转为统一的 Post 格式"""
        # ... 转换逻辑
        pass

    def _save_posts(self, posts: list, event_id: str):
        """批量保存帖子并更新事件统计"""
        for post in posts:
            self.db.execute(
                """INSERT OR IGNORE INTO posts
                   (id, platform, post_type, text, images, author_name,
                    parent_id, event_id, timestamp, engagement_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (post.post_id, post.platform, post.post_type, post.text,
                 json.dumps(post.images), post.author_name, post.parent_id,
                 event_id, post.timestamp, post.engagement_count)
            )
        self.db.commit()
```

---

## 4. 特征层

### 4.1 文本特征提取

#### 4.1.1 语义编码

```python
import torch
from transformers import AutoTokenizer, AutoModel
import numpy as np

class TextEncoder:
    """中文文本语义编码器"""

    def __init__(self, model_name: str = "hfl/chinese-roberta-wwm-ext",
                 device: str = "cuda"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(device)
        self.device = device
        self.model.eval()

    @torch.no_grad()
    def encode(self, text: str) -> np.ndarray:
        """提取 CLS 嵌入 (768-dim)"""
        inputs = self.tokenizer(
            text, max_length=256, padding=True,
            truncation=True, return_tensors="pt"
        ).to(self.device)
        outputs = self.model(**inputs)
        return outputs.last_hidden_state[:, 0, :].cpu().numpy().squeeze()  # (768,)

    @torch.no_grad()
    def encode_batch(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """批量编码"""
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            emb = self.encode_batch_raw(batch)
            embeddings.append(emb)
        return np.vstack(embeddings)
```

#### 4.1.2 细粒度情感分析

```python
class ChineseSentimentAnalyzer:
    """中文细粒度情感分析器

    基于 bert-base-chinese 微调的情感分类模型，
    支持 7 类情感 + 情感强度打分。
    """

    EMOTION_LABELS = ["愤怒", "悲伤", "惊讶", "喜悦",
                      "恐惧", "厌恶", "中性"]
    # 情感极性映射
    POLARITY_MAP = {
        "愤怒": -0.8, "悲伤": -0.6, "惊讶": 0.1,
        "喜悦": 0.9, "恐惧": -0.4, "厌恶": -0.7,
        "中性": 0.0,
    }

    def __init__(self,
                 model_name: str = "uer/roberta-base-finetuned-jd-binary-chinese",
                 device: str = "cuda"):
        from transformers import pipeline
        self.classifier = pipeline(
            "text-classification",
            model=model_name,
            device=0 if device == "cuda" else -1,
            top_k=None,
        )

    def analyze(self, text: str) -> dict:
        """返回细粒度情感分析结果"""
        # 使用多标签情感模型
        results = self.classifier(text[:512])

        emotions = {}
        for r in results:
            label = r["label"]
            # 映射英文标签到中文
            if label in self.EMOTION_LABELS or True:
                emotions[label] = r["score"]

        # 计算加权情感极性
        polarity = sum(
            emotions.get(label, 0) * self.POLARITY_MAP.get(label, 0)
            for label in self.EMOTION_LABELS
        )

        # 情感唤起度（情绪强度）
        arousal = max(emotions.values()) if emotions else 0.0

        return {
            "emotions": emotions,
            "polarity": float(polarity),    # -1 到 +1
            "arousal": float(arousal),      # 0 到 1
            "dominant": max(emotions, key=emotions.get) if emotions else "中性",
        }
```

#### 4.1.3 文本统计特征

```python
class TextStatistics:
    """文本语言学统计特征"""

    def extract(self, text: str) -> dict:
        return {
            "char_count": len(text),
            "sentence_count": text.count("。") + text.count("！") + text.count("？"),
            "avg_sentence_len": len(text) / max(text.count("。") + text.count("！") + text.count("？"), 1),
            "exclamation_ratio": text.count("！") / max(len(text), 1),
            "question_ratio": text.count("？") / max(len(text), 1),
            "has_hashtag": 1.0 if "#" in text else 0.0,
            "has_mention": 1.0 if "@" in text else 0.0,
            "url_count": min(text.count("http"), 5) / 5.0,
        }
```

#### 4.1.4 文本特征汇总

```python
class TextFeatureExtractor:
    """文本特征统一提取器"""

    def __init__(self, device: str = "cuda"):
        self.encoder = TextEncoder(device=device)
        self.sentiment = ChineseSentimentAnalyzer(device=device)
        self.stats = TextStatistics()

    def extract(self, text: str) -> np.ndarray:
        """提取完整文本特征向量 (~787-dim)"""
        semantic = self.encoder.encode(text)                    # 768

        sent_result = self.sentiment.analyze(text)
        sentiment_vec = np.array([
            sent_result["polarity"],                            # 1
            sent_result["arousal"],                             # 1
            sent_result["emotions"].get("愤怒", 0),              # 1
            sent_result["emotions"].get("喜悦", 0),              # 1
            sent_result["emotions"].get("悲伤", 0),              # 1
            sent_result["emotions"].get("惊讶", 0),              # 1
            sent_result["emotions"].get("恐惧", 0),              # 1
            sent_result["emotions"].get("厌恶", 0),              # 1
        ])                                                      # 8

        stats = self.stats.extract(text)
        stats_vec = np.array(list(stats.values()))              # 8

        return np.concatenate([semantic, sentiment_vec,
                               stats_vec])                      # 784
```

### 4.2 图像特征提取

#### 4.2.1 Chinese-CLIP 语义嵌入

```python
import clip
from PIL import Image

class CLIPImageEncoder:
    """基于 Chinese-CLIP 的图像语义编码器"""

    def __init__(self,
                 model_name: str = "OFA-Sys/chinese-clip-vit-base-patch16",
                 device: str = "cuda"):
        self.model, self.preprocess = clip.load(
            "ViT-B/32", device=device
        )  # Chinese-CLIP 兼容 OpenAI CLIP API
        self.device = device

    @torch.no_grad()
    def encode(self, image: Image.Image) -> np.ndarray:
        """提取 CLIP 图像嵌入 (512-dim)"""
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)
        features = self.model.encode_image(image_input)
        return features.cpu().numpy().squeeze()  # (512,)

    @torch.no_grad()
    def similarity(self, img1: Image.Image, img2: Image.Image) -> float:
        """两张图像的 CLIP 语义相似度"""
        f1 = self.encode(img1)
        f2 = self.encode(img2)
        return float(np.dot(f1, f2) / (np.linalg.norm(f1) * np.linalg.norm(f2)))
```

#### 4.2.2 感知哈希（跨平台图像指纹）

```python
import cv2
import numpy as np

class ImageHasher:
    """感知哈希 — 用于跨平台图像重复/近似检测"""

    @staticmethod
    def phash(image: Image.Image, hash_size: int = 8) -> str:
        """感知哈希 (pHash): 基于 DCT 变换，对缩放/压缩鲁棒"""
        img = np.array(image.convert("L"), dtype=np.float32)
        # 缩放到 32x32
        img = cv2.resize(img, (32, 32))
        # DCT 变换
        dct = cv2.dct(img)
        # 取左上角低频部分
        dct_low = dct[:hash_size, :hash_size]
        # 以均值二值化
        mean = dct_low.mean()
        hash_bits = (dct_low > mean).flatten()
        return ''.join(['1' if b else '0' for b in hash_bits])

    @staticmethod
    def dhash(image: Image.Image, hash_size: int = 8) -> str:
        """差异哈希 (dHash): 基于相邻像素梯度，对亮度变化鲁棒"""
        img = np.array(image.convert("L"), dtype=np.float32)
        img = cv2.resize(img, (hash_size + 1, hash_size))
        # 水平方向相邻像素差值
        diff = img[:, 1:] > img[:, :-1]
        return ''.join(['1' if b else '0' for b in diff.flatten()])

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """汉明距离 — 越小越相似"""
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

    def is_same_image(self, img1: Image.Image, img2: Image.Image,
                      threshold: int = 10) -> bool:
        """判断两张图是否为同一张（允许裁剪/压缩/水印差异）"""
        ph1, ph2 = self.phash(img1), self.phash(img2)
        return self.hamming_distance(ph1, ph2) <= threshold
```

#### 4.2.3 OCR 文字提取

```python
class ImageOCR:
    """图像文字提取 — 用于截图等场景的文字信息提取"""

    def __init__(self, use_gpu: bool = True):
        from paddleocr import PaddleOCR
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang='ch',
            use_gpu=use_gpu,
        )

    def extract_text(self, image: Image.Image) -> str:
        """提取图像中所有文字"""
        img_array = np.array(image)
        results = self.ocr.ocr(img_array, cls=True)
        if not results or not results[0]:
            return ""
        texts = []
        for line in results[0]:
            if line and len(line) >= 2:
                texts.append(line[1][0])  # (bbox, (text, confidence))
        return ' '.join(texts)

    def extract_text_with_confidence(self, image: Image.Image) -> list[tuple[str, float]]:
        """提取文字并保留置信度"""
        img_array = np.array(image)
        results = self.ocr.ocr(img_array, cls=True)
        if not results or not results[0]:
            return []
        return [(line[1][0], line[1][1]) for line in results[0] if line]
```

#### 4.2.4 图像情感色彩

```python
class ImageColorSentiment:
    """基于色彩统计的图像情感倾向"""

    def extract(self, image: Image.Image) -> np.ndarray:
        """提取色彩情感特征 (3-dim)"""
        img = np.array(image.convert("RGB"))
        # HSV 色彩空间
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        # 暖色调占比 (H: 0-30 红, 150-180 品红)
        warm_mask = ((hsv[:, :, 0] < 30) | (hsv[:, :, 0] > 150))
        warm_ratio = warm_mask.mean()

        # 平均饱和度和亮度
        avg_saturation = hsv[:, :, 1].mean() / 255.0
        avg_brightness = hsv[:, :, 2].mean() / 255.0

        return np.array([warm_ratio, avg_saturation, avg_brightness])  # (3,)
```

#### 4.2.5 图像特征汇总

```python
class ImageFeatureExtractor:
    """图像特征统一提取器 — 输出 ~643-dim"""

    def __init__(self, device: str = "cuda"):
        self.clip_encoder = CLIPImageEncoder(device=device)
        self.hasher = ImageHasher()
        self.ocr = ImageOCR(use_gpu=(device == "cuda"))
        self.color = ImageColorSentiment()

    def extract(self, image: Image.Image) -> dict:
        """提取完整图像特征"""
        return {
            "clip_embedding": self.clip_encoder.encode(image),       # (512,)
            "phash": self.hasher.phash(image),                       # str
            "dhash": self.hasher.dhash(image),                       # str
            "ocr_text": self.ocr.extract_text(image),                # str
            "color_features": self.color.extract(image),             # (3,)
        }

    def extract_vector(self, image: Image.Image) -> np.ndarray:
        """提取为数值向量 (用于模型输入)"""
        features = self.extract(image)
        # 将感知哈希转为位向量
        phash_vec = np.array([int(b) for b in features["phash"]])   # (64,)
        dhash_vec = np.array([int(b) for b in features["dhash"]])   # (64,)
        return np.concatenate([
            features["clip_embedding"],     # 512
            features["color_features"],     # 3
            phash_vec,                      # 64
            dhash_vec,                      # 64
        ])                                   # 643
```

### 4.3 跨平台多模态关联

```python
class CrossPlatformMatcher:
    """跨平台内容匹配器

    利用文本语义 + 图像指纹 + OCR 三维度进行跨平台关联。
    用于发现不同平台上对同一新闻事件的报道/帖子。
    """

    def __init__(self):
        self.text_encoder = TextEncoder()
        self.img_encoder = CLIPImageEncoder()
        self.img_hasher = ImageHasher()

    def match_posts(self, post_a: dict, post_b: dict) -> float:
        """
        计算两个帖子属于同一事件的综合置信度。
        post_a, post_b 包含 'text', 'images' 字段。

        Returns:
            float: 0-1 匹配置信度
        """
        scores = []

        # 1. 文本语义相似度
        if post_a.get("text") and post_b.get("text"):
            emb_a = self.text_encoder.encode(post_a["text"][:256])
            emb_b = self.text_encoder.encode(post_b["text"][:256])
            text_sim = float(np.dot(emb_a, emb_b) /
                            (np.linalg.norm(emb_a) * np.linalg.norm(emb_b)))
            scores.append(("text", text_sim, 0.5))  # 权重 0.5

        # 2. 图像感知哈希匹配（同一张图在不同平台）
        img_sims = []
        for img_a_path in post_a.get("images", [])[:5]:
            img_a = Image.open(img_a_path)
            for img_b_path in post_b.get("images", [])[:5]:
                img_b = Image.open(img_b_path)
                if self.img_hasher.is_same_image(img_a, img_b, threshold=8):
                    img_sims.append(1.0)
                else:
                    # CLIP 语义相似度
                    clip_sim = self.img_encoder.similarity(img_a, img_b)
                    img_sims.append(max(0, clip_sim))

        if img_sims:
            scores.append(("image", max(img_sims), 0.35))  # 权重 0.35

        # 3. 时间窗口得分（越近越高）
        time_a = post_a.get("timestamp")
        time_b = post_b.get("timestamp")
        if time_a and time_b:
            diff_hours = abs((time_a - time_b).total_seconds()) / 3600
            time_score = max(0, 1.0 - diff_hours / 24)  # 24小时内线性衰减
            scores.append(("time", time_score, 0.15))

        # 加权综合
        if not scores:
            return 0.0

        total_weight = sum(w for _, _, w in scores)
        weighted_score = sum(s * w for _, s, w in scores) / total_weight
        return float(weighted_score)
```

---

## 5. 分析层

### 5.1 传播图构建

#### 5.1.1 图数据结构

```python
import networkx as nx
from dataclasses import field

@dataclass
class PropagationGraph:
    """新闻事件传播图"""
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    event_id: str = ""
    root_candidates: list[str] = field(default_factory=list)

    def add_post_node(self, post: dict):
        """添加帖子/文章节点"""
        self.graph.add_node(
            post["id"],
            type=post.get("platform", "unknown"),
            text=post.get("text", "")[:100],
            timestamp=post.get("timestamp"),
            sentiment=post.get("sentiment"),
            author=post.get("author_name", ""),
            engagement=post.get("engagement_count", 0),
        )

    def add_edge(self, source_id: str, target_id: str,
                 edge_type: str, confidence: float = 1.0):
        """添加传播边"""
        self.graph.add_edge(
            source_id, target_id,
            type=edge_type,         # 'repost', 'cite', 'image_match'
            confidence=confidence,
        )
```

#### 5.1.2 图构建流程

```python
class PropagationGraphBuilder:
    """传播图构建器"""

    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.matcher = CrossPlatformMatcher()

    def build(self, event_id: str) -> PropagationGraph:
        """为指定事件构建完整传播图"""
        pg = PropagationGraph(event_id=event_id)

        # Step 1: 加载所有相关帖子
        posts = self._load_event_posts(event_id)
        for post in posts:
            pg.add_post_node(post)

        # Step 2: 添加平台内边（转发链 / 引用链）
        self._add_intra_platform_edges(pg, posts)

        # Step 3: 添加跨平台边（基于多模态内容匹配）
        self._add_cross_platform_edges(pg, posts)

        # Step 4: 时序验证 — 移除不合理的边（目标时间早于源）
        self._validate_temporal_consistency(pg)

        return pg

    def _load_event_posts(self, event_id: str) -> list[dict]:
        """加载事件相关的所有帖子"""
        rows = self.db.execute(
            "SELECT * FROM posts WHERE event_id=? ORDER BY timestamp",
            (event_id,)
        ).fetchall()
        return [dict(zip([c[0] for c in self.db.execute(
            "PRAGMA table_info(posts)")], row)) for row in rows]

    def _add_intra_platform_edges(self, pg: PropagationGraph, posts: list[dict]):
        """添加平台内传播边

        - 微博：通过 repost_of 字段构建转发链
        - 新闻网站：通过转载声明匹配
        """
        post_map = {p["id"]: p for p in posts}

        for post in posts:
            # 微博转发边
            parent_id = post.get("parent_id")
            if parent_id and parent_id in post_map:
                pg.add_edge(parent_id, post["id"], edge_type="repost")

            # 新闻引用边（基于文本相似度 + 时间先后）
            if post["platform"] in ("sina", "netease"):
                for other in posts:
                    if other["id"] == post["id"]:
                        continue
                    if other["timestamp"] < post["timestamp"]:
                        # 简单规则：文本相似度 > 0.3 认为存在引用
                        sim = self.matcher.match_posts(post, other)
                        if sim > 0.3:
                            pg.add_edge(other["id"], post["id"],
                                       edge_type="cite", confidence=sim)

    def _add_cross_platform_edges(self, pg: PropagationGraph, posts: list[dict]):
        """添加跨平台传播边

        通过多模态匹配发现跨平台的信息流动：
        - 同一张图片出现在不同平台 → image_match 边
        - 高文本语义相似度 + 合理时序 → cross_platform 边
        """
        for i, post_a in enumerate(posts):
            for post_b in posts[i+1:]:
                if post_a["platform"] == post_b["platform"]:
                    continue  # 同平台已在 intra 步处理

                match_score = self.matcher.match_posts(post_a, post_b)

                if match_score > 0.5:
                    # 按时间确定方向
                    if post_a["timestamp"] <= post_b["timestamp"]:
                        src, tgt = post_a["id"], post_b["id"]
                    else:
                        src, tgt = post_b["id"], post_a["id"]
                    pg.add_edge(src, tgt, edge_type="cross_platform",
                               confidence=match_score)

    def _validate_temporal_consistency(self, pg: PropagationGraph):
        """移除时间不一致的边"""
        edges_to_remove = []
        for u, v in pg.graph.edges():
            t_u = pg.graph.nodes[u].get("timestamp")
            t_v = pg.graph.nodes[v].get("timestamp")
            if t_u and t_v and t_u > t_v:
                edges_to_remove.append((u, v))

        for u, v in edges_to_remove:
            pg.graph.remove_edge(u, v)
```

### 5.2 源头溯源

#### 5.2.1 溯源算法

```python
class SourceTracer:
    """新闻源头溯源器

    核心思路：在传播图 DAG 中找到入度为 0 的节点（根节点），
    按时间 + 置信度排序给出候选源头列表。
    """

    def __init__(self):
        self.img_hasher = ImageHasher()

    def trace(self, pg: PropagationGraph) -> list[dict]:
        """推断新闻事件的可能源头"""
        G = pg.graph

        # Step 1: 找传播图根节点（入度为 0）
        roots = [n for n in G.nodes() if G.in_degree(n) == 0]

        # Step 2: 如无纯根节点（全图连通），找最早发布的节点
        if not roots:
            nodes_with_time = [(n, G.nodes[n].get("timestamp"))
                              for n in G.nodes()
                              if G.nodes[n].get("timestamp")]
            nodes_with_time.sort(key=lambda x: x[1])
            roots = [n for n, _ in nodes_with_time[:5]]

        # Step 3: 对每个候选源头打分
        candidates = []
        for root in roots:
            node = G.nodes[root]
            score = self._score_source_candidate(G, root)
            candidates.append({
                "post_id": root,
                "platform": node.get("type", "unknown"),
                "author": node.get("author", "unknown"),
                "timestamp": node.get("timestamp"),
                "text_preview": node.get("text", "")[:100],
                "confidence": score,
                "evidence": self._gather_evidence(G, root),
            })

        # 按置信度降序
        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        return candidates

    def _score_source_candidate(self, G: nx.DiGraph, node_id: str) -> float:
        """
        源头评分因素：
        - 时间最早 → +分
        - 出度大（被很多人转发）→ +分
        - 有图像证据 → +分
        - 入度为 0 → +分
        """
        node = G.nodes[node_id]
        score = 0.5  # 基础分

        # 入度为 0（真正的根节点）
        if G.in_degree(node_id) == 0:
            score += 0.25

        # 出度贡献（每 10 个出度 +0.05）
        out_degree = G.out_degree(node_id)
        score += min(0.15, out_degree * 0.005)

        # 有图像内容（可提供视觉证据）
        if node.get("text"):
            score += 0.10

        return min(1.0, score)

    def _gather_evidence(self, G: nx.DiGraph, root: str) -> dict:
        """收集源头证据"""
        out_edges = list(G.out_edges(root, data=True))
        return {
            "direct_reposts": len([e for e in out_edges
                                   if e[2].get("type") == "repost"]),
            "cross_platform_spread": len([e for e in out_edges
                                          if e[2].get("type") == "cross_platform"]),
            "total_out_degree": len(out_edges),
            "first_level_platforms": list(set(
                G.nodes[tgt].get("type", "?")
                for _, tgt, _ in out_edges
            )),
        }
```

#### 5.2.2 溯源评估

```python
class SourceTracingEvaluator:
    """溯源准确性评估"""

    def evaluate(self, tracer: SourceTracer, events: list[dict]) -> dict:
        """对标注好 ground truth 源头的事件进行评估"""
        metrics = {"hits@1": 0, "hits@3": 0, "mrr": 0.0, "total": len(events)}

        for event in events:
            pg = PropagationGraphBuilder(event["db_path"]).build(event["id"])
            candidates = tracer.trace(pg)

            true_source = event["true_source_id"]

            # Hits@K
            for rank, cand in enumerate(candidates[:3]):
                if cand["post_id"] == true_source:
                    if rank == 0:
                        metrics["hits@1"] += 1
                    metrics["hits@3"] += 1
                    metrics["mrr"] += 1.0 / (rank + 1)
                    break

        metrics["hits@1"] /= metrics["total"]
        metrics["hits@3"] /= metrics["total"]
        metrics["mrr"] /= metrics["total"]
        return metrics
```

### 5.3 情感演化分析

#### 5.3.1 沿传播路径的情感追踪

```python
class SentimentEvolutionAnalyzer:
    """情感沿传播路径的演化分析"""

    def __init__(self):
        self.sentiment_analyzer = ChineseSentimentAnalyzer()

    def analyze_path(self, pg: PropagationGraph,
                     source_id: str) -> dict:
        """分析从 source 开始沿所有传播路径的情感演化"""
        G = pg.graph

        # BFS 遍历传播树
        levels = self._bfs_levels(G, source_id)

        # 每层统计情感
        evolution = []
        for level, nodes in levels.items():
            sentiments = []
            for node_id in nodes:
                text = G.nodes[node_id].get("text", "")
                if text:
                    result = self.sentiment_analyzer.analyze(text)
                    sentiments.append(result)

            if sentiments:
                avg_polarity = np.mean([s["polarity"] for s in sentiments])
                avg_arousal = np.mean([s["arousal"] for s in sentiments])
                dominant_emotions = self._aggregate_dominant(sentiments)
                evolution.append({
                    "level": level,
                    "node_count": len(nodes),
                    "avg_polarity": float(avg_polarity),
                    "avg_arousal": float(avg_arousal),
                    "dominant_emotion": dominant_emotions,
                })

        # 识别情感转折点
        turning_points = self._detect_turning_points(evolution)

        return {
            "source_id": source_id,
            "evolution": evolution,
            "turning_points": turning_points,
            "overall_trend": self._compute_trend(evolution),
        }

    def _bfs_levels(self, G: nx.DiGraph, source: str) -> dict[int, list]:
        """BFS 分层遍历传播图"""
        levels = {0: [source]}
        visited = {source}
        current_level = [source]
        depth = 0

        while current_level:
            next_level = []
            for node in current_level:
                for _, child in G.out_edges(node):
                    if child not in visited:
                        visited.add(child)
                        next_level.append(child)
            if next_level:
                depth += 1
                levels[depth] = next_level
                current_level = next_level
            else:
                break

        return levels

    def _aggregate_dominant(self, sentiments: list[dict]) -> dict:
        """聚合每层的主导情感"""
        emotion_counts = {}
        for s in sentiments:
            dom = s.get("dominant", "中性")
            emotion_counts[dom] = emotion_counts.get(dom, 0) + 1
        total = len(sentiments)
        return {k: v/total for k, v in
                sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True)[:3]}

    def _detect_turning_points(self, evolution: list[dict]) -> list[dict]:
        """检测情感转折点（相邻层极性变化 > 阈值）"""
        turning_points = []
        for i in range(1, len(evolution)):
            prev_pol = evolution[i-1]["avg_polarity"]
            curr_pol = evolution[i]["avg_polarity"]
            delta = abs(curr_pol - prev_pol)
            if delta > 0.3:  # 极性跳变 > 0.3
                turning_points.append({
                    "from_level": i - 1,
                    "to_level": i,
                    "polarity_shift": float(curr_pol - prev_pol),
                    "direction": "正向" if curr_pol > prev_pol else "负向",
                    "magnitude": float(delta),
                })
        return turning_points

    def _compute_trend(self, evolution: list[dict]) -> str:
        """计算整体情感趋势"""
        if len(evolution) < 2:
            return "数据不足"
        first = evolution[0]["avg_polarity"]
        last = evolution[-1]["avg_polarity"]
        diff = last - first
        if diff > 0.2:
            return "情感正向偏移"
        elif diff < -0.2:
            return "情感负向偏移"
        else:
            return "情感基本稳定"

    def cross_platform_sentiment(self, pg: PropagationGraph) -> dict:
        """跨平台情感差异分析"""
        G = pg.graph
        platform_sentiments = {}

        for node_id in G.nodes():
            platform = G.nodes[node_id].get("type", "unknown")
            text = G.nodes[node_id].get("text", "")
            if text:
                result = self.sentiment_analyzer.analyze(text)
                if platform not in platform_sentiments:
                    platform_sentiments[platform] = []
                platform_sentiments[platform].append(result)

        # 按平台聚合
        comparison = {}
        for platform, sentiments in platform_sentiments.items():
            comparison[platform] = {
                "count": len(sentiments),
                "avg_polarity": float(np.mean([s["polarity"]
                                               for s in sentiments])),
                "avg_arousal": float(np.mean([s["arousal"]
                                              for s in sentiments])),
                "dominant_emotion": max(set(s["dominant"]
                    for s in sentiments),
                    key=lambda e: sum(1 for s in sentiments
                                     if s["dominant"] == e)),
            }

        return comparison
```

---

## 6. 应用层

### 6.1 传播图谱可视化

```python
import plotly.graph_objects as go
import networkx as nx

class PropagationVisualizer:
    """交互式传播图谱"""

    @staticmethod
    def plot_propagation_graph(pg: PropagationGraph,
                               highlight_source: str = None) -> go.Figure:
        """绘制传播力导向图"""
        G = pg.graph
        pos = nx.spring_layout(G, k=2, iterations=50)

        # 边
        edge_x, edge_y = [], []
        for u, v, data in G.edges(data=True):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            # 按边类型着色
            edge_color = {"repost": "#1f77b4",
                          "cite": "#ff7f0e",
                          "cross_platform": "#2ca02c",
                          "image_match": "#d62728"}

        edge_traces = []
        for etype, color in edge_color.items():
            # ... 按类型分组绘制边

        # 节点
        node_x, node_y, node_color, node_size, node_text = [], [], [], [], []
        for node in G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            # 按平台着色
            platform = G.nodes[node].get("type", "?")
            platform_colors = {
                "weibo": "#e60012",    # 微博红
                "sina": "#ff8400",     # 新浪橙
                "netease": "#c30",     # 网易红
                "zhihu": "#0066ff",    # 知乎蓝
            }
            node_color.append(platform_colors.get(platform, "#999"))
            node_size.append(max(5, G.nodes[node].get("engagement", 0) / 100))
            node_text.append(G.nodes[node].get("text", "")[:50])

        # ... 组装 Figure
        return go.Figure()

    @staticmethod
    def plot_sentiment_timeline(evolution: list[dict]) -> go.Figure:
        """情感演化时间线"""
        fig = go.Figure()
        levels = [e["level"] for e in evolution]

        fig.add_trace(go.Scatter(
            x=levels, y=[e["avg_polarity"] for e in evolution],
            mode='lines+markers',
            name='情感极性',
            line=dict(color='#e60012', width=2),
        ))
        fig.add_trace(go.Scatter(
            x=levels, y=[e["avg_arousal"] for e in evolution],
            mode='lines+markers',
            name='情感唤起度',
            line=dict(color='#0066ff', width=2),
            yaxis='y2',
        ))

        fig.update_layout(
            title="传播链情感演化",
            xaxis_title="传播层级",
            yaxis=dict(title="情感极性 (-1 ~ +1)"),
            yaxis2=dict(title="情感唤起度 (0-1)", overlaying='y', side='right'),
        )
        return fig

    @staticmethod
    def plot_source_confidence(candidates: list[dict]) -> go.Figure:
        """源头溯源置信度柱状图"""
        fig = go.Figure(go.Bar(
            x=[f"{c['platform']}:{c['post_id'][:8]}" for c in candidates],
            y=[c["confidence"] for c in candidates],
            marker_color=['#e60012' if i == 0 else '#999'
                         for i in range(len(candidates))],
            text=[f"{c['confidence']:.2f}" for c in candidates],
            textposition='auto',
        ))
        fig.update_layout(
            title="源头候选置信度排序",
            xaxis_title="候选",
            yaxis_title="置信度",
            yaxis_range=[0, 1],
        )
        return fig
```

### 6.2 分析报告生成

```python
class ReportGenerator:
    """新闻溯源分析报告自动生成"""

    def generate(self, event_id: str,
                 pg: PropagationGraph,
                 trace_result: list[dict],
                 sentiment_result: dict) -> str:
        """生成 Markdown 格式分析报告"""

        top_source = trace_result[0] if trace_result else None
        total_nodes = pg.graph.number_of_nodes()
        total_edges = pg.graph.number_of_edges()
        platforms = set(pg.graph.nodes[n].get("type", "?")
                       for n in pg.graph.nodes())

        report = f"""# 新闻事件溯源分析报告

## 事件概要
- **事件 ID**: {event_id}
- **传播规模**: {total_nodes} 个节点, {total_edges} 条传播边
- **涉及平台**: {', '.join(platforms)}

## 源头溯源结果

### 最可能源头
- **平台**: {top_source['platform']}
- **发布者**: {top_source['author']}
- **发布时间**: {top_source['timestamp']}
- **置信度**: {top_source['confidence']:.2%}
- **内容预览**: {top_source['text_preview']}

### 证据链
- 直接转发数: {top_source['evidence']['direct_reposts']}
- 跨平台传播数: {top_source['evidence']['cross_platform_spread']}
- 首批传播平台: {', '.join(top_source['evidence']['first_level_platforms'])}

## 情感演化分析

### 整体趋势
{sentiment_result['overall_trend']}

### 情感转折点
"""
        for tp in sentiment_result.get("turning_points", []):
            report += (f"- 第 {tp['from_level']} → {tp['to_level']} 层: "
                      f"{tp['direction']} ({tp['polarity_shift']:+.2f})\n")

        report += "\n### 跨平台情感对比\n\n"
        comparison = sentiment_result.get("cross_platform", {})
        report += "| 平台 | 帖子数 | 平均极性 | 平均唤起度 | 主导情感 |\n"
        report += "|------|--------|----------|------------|----------|\n"
        for platform, stats in comparison.items():
            report += (f"| {platform} | {stats['count']} | "
                      f"{stats['avg_polarity']:.2f} | "
                      f"{stats['avg_arousal']:.2f} | "
                      f"{stats['dominant_emotion']} |\n")

        return report
```

---

## 7. 技术栈总览

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| Python | CPython | 3.10+ | 主语言 |
| 爬虫 | Scrapling | latest | 隐身浏览器 + HTTP 请求 |
| 图像处理 | OpenCV | 4.8+ | 图像预处理、色彩分析 |
| | Pillow | 10+ | 图像加载/缩放 |
| 深度学习 | PyTorch | 2.x | 模型推理框架 |
| | HuggingFace Transformers | 4.36+ | BERT/RoBERTa 模型加载 |
| | Chinese-CLIP | — | 中文图文对齐 |
| OCR | PaddleOCR | 2.7+ | 图像文字提取 |
| 图计算 | NetworkX | 3.2+ | 传播图构建与分析 |
| 数值计算 | NumPy | 1.24+ | 向量运算 |
| 数据存储 | SQLite | 3 (stdlib) | 结构化数据 |
| 可视化 | Plotly | 5.17+ | 交互式图表 |
| | pyecharts | 2.0+ | 中文友好的可视化 |
| 配置管理 | Hydra / OmegaConf | 2.3+ | YAML 配置 |
| Cookie 管理 | browser-cookie3 | — | 浏览器 Cookie 导入 |
| 实验管理 | wandb (可选) | — | 训练追踪 |

---

## 8. 数据流

### 8.1 端到端流水线

```
┌─────────────────────────────────────────────────────────────┐
│  用户输入: 新闻事件关键词 (如 "东方甄选 事件")                  │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 事件发现 (EventTracker.discover_event)                │
│   - 关键词匹配已有事件 / 创建新事件                            │
│   - 输出: event_id                                           │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 全平台采集 (EventTracker.crawl_event)                 │
│   - 微博: WeiboScraper.search_event(keyword)                  │
│   - 新闻: NewsScraper.fetch_by_keyword(keyword)               │
│   - 可选知乎等                                                 │
│   - 输出: List[Post] → SQLite                                │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: 特征提取                                              │
│   - 文本: RoBERTa 嵌入 + 情感分析 + 统计特征                   │
│   - 图像: CLIP 嵌入 + pHash/dHash + OCR + 色彩               │
│   - 下载图片并存储本地                                        │
│   - 输出: posts 表更新, images 表填充                         │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: 传播图构建 (PropagationGraphBuilder.build)            │
│   - 平台内边: 转发链 / 引用                                   │
│   - 跨平台边: 多模态内容匹配                                   │
│   - 时序一致性验证                                            │
│   - 输出: PropagationGraph + propagation_edges 表             │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 5: 源头溯源 (SourceTracer.trace)                         │
│   - 根节点定位 + 候选打分                                     │
│   - 输出: 候选源头排序列表                                    │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 6: 情感演化分析                                          │
│   - 沿传播路径的逐层情感统计                                   │
│   - 跨平台情感对比                                            │
│   - 情感转折点检测                                            │
│   - 输出: sentiment_records 表 + 分析结果                     │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 7: 可视化 & 报告生成                                     │
│   - 传播图谱 (Plotly 力导向图)                                │
│   - 情感演化时间线                                            │
│   - 源头置信度柱状图                                          │
│   - Markdown 分析报告                                         │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 数据流示意图

```
[微博] ──StealthySession(solve_cloudflare=True, adaptive=True)──┐
                                                                 ├──→ [SQLite] ──→ [特征提取] ──→ [传播图]
[新浪新闻] ──FetcherSession(impersonate='chrome')───────────────┤                                      │
                                                                 │                                      ▼
[网易新闻] ──FetcherSession(impersonate='chrome')───────────────┤                              [源头溯源 + 情感演化]
                                                                 │                                      │
[知乎] ──StealthySession(adaptive=True)─────────────────────────┘                                      ▼
                                                                                              [可视化 + 报告]
```

---

## 9. 配置管理

```yaml
# config.yaml
# 基于 Hydra 的完整系统配置

defaults:
  - _self_
  - data: default
  - features: default
  - analysis: default

# ========== 爬虫配置 ==========
scraping:
  # --- Scrapling 全局参数 ---
  scrapling:
    headless: true                    # 无头模式（节省资源）
    solve_cloudflare: true            # 自动绕过 Cloudflare
    stealthy_headers: true            # 真实浏览器请求头
    google_search: false              # 不通过 Google 跳转
    adaptive_mode: true               # 启用自适应选择器
    auto_save_first_run: true         # 首次运行保存元素特征
    fingerprint_dir: ".scrapling/"    # 元素指纹存储目录

  weibo:
    enabled: true
    cookie_dir: "cookies/weibo/"
    max_pages_per_keyword: 10
    request_delay: 3                  # 请求间隔（秒）
    max_retry: 3
    retry_backoff: "exponential"      # 指数退避

  news:
    enabled: true
    sources: ["sina", "netease"]
    max_articles_per_source: 50
    request_delay: 2
    impersonate: "chrome"             # FetcherSession TLS 指纹

  zhihu:
    enabled: false
    max_pages: 5

# ========== 数据存储 ==========
storage:
  db_path: "data/news_trace.db"
  image_dir: "data/images/"
  cache_ttl_hours: 24         # 爬虫缓存有效期

# ========== 特征提取 ==========
features:
  text:
    model_name: "hfl/chinese-roberta-wwm-ext"
    device: "cuda"
    max_length: 256
    sentiment_model: "uer/roberta-base-finetuned-jd-binary-chinese"
    output_dim: 784           # 768 + 8 + 8

  image:
    clip_model: "ViT-B/32"
    device: "cuda"
    hash_size: 8
    output_dim: 643           # 512 + 3 + 64 + 64

# ========== 分析 ==========
analysis:
  propagation:
    cross_platform_threshold: 0.5   # 跨平台匹配最低置信度
    temporal_validation: true
    max_graph_depth: 10

  source_tracing:
    min_out_degree: 1
    time_window_hours: 24

  sentiment:
    turning_point_threshold: 0.3     # 情感极性变化阈值
    min_posts_per_level: 3           # 每层最少帖子数

# ========== 可视化 ==========
visualization:
  graph_layout: "spring"      # spring, kamada_kawai, circular
  max_nodes_display: 200
  platform_colors:
    weibo: "#e60012"
    sina: "#ff8400"
    netease: "#c30"
    zhihu: "#0066ff"
```

---

## 10. 评估策略

### 10.1 评估指标

| 维度 | 指标 | 目标值 | 说明 |
|------|------|--------|------|
| **源头溯源** | Hits@1 | > 0.60 | 排名第一命中率 |
| | Hits@3 | > 0.80 | 前三命中率 |
| | MRR | > 0.70 | 平均倒数排名 |
| **跨平台匹配** | 图像重复检测 Precision | > 0.90 | 感知哈希精度 |
| | 文本语义匹配 mAP | > 0.75 | 跨平台事件匹配 |
| **情感分析** | 情感分类 Accuracy | > 0.80 | 7类情感 |
| | 极性方向 Accuracy | > 0.85 | 正/负/中 三分类 |
| **系统** | 端到端延迟 | < 5 分钟 | 单事件完整分析 |

### 10.2 评估数据集

| 数据 | 用途 | 规模 |
|------|------|------|
| Weibo-Fake-News (标注版) | 源头溯源 + 传播图 | ~4,000 事件 |
| CHEF 中文突发事件 | 情感演化基准 | ~1,200 事件 |
| 自标注 50 事件 | 跨平台综合验证 | ~50 事件 |

### 10.3 消融实验设计

| 变体 | 描述 | 验证假设 |
|------|------|----------|
| **Full** | 所有模块开启 | — |
| **w/o Images** | 仅文本特征 | 图像指纹对跨平台匹配的贡献 |
| **w/o Cross-Platform** | 仅平台内图 | 多源融合对传播图完整性的贡献 |
| **w/o OCR** | 不再从图像提取文字 | OCR 对截图场景的贡献 |
| **w/o Temporal Validation** | 不验证时间一致性 | 时序约束对图质量的贡献 |
| **Rule-Based Baseline** | 仅按时间排序定源头 | 图方法 vs. 简单规则的提升 |

### 10.4 案例研究

选取 3 类典型新闻事件进行端到端验证：

| 类型 | 案例 | 验证重点 |
|------|------|----------|
| **突发事件** | 某自然灾害报道 | 多平台传播速度、源头单一性 |
| **社会热点** | 某争议事件 | 情感反转、多源头竞争 |
| **跨平台谣言** | 某虚假信息 | 辟谣信息的传播路径、情感纠偏 |

---

## 11. 项目结构

```
news-trace/
├── config/
│   └── config.yaml                  # Hydra 全局配置
├── data/
│   ├── news_trace.db                # SQLite 数据库
│   ├── images/                      # 下载的图片
│   └── cookies/                     # 浏览器 Cookie 文件
│       └── weibo.json
├── src/
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py                  # 基础爬虫类
│   │   ├── weibo.py                 # 微博爬虫
│   │   ├── news.py                  # 新闻网站爬虫
│   │   ├── zhihu.py                 # 知乎爬虫（可选）
│   │   └── cookie_manager.py        # Cookie 池管理
│   ├── features/
│   │   ├── __init__.py
│   │   ├── text_encoder.py          # RoBERTa 编码器
│   │   ├── sentiment.py             # 中文情感分析
│   │   ├── image_encoder.py         # CLIP 图像编码
│   │   ├── image_hasher.py          # 感知哈希
│   │   ├── ocr.py                   # OCR 文字提取
│   │   └── cross_platform.py        # 跨平台匹配器
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── graph_builder.py         # 传播图构建
│   │   ├── source_tracer.py         # 源头溯源
│   │   ├── sentiment_evolution.py   # 情感演化
│   │   └── evaluator.py             # 评估模块
│   ├── visualization/
│   │   ├── __init__.py
│   │   ├── propagation_graph.py     # 传播图谱
│   │   ├── sentiment_timeline.py    # 情感时间线
│   │   └── report.py                # 报告生成
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py              # 数据库操作
│   │   └── models.py                # 数据模型
│   └── pipeline.py                  # 端到端流水线
├── notebooks/
│   ├── 01_scraping_demo.ipynb       # 爬虫演示
│   ├── 02_feature_extraction.ipynb  # 特征提取演示
│   ├── 03_propagation_graph.ipynb   # 传播图构建演示
│   ├── 04_source_tracing.ipynb      # 溯源演示
│   └── 05_sentiment_evolution.ipynb # 情感演化演示
├── scripts/
│   ├── run_pipeline.py              # 命令行入口
│   ├── evaluate.py                  # 评估脚本
│   └── export_cookies.py            # Cookie 导出工具
├── tests/
│   ├── test_scrapers.py
│   ├── test_features.py
│   └── test_analysis.py
├── requirements.txt
└── README.md
```

---

## 12. 运行方式

### 12.1 环境配置

```bash
# 创建虚拟环境
conda create -n news-trace python=3.10
conda activate news-trace

# 安装 PyTorch (按 GPU 型号选择 CUDA 版本)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 安装 NLP 和图像处理
pip install transformers pillow opencv-python-headless
pip install paddlepaddle-gpu paddleocr

# ========== Scrapling 安装（核心爬虫框架）==========
pip install "scrapling[fetchers]"

# 下载 Scrapling 所需浏览器及依赖（必须执行）
scrapling install

# 可选: 安装 Scrapling 扩展
# pip install "scrapling[ai]"      # AI 辅助抓取 (MCP Server)
# pip install "scrapling[shell]"   # 命令行 Shell (scrapling shell)

# 分析和可视化
pip install networkx plotly pyecharts sqlite-utils

# 配置和实验管理
pip install hydra-core omegaconf
pip install wandb  # 可选

# 开发环境
pip install jupyterlab pytest

# 导出浏览器 Cookie（用于微博登录态）
pip install browser-cookie3
```

### 12.2 启动流水线

```bash
# 单事件分析
python scripts/run_pipeline.py --keyword "东方甄选事件"

# 批量评估
python scripts/evaluate.py --dataset data/weibo_fake_news --output results/

# 交互式分析
jupyter lab notebooks/
```

### 12.3 硬件需求

| 组件 | 最低要求 | 推荐配置 |
|------|----------|----------|
| CPU | 4 核 | 8 核 |
| RAM | 16 GB | 32 GB |
| GPU | GTX 1660 (6GB) | RTX 3060 (12GB) |
| 磁盘 | 50 GB | 100 GB SSD |

---

## 13. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 微博 Cookie 失效 | 中 | 中 | CookieManager 多账号池轮询，失效自动切换；池不足 2 个时触发重新登录提醒 |
| 微博反爬策略升级 | 中 | 高 | **Scrapling 三层防护**: (1) `StealthySession(solve_cloudflare=True)` 自动绕过验证; (2) `adaptive=True` 选择器自动适应 DOM 变化; (3) 降级至公开数据集 |
| 新闻网站改版导致选择器失效 | 低 | 低 | **Scrapling 自适应**: `css(..., adaptive=True)` + `find_similar()` 自动定位; CSS/XPath 双选择器注册表回退 |
| Scrapling 浏览器依赖更新 | 低 | 中 | `scrapling install --force` 强制重装；`pip install "scrapling[fetchers]"` 保持最新版 |
| 跨平台图像匹配精度不足 | 低 | 中 | pHash + dHash + CLIP 三路互补 |
| 传播图存在缺失边 | 中 | 中 | 图补全 + 缺失推断，在评估中报告覆盖率 |
| 某平台数据占比过低导致偏差 | 低 | 中 | 按平台分层统计，低数据量平台标注 confidence 折扣 |

---

## 14. 路线图

### Phase 1: 核心流水线（4 周）

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W1 | 微博 + 新闻爬虫实现 | 可用爬虫，采集测试数据 |
| W2 | 文本特征提取（编码 + 情感） | 特征提取模块 + 单元测试 |
| W3 | 图像特征提取（CLIP + 哈希 + OCR） | 多模态特征提取模块 |
| W4 | SQLite 存储 + 端到端流水线联调 | 完整数据流可运行 |

### Phase 2: 分析模块（3 周）

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W5 | 传播图构建（平台内 + 跨平台） | PropagationGraphBuilder |
| W6 | 源头溯源 + 情感演化分析 | SourceTracer + SentimentEvolutionAnalyzer |
| W7 | 可视化 + 报告生成 + 评价指标 | 6 张图 + 报告模板 + 评估结果 |

### Phase 3: 完善（2 周）

| 周次 | 任务 | 交付物 |
|------|------|--------|
| W8 | 案例研究 + 消融实验 | 3 个案例 + 消融结果 |
| W9 | 论文撰写 + 演示准备 | 论文初稿 + 演示 PPT |

---

## 附录 A: 与题目10的关键差异

| 维度 | 题目10（已否决） | 题目8（本系统） |
|------|-----------------|-----------------|
| 目标平台 | 小红书/抖音（不可爬） | 微博/新闻网站（可爬） |
| 爬虫方案 | StealthyFetcher + 无解加密 | Scrapling + Cookie 池 |
| 图像模型数 | 5 个独立模型 | 3 个（CLIP+pHash+OCR） |
| 中文支持 | 英文 GoEmotions ❌ | Chinese-RoBERTa ✅ |
| 数学方法 | Hawkes 过程（数据不可得） | 图论（NetworkX 直接算） |
| 核心任务 | 爆款预测（分类+回归） | 溯源+情感演化（图分析） |
| 部署方式 | Docker 微服务集群 | 单机脚本 + Jupyter |
| 公开数据集 | 无中文可用数据 | Weibo-Fake-News、CHEF |
| 论文卖点 | 多模态预测（数据不可行） | 跨平台多模态溯源（可行） |

## 附录 B: 依赖清单

```
# requirements.txt

# ===== 爬虫核心 (Scrapling) =====
scrapling[fetchers]>=0.1.0
# 安装后必须执行: scrapling install (下载浏览器依赖)

# ===== 深度学习 =====
torch>=2.0.0
torchvision>=0.15.0
transformers>=4.36.0

# ===== 图像处理 =====
pillow>=10.0.0
opencv-python-headless>=4.8.0

# ===== OCR =====
paddlepaddle-gpu>=2.5.0   # CPU 版: paddlepaddle>=2.5.0
paddleocr>=2.7.0

# ===== 图计算 & 数值 =====
networkx>=3.2
numpy>=1.24.0

# ===== 可视化 =====
plotly>=5.17.0
pyecharts>=2.0.0

# ===== 配置 & 实验 =====
hydra-core>=1.3.0
omegaconf>=2.3.0
wandb>=0.16.0              # 可选

# ===== 数据存储 =====
sqlite-utils>=3.35

# ===== 开发工具 =====
jupyterlab>=4.0.0
pytest>=7.0.0
browser-cookie3>=0.19.0    # Cookie 导出
```

**首次安装步骤（必须按顺序）：**

```bash
# 1. 安装 Scrapling
pip install "scrapling[fetchers]"

# 2. 下载 Scrapling 的浏览器二进制文件（Chromium 等）
scrapling install

# 3. 验证安装
python -c "from scrapling.fetchers import StealthySession; print('OK')"

# 4. 安装其余依赖
pip install -r requirements.txt
```
