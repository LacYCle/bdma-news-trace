"""共享 fixtures — 所有测试模块共用"""

import os
import sys
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import networkx as nx

# 确保项目根在 sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 设置 HF 离线模式避免网络延迟
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from src.storage.models import Post, Event, SentimentRecord
from src.storage.database import Database
from src.analysis.graph import PropagationGraph, PropagationGraphBuilder


# ═══════════════════════════════════════════════════════════════
# 时间工具
# ═══════════════════════════════════════════════════════════════

BASE_TIME = datetime(2026, 5, 29, 10, 0, 0)


def ts(offset_minutes: int = 0) -> datetime:
    return BASE_TIME + timedelta(minutes=offset_minutes)


# ═══════════════════════════════════════════════════════════════
# 样本数据 fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def sample_posts_raw():
    """12 条模拟帖子 (dict 格式, 用于图构建)"""
    return [
        # 微博源头 + 转发
        {"id": "wb_001", "post_id": "wb_001", "platform": "weibo",
         "text": "突发!人工智能新突破引发全球关注", "author_name": "科技观察员",
         "parent_id": None, "timestamp": ts(0),
         "engagement_count": 500, "image_urls": json.dumps(
             ["https://example.com/img_a1.jpg", "https://example.com/img_a2.jpg"])},
        {"id": "wb_002", "post_id": "wb_002", "platform": "weibo",
         "text": "转发:人工智能新突破值得关注 #AI", "author_name": "路人甲",
         "parent_id": "wb_001", "timestamp": ts(10),
         "engagement_count": 50, "image_urls": "[]"},
        {"id": "wb_003", "post_id": "wb_003", "platform": "weibo",
         "text": "这次AI进步太震撼了,完全不同表述", "author_name": "科技迷",
         "parent_id": "wb_001", "timestamp": ts(20),
         "engagement_count": 120, "image_urls": json.dumps(
             ["https://example.com/img_a1.jpg"])},
        {"id": "wb_004", "post_id": "wb_004", "platform": "weibo",
         "text": "独立发布的评论:人工智能未来在哪", "author_name": "思考者",
         "parent_id": None, "timestamp": ts(30),
         "engagement_count": 30, "image_urls": "[]"},

        # 新浪新闻
        {"id": "sina_001", "post_id": "sina_001", "platform": "sina",
         "text": "人工智能技术取得重大突破 引发全球科技界热议",
         "author_name": "每日科技", "parent_id": None, "timestamp": ts(5),
         "engagement_count": 200, "image_urls": json.dumps(
             [{"u": "https://example.com/img_b1.png", "w": 550}])},
        {"id": "sina_002", "post_id": "sina_002", "platform": "sina",
         "text": "AI新突破:技术变革正在加速来临",
         "author_name": "科技前线", "parent_id": None, "timestamp": ts(15),
         "engagement_count": 80, "image_urls": "[]"},
        {"id": "sina_003", "post_id": "sina_003", "platform": "sina",
         "text": "深度解读:人工智能如何改变未来产业格局",
         "author_name": "经济观察", "parent_id": None, "timestamp": ts(25),
         "engagement_count": 150, "image_urls": json.dumps(
             [{"u": "https://example.com/img_b1.png", "w": 550}])},
        {"id": "sina_004", "post_id": "sina_004", "platform": "sina",
         "text": "完全不相关的健康资讯报道内容",
         "author_name": "健康频道", "parent_id": None, "timestamp": ts(35),
         "engagement_count": 10, "image_urls": "[]"},

        # 网易
        {"id": "nt_001", "post_id": "nt_001", "platform": "netease",
         "text": "人工智能领域迎来里程碑式突破",
         "author_name": "科技频道", "parent_id": None, "timestamp": ts(12),
         "engagement_count": 300, "image_urls": "[]"},
        {"id": "nt_002", "post_id": "nt_002", "platform": "netease",
         "text": "AI技术新进展引发各界关注",
         "author_name": "深度报道", "parent_id": None, "timestamp": ts(22),
         "engagement_count": 60, "image_urls": "[]"},

        # 知乎
        {"id": "zh_001", "post_id": "zh_001", "platform": "zhihu",
         "text": "如何看待最新的人工智能技术突破?",
         "author_name": "问答达人", "parent_id": None, "timestamp": ts(8),
         "engagement_count": 400, "image_urls": "[]"},
        {"id": "zh_002", "post_id": "zh_002", "platform": "zhihu",
         "text": "作为从业者分析一下这次AI突破的技术细节",
         "author_name": "AI研究员", "parent_id": None, "timestamp": ts(18),
         "engagement_count": 250, "image_urls": "[]"},
    ]


