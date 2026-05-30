"""配置加载器

从 config/config.yaml 读取系统配置，提供类型安全的访问接口。
不依赖 Hydra/OmegaConf，纯 YAML + dataclass 实现。

用法:
  from src.config import load_config, Config
  cfg = load_config()            # 自动找 config/config.yaml
  cfg = load_config("my.yaml")   # 自定义路径
  print(cfg.db_path)             # 'data/news_trace.db'
  print(cfg.weibo.max_pages)     # 10
"""

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# 配置数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class WeiboConfig:
    enabled: bool = True
    cookie_dir: str = "data/cookies/"
    max_pages_per_keyword: int = 10
    request_delay: int = 3
    max_retry: int = 3


@dataclass
class NewsConfig:
    enabled: bool = True
    sources: list[str] = field(default_factory=lambda: ["sina", "netease"])
    max_articles_per_source: int = 50
    request_delay: int = 2
    impersonate: str = "chrome"


@dataclass
class ScrapingConfig:
    headless: bool = True
    weibo: WeiboConfig = field(default_factory=WeiboConfig)
    news: NewsConfig = field(default_factory=NewsConfig)


@dataclass
class StorageConfig:
    db_path: str = "data/news_trace.db"
    image_dir: str = "data/images/"
    cache_ttl_hours: int = 24


@dataclass
class TextFeatureConfig:
    model_name: str = "hfl/chinese-roberta-wwm-ext"
    device: str = "cpu"
    max_length: int = 256
    sentiment_model: str = "uer/roberta-base-finetuned-jd-binary-chinese"


@dataclass
class ImageFeatureConfig:
    clip_model: str = "ViT-B/32"
    device: str = "cpu"
    hash_size: int = 8


@dataclass
class FeaturesConfig:
    text: TextFeatureConfig = field(default_factory=TextFeatureConfig)
    image: ImageFeatureConfig = field(default_factory=ImageFeatureConfig)


@dataclass
class PropagationConfig:
    cross_platform_threshold: float = 0.5
    temporal_validation: bool = True
    max_graph_depth: int = 10


@dataclass
class SourceTracingConfig:
    min_out_degree: int = 1
    time_window_hours: int = 24


@dataclass
class SentimentConfig:
    turning_point_threshold: float = 0.3
    min_posts_per_level: int = 3


@dataclass
class AnalysisConfig:
    propagation: PropagationConfig = field(default_factory=PropagationConfig)
    source_tracing: SourceTracingConfig = field(default_factory=SourceTracingConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)


@dataclass
class VisualizationConfig:
    graph_layout: str = "spring"
    max_nodes_display: int = 200
    platform_colors: dict = field(default_factory=lambda: {
        "weibo": "#0F4D92",
        "sina": "#E28E2C",
        "netease": "#42949E",
        "zhihu": "#9A4D8E",
    })


@dataclass
class Config:
    """系统全局配置 — 从 YAML 加载, 缺失字段使用默认值"""
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    visualization: VisualizationConfig = field(default_factory=VisualizationConfig)

    # ── 便捷属性 (兼容现有代码的硬编码引用) ─────────────────

    @property
    def db_path(self) -> str:
        return self.storage.db_path

    @property
    def image_dir(self) -> str:
        return self.storage.image_dir

    @property
    def cookie_dir(self) -> str:
        return self.scraping.weibo.cookie_dir

    @property
    def weibo(self) -> WeiboConfig:
        return self.scraping.weibo

    @property
    def news(self) -> NewsConfig:
        return self.scraping.news

    @property
    def propagation(self) -> PropagationConfig:
        return self.analysis.propagation

    @property
    def sentiment(self) -> SentimentConfig:
        return self.analysis.sentiment

    @property
    def source_tracing(self) -> SourceTracingConfig:
        return self.analysis.source_tracing


# ═══════════════════════════════════════════════════════════════
# 加载函数
# ═══════════════════════════════════════════════════════════════

def _find_config_path(path: Optional[str] = None) -> Path:
    """查找配置文件路径"""
    if path:
        p = Path(path)
        if p.exists():
            return p
        raise FileNotFoundError(f"Config file not found: {path}")

    # 自动查找: 当前目录 / 父目录 / 项目根
    search_dirs = [
        Path.cwd(),
        Path.cwd() / "config",
        Path(__file__).parent.parent / "config",  # 项目根/config/
    ]
    for d in search_dirs:
        for name in ["config.yaml", "config.yml"]:
            candidate = d / name
            if candidate.exists():
                return candidate

    raise FileNotFoundError(
        "Cannot find config.yaml. Searched: "
        + ", ".join(str(d) for d in search_dirs)
    )


def _deep_update(base: dict, override: dict) -> dict:
    """递归合并字典，override 覆盖 base"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _from_dict(cls, data: dict):
    """将字典转为 dataclass 实例, 仅传已知字段, 缺失字段使用 dataclass 默认值"""
    known = cls.__dataclass_fields__.keys()
    return cls(**{k: v for k, v in data.items() if k in known})


def load_config(path: Optional[str] = None,
                overrides: Optional[dict] = None) -> Config:
    """加载系统配置。

    Parameters
    ----------
    path: 配置文件路径, None=自动查找 config/config.yaml
    overrides: 可选的覆盖字典, 例如 {"storage": {"db_path": ":memory:"}}
    """
    config_path = _find_config_path(path)
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if overrides:
        raw = _deep_update(raw, overrides)

    scraping_raw = raw.get("scraping", {})
    scraping = ScrapingConfig(
        headless=scraping_raw.get("headless", True),
        weibo=_from_dict(WeiboConfig, scraping_raw.get("weibo", {})),
        news=_from_dict(NewsConfig, scraping_raw.get("news", {})),
    )
    features_raw = raw.get("features", {})
    features = FeaturesConfig(
        text=_from_dict(TextFeatureConfig, features_raw.get("text", {})),
        image=_from_dict(ImageFeatureConfig, features_raw.get("image", {})),
    )
    analysis_raw = raw.get("analysis", {})
    analysis = AnalysisConfig(
        propagation=_from_dict(PropagationConfig, analysis_raw.get("propagation", {})),
        source_tracing=_from_dict(SourceTracingConfig, analysis_raw.get("source_tracing", {})),
        sentiment=_from_dict(SentimentConfig, analysis_raw.get("sentiment", {})),
    )
    return Config(
        scraping=scraping,
        storage=_from_dict(StorageConfig, raw.get("storage", {})),
        features=features,
        analysis=analysis,
        visualization=_from_dict(VisualizationConfig, raw.get("visualization", {})),
    )


# ═══════════════════════════════════════════════════════════════
# 全局单例 (惰性加载)
# ═══════════════════════════════════════════════════════════════

_config: Optional[Config] = None


def get_config(path: Optional[str] = None) -> Config:
    """获取全局配置单例 (首次调用时加载)"""
    global _config
    if _config is None:
        _config = load_config(path)
    return _config


def reset_config():
    """重置全局配置 (测试用)"""
    global _config
    _config = None
