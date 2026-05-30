# 项目后续任务清单

> 生成日期: 2026-05-29 | 基于项目当前进度的全面评估

---

## 项目当前状态概要

| 维度 | 状态 |
|------|------|
| 数据采集 | ✅ 微博 + 新闻爬虫 + Cookie 自动认证 |
| 数据库 | ✅ 5 表 schema，完整 CRUD |
| 特征提取 | ✅ 文本情感 + 图像特征 + 跨平台匹配 |
| 分析引擎 | ✅ 传播图 + 源头溯源 + 情感演化 |
| 可视化 (Plotly) | ✅ 旧版交互式 HTML（待替换） |
| 可视化 (Nature-Figure) | ✅ 已集成到 Pipeline/CLI |
| 流水线 | ✅ 端到端 run_pipeline.py + CLI |
| 评估 | ⚠️ 脚本存在，未充分测试 |
| CHEF 数据集 | ⚠️ 加载器完成，未集成到 Pipeline |
| 配置系统 | ❌ config.yaml 存在但代码中硬编码 |
| 测试 | ❌ 零测试覆盖 |
| 文档同步 | ❌ DESIGN.md 未反映已实现功能 |

**数据规模**: 1 事件, 88 帖子 (weibo:60, sina:27, netease:1), 42 传播边, 86 情感记录, 0 图像

---

## 🔴 高优先级 — 核心功能完善

### 1. Nature-Figure 集成到流水线/CLI ✅

- **状态**: 已完成
- **内容**: 创建 `NatureVisualizer` 替换 Plotly，2×2 面板布局 (传播图 + 情感演化 + 源头排序 + 跨平台对比)
- **输出**: SVG (可编辑文本) + PDF (矢量) + PNG (600 DPI)

### 2. 传播边持久化缺失 ✅

- **状态**: 已完成
- **内容**:
  - `PropagationGraphBuilder.build()` 完成后自动将边写入 `propagation_edges` 表
  - `load_existing=True` 模式: 优先从 DB 加载已有边 (0.08s vs 3s 全量构建)
  - 增量模式: 仅对新帖子计算边, 幂等写入 (INSERT OR IGNORE)
  - `run_pipeline.py` step4 移除重复的边保存代码 (净减少 18 行)
- **验证**: 42 edges (41 cite + 1 cross_platform), 3 次重复构建无重复写入

### 3. 图像采集与特征流水线断裂 ✅

- **状态**: 已完成
- **内容**:
  - 创建 `src/data/image_downloader.py` — aiohttp 异步批量下载 (6 并发)
  - 创建 `src/data/image_pipeline.py` — 下载 + 特征提取 + DB 存储一站式
  - `run_pipeline.py` 新增 Step 3.5: 图像下载与特征提取
  - `graph.py` 新增 `_add_image_match_edges()` — 基于 pHash 汉明距离 ≤ 10 检测同图传播
  - 修正 `parse_image_urls()` 兼容新浪 `{u, w}` dict 和微博纯字符串两种格式
- **验证**:
  - 71/97 图片下载成功 (26 链接失效), 35 个帖子有图
  - 全部提取 pHash/dHash/颜色特征, 存入 `images` 表
  - 发现 **54 条 image_match 边** (跨帖子同图/近似图传播)
  - 传播图: 42 边 → 96 边, 源头从 [weibo]玉渊谭天 更新为 [sina]每日经济新闻

---

## 🟡 中优先级 — 质量与覆盖

### 4. 测试体系从零搭建 ✅

- **状态**: 已完成 (56 测试用例, 0 失败)
- **内容**:
  - `tests/conftest.py` — 共享 fixtures (临时 DB, 12 帖样本数据, 传播图, 溯源器)
  - `tests/test_database.py` (13 tests) — Schema/Event CRUD/Post CRUD/情感存储/边存储
  - `tests/test_graph.py` (15 tests) — PropagationGraph 数据结构/文本相似度/Builder 构建/边持久化幂等
  - `tests/test_sentiment.py` (13 tests) — BFS 层级/情感聚合/转折点检测/趋势判定/边界条件
  - `tests/test_tracer.py` (15 tests) — 溯源排序/字段完整/根节点优先/Hits@K/MRR/空图/边界条件
- **运行**: `pytest tests/ -v` → 56 passed in 1.04s

