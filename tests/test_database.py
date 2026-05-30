"""数据库 CRUD 操作测试"""

import json
import sqlite3
from datetime import datetime

import pytest
from src.storage.database import Database
from src.storage.models import Post, Event, SentimentRecord


class TestDatabaseInit:
    """Schema 初始化"""

    def test_tables_created(self, db):
        """初始化后 5 张表应全部存在"""
        conn = sqlite3.connect(db.db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        for t in ["posts", "events", "images", "propagation_edges",
                   "sentiment_records"]:
            assert t in tables, f"Table {t} missing"

    def test_schema_idempotent(self, temp_db_path):
        """重复创建不应报错"""
        db1 = Database(db_path=temp_db_path)
        db2 = Database(db_path=temp_db_path)  # 第二次 init
        conn = sqlite3.connect(db2.db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "posts" in tables


class TestEventCRUD:
    """事件 CRUD"""

    def test_create_and_get_event(self, db):
        event = Event(
            event_id="ev_001", name="测试事件",
            keywords=["测试", "AI"],
        )
        db.create_event(event)
        result = db.get_event("ev_001")
        assert result is not None
        assert result["name"] == "测试事件"

    def test_create_event_defaults(self, db):
        """默认值应正确设置"""
        event = Event(event_id="ev_defaults", name="默认值测试")
        db.create_event(event)
        result = db.get_event("ev_defaults")
        assert result["post_count"] == 0

    def test_get_nonexistent_event(self, db):
        """不存在的 event_id 返回 None"""
        result = db.get_event("nonexistent_id")
        assert result is None


class TestPostCRUD:
    """帖子 CRUD"""

    def test_insert_and_retrieve_post(self, db):
        event = Event(event_id="ev_001", name="测试")
        db.create_event(event)

        post = Post(
            post_id="p_001", platform="weibo", post_type="original",
            text="测试内容", author_name="测试用户",
            event_id="ev_001",
            timestamp=datetime(2026, 5, 29, 10, 0, 0),
        )
        db.insert_post(post)

        posts = db.get_event_posts("ev_001")
        assert len(posts) == 1
        assert posts[0]["id"] == "p_001"
        assert posts[0]["platform"] == "weibo"

    def test_insert_duplicate_post(self, db):
        """重复插入应被 REPLACE (不抛异常, 不产生重复)"""
        event = Event(event_id="ev_001", name="测试")
        db.create_event(event)

        post = Post(post_id="p_dup", platform="weibo", post_type="original",
                    text="原内容", event_id="ev_001")
        db.insert_post(post)
        db.insert_post(post)  # 再次插入

        posts = db.get_event_posts("ev_001")
        assert len(posts) == 1

    def test_get_posts_empty_event(self, db):
        """空事件返回空列表"""
        event = Event(event_id="ev_empty", name="空")
        db.create_event(event)
        posts = db.get_event_posts("ev_empty")
        assert posts == []

    def test_platform_distribution(self, db_with_data, sample_event_id):
        """平台分布验证"""
        posts = db_with_data.get_event_posts(sample_event_id)
        platforms = {}
        for p in posts:
            plat = p.get("platform", "unknown")
            platforms[plat] = platforms.get(plat, 0) + 1
        assert platforms.get("weibo", 0) == 4
        assert platforms.get("sina", 0) == 4
        assert platforms.get("netease", 0) == 2
        assert platforms.get("zhihu", 0) == 2

    def test_post_count(self, db_with_data, sample_event_id):
        """事件帖子计数"""
        posts = db_with_data.get_event_posts(sample_event_id)
        assert len(posts) == 12

    def test_post_fields_complete(self, db_with_data, sample_event_id):
        """帖子字段应完整保留"""
        posts = db_with_data.get_event_posts(sample_event_id)
        weibo_001 = [p for p in posts if p["id"] == "wb_001"][0]
        assert weibo_001["platform"] == "weibo"
        assert "人工智能" in weibo_001["text"]
        assert weibo_001["author_name"] == "科技观察员"


class TestSentimentRecords:
    """情感记录存储"""

    def test_save_sentiment(self, db):
        """直接插入情感记录"""
        event = Event(event_id="ev_001", name="测试")
        db.create_event(event)
        post = Post(post_id="p_sent", platform="weibo", post_type="original",
                    text="情感测试文本", event_id="ev_001")
        db.insert_post(post)

        conn = sqlite3.connect(db.db_path)
        conn.execute("""
            INSERT INTO sentiment_records
            (post_id, sentiment_label, sentiment_score, arousal_score,
             emotions, model_version)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("p_sent", "正面", 0.85, 0.72,
              json.dumps({"喜悦": 0.8, "惊讶": 0.2}, ensure_ascii=False),
              "rules-v1"))
        conn.commit()

        rows = conn.execute(
            "SELECT * FROM sentiment_records WHERE post_id=?", ("p_sent",)
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][2] == "正面"


class TestEdgeStorage:
    """传播边存储"""

    def test_insert_edge(self, db):
        """边直接插入"""
        event = Event(event_id="ev_e", name="边测试")
        db.create_event(event)
        for pid in ["e_a", "e_b"]:
            post = Post(post_id=pid, platform="weibo", post_type="original",
                        text="x", event_id="ev_e")
            db.insert_post(post)

        conn = sqlite3.connect(db.db_path)
        conn.execute("""
            INSERT INTO propagation_edges
            (source_id, target_id, edge_type, confidence, timestamp_diff)
            VALUES (?, ?, ?, ?, ?)
        """, ("e_a", "e_b", "cite", 0.75, 600))
        conn.commit()
        conn.close()

        conn = sqlite3.connect(db.db_path)
        edges = conn.execute(
            "SELECT * FROM propagation_edges").fetchall()
        conn.close()
        assert len(edges) == 1
        assert edges[0][3] == "cite"
        assert edges[0][4] == 0.75
