# 基于多源数据融合的新闻事件传播路径溯源与情感演化分析

> 大数据分析与挖掘课程论文 — 系统实现

## 项目结构

```
news-trace/
├── config/config.yaml          # 全局配置
├── src/
│   ├── scrapers/               # 数据采集 (Scrapling)
│   │   ├── base.py             #   爬虫基类
│   │   ├── weibo.py            #   微博爬虫 (StealthySession)
│   │   ├── news.py             #   新闻爬虫 (FetcherSession)
│   │   ├── cookie_manager.py   #   Cookie 池管理
│   │   └── selector_registry.py #  CSS/XPath 选择器注册表
│   ├── storage/                # 数据存储 (SQLite)
│   │   ├── models.py           #   数据模型
│   │   └── database.py         #   数据库操作
│   ├── features/               # 特征提取 (TODO)
│   ├── analysis/               # 图分析 (TODO)
│   ├── visualization/          # 可视化 (TODO)
│   └── pipeline.py             # 采集流水线入口
├── scripts/
│   ├── export_cookies.py       # Cookie 导出工具
│   └── scrape_demo.py          # 采集演示
├── notebooks/                  # Jupyter Notebooks (TODO)
├── data/                       # 数据目录
│   ├── cookies/                #   Cookie 文件
│   └── images/                 #   下载的图片
├── DESIGN.md                   # 完整系统设计文档
└── requirements.txt
```

## 快速开始

### 1. 安装 Scrapling

```bash
pip install "scrapling[fetchers]"
scrapling install  # 下载浏览器依赖（必须）
```

### 2. 准备微博 Cookie

```bash
# 方式一: 浏览器插件导出
# Chrome 安装 EditThisCookie → 登录 weibo.com → Export → 保存为 data/cookies/weibo_main.json

# 方式二: 命令行导出
python scripts/export_cookies.py --browser chrome --domain .weibo.com --output data/cookies/weibo_main.json
```

### 3. 运行采集

```bash
# 采集单个事件
python -m src.pipeline --keyword "东方甄选事件"

# 仅采集新闻网站
python -m src.pipeline --keyword "某热点事件" --sources sina,netease

# Demo 脚本
python scripts/scrape_demo.py --keyword "东方甄选"
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 爬虫 | Scrapling (StealthySession, FetcherSession) |
| 存储 | SQLite |
| NLP | Chinese-RoBERTa, Transformers |
| 图像 | Chinese-CLIP, PaddleOCR, OpenCV |
| 图计算 | NetworkX |
| 可视化 | Plotly, pyecharts |
