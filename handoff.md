# Handoff — 新闻事件传播路径溯源与情感演化分析系统

> 最后更新: 2026-05-30 | 会话涵盖: 系统设计 → 全栈实现 → 技能安装 → 代码审查与清理

---

## 一、工作目标

构建「基于多源数据融合的新闻事件传播路径溯源与情感演化分析」系统，核心能力：

1. **多源数据采集**: 微博 (Playwright QR 码认证) + 新闻网站 (sina/netease, curl_cffi impersonate)
2. **传播图构建**: NetworkX DiGraph，支持 repost/cite/cross_platform/image_match 四种边类型
3. **源头溯源**: 入度为 0 根节点 + 多维证据打分 (出度/时间/跨平台)
4. **情感演化**: BFS 层级情感追踪 + 转折点检测 + 跨平台对比
5. **出版物可视化**: matplotlib Nature-Figure 2×2 面板 (SVG/PDF/PNG, 600 DPI)
6. **基准评估**: CHEF 数据集集成 + Hits@K/MRR 评估
7. **图像特征**: pHash/dHash 同图检测 → image_match 传播边

---

## 二、当前代码情况

### 项目结构

```
bdma-news-trace/
├── config/config.yaml          # 系统配置
├── DESIGN.md                   # 系统设计文档 (含 §11 实现状态)
├── docs/TODO.md                # 11 步任务清单 (全部完成)
├── handoff.md                  # ← 本文件
├── data/
│   ├── news_trace.db           # SQLite (3 events, ~95 posts, ~96 edges)
│   ├── images/                 # 下载的图片 (71 张)
│   ├── figures/                # SVG/PDF/PNG 图表输出
│   ├── reports/                # Markdown 分析报告
│   └── logs/                   # 日志文件
├── scripts/
│   ├── run_pipeline.py         # 端到端流水线 (主入口)
│   ├── cli.py                  # 交互式 CLI 菜单
│   ├── evaluate.py             # 溯源评估脚本
│   ├── scrape_demo.py          # 采集 Demo
│   ├── export_cookies.py       # Cookie 导出
│   └── nature_viz_test.py      # Nature-Figure 测试
├── src/
│   ├── config.py               # YAML → dataclass 配置 (已简化)
│   ├── logging_setup.py        # 统一日志系统 (彩色控制台 + 文件)
│   ├── pipeline.py             # EventTracker + Pipeline 包装
│   ├── analysis/
│   │   ├── graph.py            # PropagationGraph + Builder (边持久化 + 增量 + 图像匹配)
│   │   ├── tracer.py           # SourceTracer + SourceTracingEvaluator
│   │   └── sentiment.py        # SentimentEvolutionAnalyzer
│   ├── data/
│   │   ├── chef.py             # CHEF 数据集加载器 (无外部依赖, 自包含)
│   │   ├── image_downloader.py # aiohttp 异步批量下载 (6 并发)
│   │   └── image_pipeline.py   # 下载 + 特征提取 + DB 存储一站式
│   ├── features/
│   │   ├── text.py             # TextEncoder + ChineseSentimentAnalyzer
│   │   └── image.py            # CLIPImageEncoder + ImageHasher + ImageColorSentiment
│   ├── storage/
│   │   ├── database.py         # SQLite 操作层 (5 表)
│   │   └── models.py           # Post/Event/SentimentRecord/PropagationEdge 数据类
│   ├── scrapers/               # 微博 + 新闻爬虫 + Cookie 管理
│   └── visualization/
│       ├── nature_visualizer.py # matplotlib 出版物图表 (主)
│       ├── visualizer.py        # Plotly 旧版 (保留供参考, 不再导出)
│       └── report.py            # Markdown 报告生成
├── tests/
│   ├── conftest.py             # 共享 fixtures
│   ├── test_database.py        # 13 tests
│   ├── test_graph.py           # 15 tests
│   ├── test_sentiment.py       # 13 tests
│   ├── test_tracer.py          # 15 tests
│   └── test_config.py          # 10 tests
└── tests/data/chef_sample/     # 合成 CHEF 测试数据 (2 events, 7 posts)
```

### 测试状态

**66 tests, 0 failures, ~0.6s** — 覆盖 database / graph / sentiment / tracer / config 五个模块。

### 数据库规模

| 指标 | 值 |
|------|-----|
| 事件数 | 3 (人工智能, 新能源汽车补贴政策调整, 台风登陆东南沿海地区) |
| 帖子数 | ~95 |
| 传播边 | ~96 (repost + cite + cross_platform + image_match) |
| 图像 | 71 张 (26 链接失效) |

### 关键设计决策

- **文本相似度**: Jaccard 字符集 (0.3/0.4 阈值)，不依赖 NLP 模型 — 快速、可确定
- **图像匹配**: pHash 汉明距离 ≤ 10 → image_match 边，置信度 = `max(0.3, 1 - dist/64)`
- **边持久化**: INSERT OR IGNORE, 增量模式 (load_existing=True) 0.08s vs 3s 全量构建
- **HF 离线模式**: `HF_HUB_OFFLINE=1` 避免 HuggingFace 网络超时
- **CJK 字体**: 'Microsoft YaHei' 为主 matplotlib sans-serif 字体