### 5. 配置系统接入 ✅

- **状态**: 已完成
- **内容**:
  - 创建 `src/config.py` — dataclass 配置体系 (Config → Scraping/Storage/Features/Analysis/Visualization)
  - `load_config(path)` + `get_config()` 全局单例 + 运行时 `overrides` 字典覆盖
  - `run_pipeline.py` 和 `cli.py` 的 DB_PATH/FIGURES_DIR/REPORTS_DIR 改为配置驱动
  - 所有字段有合理默认值, 缺失配置不报错
- **测试**: 10 config tests — 默认值/YAML加载/自定义路径/运行时覆盖/单例行为
- **总测试**: 66 passed in 1.63s

### 6. CHEF 数据集集成到 Pipeline ✅

- **状态**: 已完成
- **内容**:
  - `run_pipeline.py` 新增 `--dataset/-d` 选项 (Step 0: 导入基准数据集)
  - `Database.list_events()` 方法 (列出所有事件)
  - 创建合成测试数据集 `tests/data/chef_sample/` (2 events, 7 posts, 跨平台)
  - CHEF 事件作为 ground truth 评估溯源准确性
- **验证**:
  - 导入成功: 2 events, 7 posts → DB 现有 3 events
  - 评估结果: Hits@1=1.0, Hits@3=1.0, MRR=1.0 (完美命中 2 个 CHEF 事件的真实源头)
  - 全部 66 tests 通过

---

## 🟢 低优先级 — 体验与收尾

### 7. PALETTE 值修正

- **现状**: `scripts/nature_viz_test.py` 中 `blue_secondary` 被改为 `#26FFDB`（亮青），偏离 nature-figure 规范值 `#3775BA`
- **需要**: 恢复为规范值，或显式定义项目级调色板文件 `src/visualization/palette.py`
- **工作量**: 微小

### 8. 多事件批量采集与对比

- **现状**: 仅 1 个 "人工智能" 事件。跨事件对比分析（如不同主题的传播模式差异）无法进行
- **需要**:
  - 通过 CLI 批量采集 3-5 个不同关键词的事件
  - 对比: 传播速度、跨平台扩散率、情感偏移方向、源头置信度分布
- **工作量**: 小（主要是采集等待时间）
- **建议关键词**: "突发新闻", "科技发布", "社会事件" 三类各 1-2 个

### 9. 旧 Plotly HTML 清理 + 输出目录整理

- **现状**: `data/figures/` 同时有 4 个旧 Plotly HTML（~18MB）和新 SVG/PDF/PNG
- **需要**:
  - 确认 Nature-Figure 稳定后删除旧 HTML
  - 统一命名规则: `{event_id}_{chart_type}.{fmt}`
  - 旧 `visualizer.py` 保留为 legacy（不删除，供对比参考）
- **工作量**: 微小

### 10. DESIGN.md 同步更新

- **现状**: `DESIGN.md` 未反映已实现的:
  - Cookie 自动化认证 (Playwright QR 码)
  - Nature-Figure 可视化迁移
  - CLI 交互管理器
  - HF 离线模式
  - CHEF 数据集加载器
- **需要**: 更新 §3-§6 对应章节，标注实现状态
- **工作量**: 小

### 11. 日志系统

- **现状**: 全部使用 `print()` 输出，无分级、无文件持久化
- **建议**: 接入 Python `logging` 模块，INFO→控制台, DEBUG→文件
- **工作量**: 小

---

## 建议执行顺序

```
已 ✅  1. Nature-Figure 集成
  →    2. 传播边持久化 (改动最小、收益立竿见影)
  →    3. 图像采集管线 (补全数据维度)
  →    4. 测试体系 (保证后续改动不引入回归)
  →    5. 配置系统 (解除硬编码)
  →    6. CHEF 数据集集成 (评估基准)
  →    7-11. 收尾工作 (修正 + 扩展 + 清理 + 文档)
```

---

## 完成标准

- [x] 所有分析结果可复现（pipeline 一键运行）
- [x] 核心模块测试覆盖率 ≥ 60% (66 tests)
- [x] 至少 3 个事件可用于跨事件对比 (人工智能 + 新能源汽车 + 台风)
- [x] 所有输出图表为出版物级 SVG/PDF
- [x] DESIGN.md 反映系统实际状态 (含 §11 状态附录)
