"""统一数据模型"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Post:
    """跨平台统一帖子/文章模型"""
    post_id: str
    platform: str           # 'weibo', 'sina', 'netease', 'zhihu'
    post_type: str          # 'original', 'repost', 'article'
    text: str
    images: list[str] = field(default_factory=list)  # 本地图片路径
    image_urls: list[str] = field(default_factory=list)  # 原始 URL
    author_id: str = ""
    author_name: str = ""
    parent_id: str = ""     # 被转发/引用的帖子 ID
    repost_chain: list[str] = field(default_factory=list)
    event_id: str = ""
    url: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    engagement_count: int = 0
    repost_count: int = 0
    comment_count: int = 0
    like_count: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class NewsArticle:
    """新闻文章模型（采集阶段使用，入库前转为 Post）"""
    article_id: str
    title: str
    content: str
    images: list[str] = field(default_factory=list)
    source: str = ""
    url: str = ""
    publish_time: datetime = field(default_factory=datetime.now)
    category: str = ""


@dataclass
class Event:
    """新闻事件模型"""
    event_id: str
    name: str
    keywords: list[str] = field(default_factory=list)
    first_seen: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    post_count: int = 0
    source_candidates: list[str] = field(default_factory=list)


@dataclass
class PropagationEdge:
    """传播边模型"""
    source_id: str
    target_id: str
    edge_type: str          # 'repost', 'cite', 'cross_platform', 'image_match'
    confidence: float = 1.0
    timestamp_diff: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class SentimentRecord:
    """情感分析记录"""
    post_id: str
    sentiment_label: str    # 'anger','sadness','surprise','joy','fear','disgust','neutral'
    sentiment_score: float  # -1 (负面) 到 +1 (正面)
    arousal_score: float    # 0-1 情感唤起度
    emotions: dict = field(default_factory=dict)
    model_version: str = ""