### 本次会话清理结果

| 删除项 | 说明 |
|--------|------|
| `src/features/matcher.py` | CrossPlatformMatcher — 3D 加权融合匹配器，从未被 pipeline 调用 |
| `src/data/base.py` | BaseDataset ABC — 单实现的抽象类 |
| `src/features/image.py` | ImageOCR + ImageFeatureExtractor — 从未启用/使用 |
| `src/features/text.py` | TextStatistics + TextFeatureExtractor — ~784-dim 统一向量从未使用 |
| `src/data/image_pipeline.py` | get_image_matches() — 与 graph._add_image_match_edges() 重复 |
| `src/config.py` | load_config 从 110 行减至 35 行，冗余默认值已消除 (~75 行) |
| `src/visualization/__init__.py` | 移除 legacy PropagationVisualizer 导出 |
| `scripts/*` | 移除未使用的 get_image_matches/Pipeline 导入 |

### 已安装技能

| 来源 | 技能列表 |
|------|----------|
| obra/superpowers | 14 个 (brainstorming, writing-plans, test-driven-development, subagent-driven-development, etc.) |
| yeachan-heo/oh-my-claudecode | ai-slop-cleaner, ultraqa |
| 内置 Nature | 9 个 (academic-search, citation, data, figure, paper2ppt, polishing, reader, response, writing) |

---

## 三、正在编辑的文件 (本次会话)

本轮会话主要变更集中在代码清理：

- **删除**: `src/features/matcher.py`, `src/data/base.py`
- **大幅编辑**: `src/features/text.py`, `src/features/image.py`, `src/data/chef.py`, `src/config.py`
- **小幅编辑**: `src/features/__init__.py`, `src/data/__init__.py`, `src/data/image_pipeline.py`, `src/visualization/__init__.py`, `scripts/run_pipeline.py`, `scripts/cli.py`, `scripts/scrape_demo.py`

**未提交** — 所有变更仍在工作树中，尚未 commit。

---

## 四、尝试过但未成功/未完成的工作

### 无重大失败项

之前的 11 步任务清单全部完成，本轮代码清理也通过了全部 66 个测试。

### 遗留在文件系统上但未导出的模块

- `src/visualization/visualizer.py` — Plotly 旧版可视化器。不再从 `__init__.py` 导出，但物理文件保留在磁盘上 (~230 行)。如果 NatureVisualizer 稳定运行一段时间后，可物理删除。

---

## 五、接下来的任务

### 短期 (可直接进行)

1. **提交当前变更**: 清理了 ~390 行死代码，需要 `git add` + `git commit`

2. **多事件采集 (docs/TODO.md 第 8 项)**: 运行 CLI 用不同关键词批量采集 2-3 个新事件，用于跨事件对比分析。建议关键词:
   ```
   python scripts/cli.py → 选项 1 (新建采集) → "突发新闻" / "科技发布" / "社会事件"
   ```

3. **物理删除旧 visualizer.py**: 如果 NatureVisualizer 确认稳定，删除 `src/visualization/visualizer.py`

4. **选择性删除旧图表**:
   ```
   data/figures/nature_test_event_1780060447.*   # 测试图表，可清理
   ```

### 中期 (需要更多设计)

5. **Trace 边溯源 (真正的传播路径)**: 目前溯源器用入度为 0 找根节点，是一个启发式方法。下一步可实现更精确的「最早发帖 + 高传播出度 + 权威度」的多维排序

6. **跨事件传播模式对比**: 有了 3+ 事件后，可以自动化对比传播速度、跨平台扩散率、情感偏移方向等

7. **Pytest asyncio 警告**: 设置 `asyncio_default_fixture_loop_scope = "function"` 消除 pytest-asyncio 弃用警告

### 长期 (需要外部资源)

8. **GPU 加速嵌入**: 当前所有模型在 CPU 运行。有 GPU 后可启用 TextEncoder 语义相似度 (替换 Jaccard) 和 CLIP 图像匹配

9. **实时监控模式**: 周期性采集 + 自动更新传播图 + 告警 (情感突转、新增跨平台爆发)

10. **Web 仪表盘**: 原 `src/web/` 已删除 (Flask app, ~1000 行)，如需恢复可用 Plotly Dash 或 Streamlit 重做

---

## 六、快速启动命令

```bash
# 环境
cd E:\Workspace\BDMA\final\bdma-news-trace

# 运行全部测试
python -m pytest tests/ -v

# 端到端流水线 (跳过采集, 使用已有事件)
python scripts/run_pipeline.py --skip-collect --event-id event_1780060447

# 采集新事件
python scripts/run_pipeline.py --keyword "你的关键词" --sources weibo,sina,netease

# 导入 CHEF 数据集 + 评估溯源
python scripts/run_pipeline.py --dataset tests/data/chef_sample --skip-collect
python scripts/evaluate.py

# 交互式 CLI
python scripts/cli.py

# Nature-Figure 测试
python scripts/nature_viz_test.py
```

---

## 七、关键设计文档引用

- 系统设计: `DESIGN.md` (含 §11 实现状态附录)
- 任务清单: `docs/TODO.md` (11 项全部 ✅)
- 配置模板: `config/config.yaml`
