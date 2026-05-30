"""SQLite 数据库操作层

统一管理新闻溯源系统的数据存储。
"""

import os
import json
import sqlite3
import time
import hashlib
from datetime import datetime
from typing import Optional

from .models import Post, Event, SentimentRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    post_type TEXT NOT NULL,
    text TEXT NOT NULL,
    images TEXT,
    image_urls TEXT,
    author_id TEXT,
    author_name TEXT,
    parent_id TEXT,
    event_id TEXT,
    url TEXT,
    timestamp DATETIME NOT NULL,
    engagement_count INTEGER DEFAULT 0,
    repost_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    post_id TEXT REFERENCES posts(id),
    local_path TEXT NOT NULL,
    url TEXT,
    phash TEXT,
    dhash TEXT,
    clip_embedding BLOB,
    ocr_text TEXT,
    width INTEGER,
    height INTEGER,
    file_size INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    keywords TEXT,
    first_seen DATETIME,
    last_updated DATETIME,
    post_count INTEGER DEFAULT 0,
    source_candidates TEXT
);

CREATE TABLE IF NOT EXISTS propagation_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT REFERENCES posts(id),
    target_id TEXT REFERENCES posts(id),
    edge_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    timestamp_diff INTEGER,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS sentiment_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT REFERENCES posts(id),
    sentiment_label TEXT,
    sentiment_score REAL,
    arousal_score REAL,
    emotions TEXT,
    model_version TEXT
);
"""


class Database:
    """数据库操作封装"""

    def __init__(self, db_path: str = "data/news_trace.db"):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else "data", exist_ok=True)
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        """初始化表结构"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ========== Posts ==========

    def insert_post(self, post: Post) -> bool:
        """插入或更新帖子"""
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO posts
                    (id, platform, post_type, text, images, image_urls,
                     author_id, author_name, parent_id, event_id, url,
                     timestamp, engagement_count, repost_count,
                     comment_count, like_count, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post.post_id, post.platform, post.post_type,
                    post.text, json.dumps(post.images, ensure_ascii=False),
                    json.dumps(post.image_urls, ensure_ascii=False),
                    post.author_id, post.author_name, post.parent_id,
                    post.event_id, post.url,
                    post.timestamp.isoformat() if post.timestamp else datetime.now().isoformat(),
                    post.engagement_count, post.repost_count,
                    post.comment_count, post.like_count,
                    json.dumps(post.metadata, ensure_ascii=False),
                ))
            return True
        except Exception as e:
            print(f"[DB] 插入帖子失败 {post.post_id}: {e}")
            return False

    def insert_posts_batch(self, posts: list[Post]) -> int:
        """批量插入帖子，返回成功数"""
        count = 0
        for post in posts:
            if self.insert_post(post):
                count += 1
        return count

    def get_post(self, post_id: str) -> Optional[dict]:
        """获取单条帖子"""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
            return dict(row) if row else None

    def get_event_posts(self, event_id: str) -> list[dict]:
        """获取事件的所有帖子，按时间排序"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM posts WHERE event_id=? ORDER BY timestamp",
                (event_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_posts_by_platform(self, platform: str, limit: int = 100) -> list[dict]:
        """按平台查询帖子"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM posts WHERE platform=? ORDER BY timestamp DESC LIMIT ?",
                (platform, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_post_count(self, event_id: Optional[str] = None) -> int:
        """统计帖子数"""
        with self._connect() as conn:
            if event_id:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM posts WHERE event_id=?", (event_id,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) as cnt FROM posts").fetchone()
            return row["cnt"] if row else 0

    # ========== Events ==========

    def create_event(self, event: Event) -> str:
        """创建新事件，返回 event_id"""
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO events
                (id, name, keywords, first_seen, last_updated, post_count, source_candidates)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id, event.name,
                json.dumps(event.keywords, ensure_ascii=False),
                event.first_seen.isoformat(),
                event.last_updated.isoformat(),
                event.post_count,
                json.dumps(event.source_candidates, ensure_ascii=False),
            ))
        return event.event_id

    def find_event_by_keyword(self, keyword: str) -> Optional[dict]:
        """按关键词查找已有事件"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE json_extract(keywords, '$[0]') LIKE ?",
                (f"%{keyword}%",)
            ).fetchall()
            # 精确匹配优先
            for row in rows:
                keywords = json.loads(row["keywords"])
                if keyword in keywords:
                    return dict(row)
            return dict(rows[0]) if rows else None

    def update_event_stats(self, event_id: str):
        """更新事件统计"""
        with self._connect() as conn:
            post_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM posts WHERE event_id=?", (event_id,)
            ).fetchone()["cnt"]
            conn.execute(
                "UPDATE events SET post_count=?, last_updated=? WHERE id=?",
                (post_count, datetime.now().isoformat(), event_id)
            )

    def get_event(self, event_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            return dict(row) if row else None

    def list_events(self) -> list[dict]:
        """列出所有事件, 按最后更新时间倒序"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY last_updated DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ========== Sentiment ==========

    def insert_sentiment(self, record: SentimentRecord):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sentiment_records
                (post_id, sentiment_label, sentiment_score, arousal_score, emotions, model_version)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                record.post_id, record.sentiment_label,
                record.sentiment_score, record.arousal_score,
                json.dumps(record.emotions, ensure_ascii=False),
                record.model_version,
            ))

    # ========== Stats ==========

    def stats(self) -> dict:
        """数据库统计"""
        with self._connect() as conn:
            post_count = conn.execute("SELECT COUNT(*) as cnt FROM posts").fetchone()["cnt"]
            event_count = conn.execute("SELECT COUNT(*) as cnt FROM events").fetchone()["cnt"]
            platforms = conn.execute(
                "SELECT platform, COUNT(*) as cnt FROM posts GROUP BY platform"
            ).fetchall()

        return {
            "post_count": post_count,
            "event_count": event_count,
            "by_platform": {r["platform"]: r["cnt"] for r in platforms},
        }
