"""CHEF 中文突发事件数据集加载器

CHEF (Chinese Emergency Events) — 清华大学发布的中文突发事件数据集,
包含 ~1,200 个事件的新闻报道,适用于情感演化基准测试。

数据集结构 (预期):
  data/datasets/CHEF/
    ├── events.json          # 事件元信息列表
    ├── articles/            # 按事件分组的新闻文章
    │   ├── event_001.json
    │   ├── event_002.json
    │   └── ...
    └── README.md

下载地址:
  - https://github.com/THU-KEG/CHEF (需申请或从论文附录获取)
"""

import os
import json
import hashlib
from datetime import datetime

from ..storage.models import Post, Event


class CHEFDataset:
    """CHEF 中文突发事件数据集"""

    DEFAULT_EVENTS_FILE = "events.json"

    def __init__(self, data_dir: str):
        if not os.path.isdir(data_dir):
            raise FileNotFoundError(f"数据集目录不存在: {data_dir}")
        self.data_dir = data_dir
        self.events_file = os.path.join(data_dir, self.DEFAULT_EVENTS_FILE)

    def to_db(self, db, event_prefix: str = "") -> int:
        """将数据集全部事件导入数据库, 返回导入的帖子数"""
        events = self.load()
        total_posts = 0
        for evt in events:
            name = evt["name"]
            event_id = f"{event_prefix}_{hashlib.md5(name.encode()).hexdigest()[:10]}"
            db.create_event(Event(event_id=event_id, name=name,
                                  keywords=evt.get("keywords", [name])))
            posts = [self._to_post(raw, event_id)
                     for raw in evt.get("posts", [])]
            posts = [p for p in posts if p is not None]
            saved = db.insert_posts_batch(posts)
            db.update_event_stats(event_id)
            total_posts += saved
        print(f"[Dataset] 导入完成: {len(events)} 事件, {total_posts} 帖子")
        return total_posts

    def _to_post(self, raw: dict, event_id: str) -> Post | None:
        """将单条原始记录转为 Post"""
        text = raw.get("text") or raw.get("content") or raw.get("title", "")
        if not text.strip():
            return None
        pid = raw.get("id") or raw.get("post_id",
              hashlib.md5(text[:80].encode()).hexdigest()[:12])
        ts = raw.get("timestamp") or raw.get("time") or raw.get("publish_time")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                ts = datetime.now()
        elif ts is None:
            ts = datetime.now()
        return Post(
            post_id=str(pid),
            platform=raw.get("platform", "dataset"),
            post_type=raw.get("post_type", "original"),
            text=text.strip(),
            image_urls=raw.get("image_urls", []) or raw.get("images", []),
            author_name=raw.get("author_name") or raw.get("author", ""),
            parent_id=raw.get("parent_id"),
            timestamp=ts,
            repost_count=raw.get("repost_count", 0) or 0,
            comment_count=raw.get("comment_count", 0) or 0,
            like_count=raw.get("like_count", 0) or 0,
            engagement_count=raw.get("engagement_count", 0) or 0,
            event_id=event_id,
            url=raw.get("url", ""),
        )

    def load(self) -> list[dict]:
        """加载 CHEF 数据集"""
        if os.path.isfile(self.events_file):
            return self._load_from_events_json()
        return self._load_from_articles_dir()

    def _load_from_events_json(self) -> list[dict]:
        with open(self.events_file, "r", encoding="utf-8") as f:
            raw_events = json.load(f)
        events = []
        for re in raw_events:
            event_id = re.get("id") or re.get("event_id", "")
            articles_file = os.path.join(self.data_dir, "articles", f"{event_id}.json")
            if os.path.isfile(articles_file):
                posts = self._parse_articles(articles_file)
            elif "articles" in re:
                posts = self._dicts_to_posts(re["articles"])
            else:
                posts = []
            if posts:
                events.append({
                    "name": re.get("name") or re.get("title", event_id),
                    "keywords": re.get("keywords", []) or [re.get("name", "")],
                    "posts": posts,
                })
        return events

    def _load_from_articles_dir(self) -> list[dict]:
        articles_dir = os.path.join(self.data_dir, "articles")
        if not os.path.isdir(articles_dir):
            articles_dir = self.data_dir
        events = []
        for fname in sorted(os.listdir(articles_dir)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(articles_dir, fname)
            posts = self._parse_articles(fpath)
            if not posts:
                continue
            event_id = fname.replace(".json", "")
            name = posts[0].get("text", event_id)[:40] if posts else event_id
            keywords = [posts[0].get("text", "")[:20]] if posts else []
            events.append({"name": name, "keywords": keywords, "posts": posts})
        return events

    def _parse_articles(self, filepath: str) -> list[dict]:
        """解析单个事件的文章 JSON 文件"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return self._dicts_to_posts(data)
        if isinstance(data, dict):
            for key in ("articles", "data", "posts", "items"):
                if key in data and isinstance(data[key], list):
                    return self._dicts_to_posts(data[key])
            return self._dicts_to_posts([data])
        return []

    def _dicts_to_posts(self, articles: list[dict]) -> list[dict]:
        """将 CHEF 原始字典转为统一 Post 格式 (dict 列表, 非 Post 对象)"""
        posts = []
        for art in articles:
            text_parts = []
            title = art.get("title", "")
            if title:
                text_parts.append(title)
            content = art.get("content") or art.get("text") or art.get("body", "")
            if content:
                text_parts.append(content)
            text = "\n".join(text_parts)
            if not text.strip():
                continue
            ts = (art.get("time") or art.get("publish_time") or
                  art.get("timestamp") or art.get("ctime") or art.get("date"))
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    ts = None
            pid = art.get("id") or art.get("article_id",
                  hashlib.md5(text[:80].encode()).hexdigest()[:12])
            posts.append({
                "id": str(pid),
                "platform": art.get("source") or art.get("platform", "news"),
                "post_type": "article",
                "text": text.strip(),
                "title": title,
                "image_urls": art.get("images", []) or [],
                "author_name": art.get("author") or art.get("media", ""),
                "parent_id": art.get("parent_id"),
                "timestamp": ts,
                "repost_count": art.get("repost_count", 0) or 0,
                "comment_count": art.get("comment_count", 0) or 0,
                "like_count": art.get("like_count", 0) or 0,
                "engagement_count": art.get("engagement_count", 0) or 0,
                "url": art.get("url", ""),
                "category": art.get("category") or art.get("type", ""),
            })
        return posts
