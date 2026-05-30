"""配置加载器测试"""

import os
import tempfile

import pytest
from src.config import (
    Config, load_config, get_config, reset_config,
    WeiboConfig, NewsConfig, StorageConfig,
    TextFeatureConfig, PropagationConfig, SentimentConfig,
)


class TestConfigDefaults:
    """默认配置"""

    def test_default_config_has_all_fields(self):
        """默认 Config 应有所有子配置"""
        cfg = Config()
        assert cfg.scraping is not None
        assert cfg.storage is not None
        assert cfg.features is not None
        assert cfg.analysis is not None
        assert cfg.visualization is not None

    def test_convenience_properties(self):
        """便捷属性应正确代理"""
        cfg = Config()
        assert cfg.db_path == "data/news_trace.db"
        assert cfg.image_dir == "data/images/"
        assert cfg.cookie_dir == "data/cookies/"
        assert cfg.weibo.max_pages_per_keyword == 10
        assert cfg.propagation.cross_platform_threshold == 0.5
        assert cfg.sentiment.turning_point_threshold == 0.3

    def test_weibo_defaults(self):
        wb = WeiboConfig()
        assert wb.enabled is True
        assert wb.max_pages_per_keyword == 10
        assert wb.request_delay == 3

    def test_news_defaults(self):
        n = NewsConfig()
        assert n.enabled is True
        assert "sina" in n.sources
        assert "netease" in n.sources

    def test_storage_defaults(self):
        s = StorageConfig()
        assert s.db_path == "data/news_trace.db"
        assert s.cache_ttl_hours == 24


class TestConfigLoad:
    """从 YAML 加载"""

    def test_load_from_project_config(self):
        """应成功加载项目 config/config.yaml"""
        cfg = load_config()
        assert cfg.db_path == "data/news_trace.db"
        assert cfg.weibo.max_pages_per_keyword == 10
        assert cfg.news.sources == ["sina", "netease"]
        assert cfg.features.text.model_name == "hfl/chinese-roberta-wwm-ext"

    def test_load_with_overrides(self):
        """运行时覆盖应生效"""
        cfg = load_config(overrides={
            "storage": {"db_path": "/tmp/test_override.db"},
            "scraping": {"weibo": {"max_pages_per_keyword": 5}},
        })
        assert cfg.db_path == "/tmp/test_override.db"
        assert cfg.weibo.max_pages_per_keyword == 5
        # 未覆盖的保持原值
        assert cfg.news.sources == ["sina", "netease"]

    def test_load_custom_path(self):
        """自定义路径加载"""
        import yaml
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump({
                "storage": {"db_path": "custom/test.db"},
                "scraping": {"weibo": {"max_pages_per_keyword": 3}},
            }, f)
            tmp_path = f.name

        try:
            cfg = load_config(path=tmp_path)
            assert cfg.db_path == "custom/test.db"
            assert cfg.weibo.max_pages_per_keyword == 3
            # 未定义的字段使用默认值
            assert cfg.news.sources == ["sina", "netease"]
        finally:
            os.unlink(tmp_path)


class TestConfigSingleton:
    """全局单例"""

    def test_get_config_returns_same_instance(self):
        reset_config()
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2

    def test_reset_config(self):
        get_config()  # 初始化
        assert get_config() is not None
        reset_config()
        # reset 后下一次 get_config 应重新加载
        c = get_config()
        assert c is not None