@pytest.fixture
def sample_event_id():
    return "test_event_001"


# ═══════════════════════════════════════════════════════════════
# 数据库 fixtures (使用实际 Database API)
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def temp_db_path():
    """临时 SQLite 数据库文件路径"""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_bdma_")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def db(temp_db_path):
    """初始化的 Database (schema 自动创建)"""
    return Database(db_path=temp_db_path)


@pytest.fixture
def db_with_data(db, sample_posts_raw, sample_event_id):
    """已填充样本数据的 Database"""
    event = Event(
        event_id=sample_event_id,
        name="测试事件: AI突破",
        keywords=["人工智能", "AI"],
        first_seen=ts(0),
        last_updated=ts(35),
    )
    db.create_event(event)

    for p in sample_posts_raw:
        try:
            img_urls_raw = p.get("image_urls", "[]")
            if isinstance(img_urls_raw, str):
                try:
                    img_urls = json.loads(img_urls_raw)
                except (json.JSONDecodeError, TypeError):
                    img_urls = []
            else:
                img_urls = img_urls_raw

            post = Post(
                post_id=p["id"],
                platform=p["platform"],
                post_type="original" if not p.get("parent_id") else "repost",
                text=p["text"],
                image_urls=img_urls,
                author_name=p.get("author_name", ""),
                parent_id=p.get("parent_id") or "",
                event_id=sample_event_id,
                timestamp=p["timestamp"],
                engagement_count=p.get("engagement_count", 0),
            )
            db.insert_post(post)
        except Exception:
            pass
    return db


# ═══════════════════════════════════════════════════════════════
# 传播图 fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def pg_empty():
    """空传播图"""
    return PropagationGraph(event_id="empty_event")


@pytest.fixture
def pg_with_nodes(sample_posts_raw):
    """仅有节点的传播图 (12 节点)"""
    pg = PropagationGraph(event_id="test_event_001")
    for post in sample_posts_raw:
        pg.add_post_node(post)
    return pg


@pytest.fixture
def pg_with_edges(pg_with_nodes, sample_posts_raw):
    """含完整边的传播图 — 通过构建器逻辑模拟"""
    pg = pg_with_nodes
    posts = sample_posts_raw

    post_map = {p.get("post_id") or p.get("id", ""): p for p in posts}
    for post in posts:
        pid = post.get("post_id") or post.get("id", "")
        parent_id = post.get("parent_id")
        if parent_id and parent_id in post_map:
            pg.add_edge(parent_id, pid, edge_type="repost")

    # 文本相似引用 (同平台)
    posts_by_plat = {}
    for p in posts:
        posts_by_plat.setdefault(p.get("platform", "unknown"), []).append(p)

    for plat, plat_posts in posts_by_plat.items():
        for i, pa in enumerate(plat_posts):
            for pb in plat_posts[i + 1:]:
                sim = PropagationGraphBuilder._text_similarity(
                    pa.get("text", ""), pb.get("text", ""))
                if sim > 0.3:
                    t_a = pg._normalize_time(pa.get("timestamp"))
                    t_b = pg._normalize_time(pb.get("timestamp"))
                    if t_a and t_b:
                        src, tgt = (pa, pb) if t_a <= t_b else (pb, pa)
                        sid = src.get("post_id") or src.get("id", "")
                        tid = tgt.get("post_id") or tgt.get("id", "")
                        pg.add_edge(sid, tid, edge_type="cite", confidence=sim)

    return pg


# ═══════════════════════════════════════════════════════════════
# 溯源 fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def tracer():
    from src.analysis.tracer import SourceTracer
    return SourceTracer()


@pytest.fixture
def candidates(tracer, pg_with_edges):
    """对样本图运行溯源"""
    return tracer.trace(pg_with_edges, top_k=5)
