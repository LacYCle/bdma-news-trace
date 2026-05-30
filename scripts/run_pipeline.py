"""端到端新闻溯源流水线 — 一键完成全部 7 步

用法:
  python scripts/run_pipeline.py --keyword "东方甄选事件"
  python scripts/run_pipeline.py --keyword "芯片" --sources weibo,sina,netease
  python scripts/run_pipeline.py --keyword "A股" --skip-collect  # 跳过采集,使用已有数据

流程:
  Step 1: 事件发现与创建
  Step 2: 全平台数据采集
  Step 3: 文本特征提取 (情感分析)
  Step 4: 传播图构建
  Step 5: 源头溯源
  Step 6: 情感演化分析
  Step 7: 可视化 + 报告生成
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime

# 离线模式避免 HuggingFace 网络超时阻塞 (25s+ 重试)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_PROJECT_ROOT)
sys.path.insert(0, _PROJECT_ROOT)

from src.config import load_config

# 加载配置
_cfg = load_config()
DB_PATH = os.path.join(_PROJECT_ROOT, _cfg.db_path) if not os.path.isabs(_cfg.db_path) else _cfg.db_path
FIGURES_DIR = os.path.join(_PROJECT_ROOT, "data", "figures")
REPORTS_DIR = os.path.join(_PROJECT_ROOT, "data", "reports")

from src.pipeline import Pipeline, EventTracker
from src.storage.database import Database
from src.storage.models import SentimentRecord
from src.features.text import ChineseSentimentAnalyzer
from src.analysis.graph import PropagationGraphBuilder
from src.analysis.tracer import SourceTracer
from src.analysis.sentiment import SentimentEvolutionAnalyzer
from src.visualization.nature_visualizer import NatureVisualizer
from src.visualization.report import ReportGenerator
from src.data.image_pipeline import run_image_pipeline


def step_extract_features(db: Database, event_id: str) -> dict:
    """Step 3: 提取所有帖子的文本情感特征"""
    print("\n" + "=" * 60)
    print("Step 3: 文本特征提取 (情感分析)")
    print("=" * 60)

    posts = db.get_event_posts(event_id)
    if not posts:
        print("[Step3] 无帖子数据，跳过特征提取")
        return {"total": 0, "with_sentiment": 0}

    analyzer = ChineseSentimentAnalyzer()

    sentiment_count = 0
    for post in posts:
        text = post.get("text", "")
        if not text:
            continue
        try:
            result = analyzer.analyze(text)
            record = SentimentRecord(
                post_id=post["id"],
                sentiment_label=result.get("dominant", "中性"),
                sentiment_score=result.get("polarity", 0.0),
                arousal_score=result.get("arousal", 0.0),
                emotions=result.get("emotions", {}),
                model_version="rule-v1",
            )
            db.insert_sentiment(record)
            sentiment_count += 1
        except Exception as e:
            print(f"[Step3] 情感分析失败 {post['id'][:12]}: {e}")

    print(f"[Step3] 完成: {sentiment_count}/{len(posts)} 条帖子已标注情感")
    return {"total": len(posts), "with_sentiment": sentiment_count}


def step_extract_images(event_id: str, skip_download: bool = False) -> dict:
    """Step 3.5: 图像下载与特征提取"""
    print("\n" + "=" * 60)
    print("Step 3.5: 图像下载与特征提取")
    print("=" * 60)

    result = run_image_pipeline(
        event_id=event_id, db_path=DB_PATH,
        save_root=os.path.join(_PROJECT_ROOT, "data", "images"),
        skip_download=skip_download,
    )
    print(f"[Step3.5] 下载 {result['downloaded']}, "
          f"特征提取 {result['extracted']}, "
          f"存储 {result['stored']}, 跳过 {result['skipped']}")
    return result


def step_build_graph(db: Database, event_id: str):
    """Step 4: 构建传播图"""
    print("\n" + "=" * 60)
    print("Step 4: 传播图构建")
    print("=" * 60)

    builder = PropagationGraphBuilder(db_path=db.db_path)
    pg = builder.build(event_id)
    return pg


def step_trace_source(pg, top_k: int = 5) -> list[dict]:
    """Step 5: 源头溯源"""
    print("\n" + "=" * 60)
    print("Step 5: 源头溯源")
    print("=" * 60)

    tracer = SourceTracer()
    candidates = tracer.trace(pg, top_k=top_k)

    if candidates:
        top = candidates[0]
        print(f"[Step5] 最可能源头: [{top['platform']}] {top['author']} "
              f"(置信度 {top['confidence']:.3f})")
        print(f"[Step5] 证据: 直接转发={top['evidence']['direct_reposts']}, "
              f"跨平台传播={top['evidence']['cross_platform_spread']}")
    else:
        print("[Step5] 未找到候选源头")

    return candidates


def step_analyze_sentiment(pg, candidates: list[dict]) -> dict:
    """Step 6: 情感演化分析"""
    print("\n" + "=" * 60)
    print("Step 6: 情感演化分析")
    print("=" * 60)

    analyzer = SentimentEvolutionAnalyzer()

    # 沿最可能源头追踪
    path_result = {}
    if candidates:
        source_id = candidates[0]["post_id"]
        path_result = analyzer.analyze_path(pg, source_id)
        print(f"[Step6] 传播链深度: {len(path_result.get('evolution', []))} 层")
        print(f"[Step6] 整体趋势: {path_result.get('overall_trend', 'N/A')}")
        turning = path_result.get("turning_points", [])
        if turning:
            for tp in turning:
                print(f"[Step6] 情感转折: L{tp['from_level']}→L{tp['to_level']} "
                      f"{tp['direction']} Δ={tp['magnitude']:.3f}")

    # 跨平台对比
    cross = analyzer.cross_platform_sentiment(pg)
    if cross:
        print(f"[Step6] 跨平台情感差异:")
        for plat, stats in cross.items():
            print(f"  {plat}: 极性={stats['avg_polarity']:+.3f}, "
                  f"唤起度={stats['avg_arousal']:.3f}, "
                  f"主导={stats['dominant_emotion']}")

    return {
        "evolution": path_result.get("evolution", []),
        "turning_points": path_result.get("turning_points", []),
        "overall_trend": path_result.get("overall_trend", ""),
        "cross_platform": cross,
    }


def step_visualize_and_report(pg, candidates: list[dict],
                              sentiment_result: dict,
                              event_name: str, event_id: str,
                              save: bool = True) -> str:
    """Step 7: 生成可视化图表和分析报告"""
    print("\n" + "=" * 60)
    print("Step 7: 可视化 & 报告生成")
    print("=" * 60)

    visualizer = NatureVisualizer(output_dir=FIGURES_DIR)
    figures = visualizer.generate_all(pg, candidates, sentiment_result, save=save)

    reporter = ReportGenerator(output_dir=REPORTS_DIR)
    report = reporter.generate(
        event_name=event_name, event_id=event_id,
        pg=pg, trace_result=candidates,
        sentiment_result=sentiment_result,
        figures=figures if save else None,
    )
    if save:
        reporter.save(report, event_id)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="新闻传播溯源端到端流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--keyword", "-k", type=str, default=None,
                        help="搜索关键词 (采集模式必填)")
    parser.add_argument("--event-id", "-e", type=str, default=None,
                        help="直接指定已有事件 ID (配合 --skip-collect)")
    parser.add_argument("--sources", "-s", type=str, default="weibo,sina,netease",
                        help="数据源,逗号分隔")
    parser.add_argument("--max-pages", "-p", type=int, default=5,
                        help="微博最大翻页数")
    parser.add_argument("--skip-collect", action="store_true",
                        help="跳过采集步骤,使用数据库已有数据")
    parser.add_argument("--dataset", "-d", type=str, default=None,
                        help="导入 CHEF 数据集路径 (如 data/datasets/CHEF)")
    parser.add_argument("--no-save", action="store_true",
                        help="不保存图表和报告文件")
    parser.add_argument("--db", type=str, default=DB_PATH,
                        help="数据库路径")

    args = parser.parse_args()

    if not args.keyword and not args.event_id:
        parser.error("必须指定 --keyword (采集模式) 或 --event-id (跳过采集模式)")

    sources = [s.strip() for s in args.sources.split(",")]
    do_save = not args.no_save

    start_time = time.time()
    db = Database(args.db)

    # ============================================================
    # Step 0: 导入基准数据集 (可选)
    # ============================================================
    if args.dataset:
        print("\n" + "=" * 60)
        print("Step 0: 导入基准数据集")
        print("=" * 60)
        from src.data.chef import CHEFDataset
        ds = CHEFDataset(args.dataset)
        imported = ds.to_db(db, event_prefix="CHEF")
        event_list = db.list_events()
        print(f"[Step0] 导入完成: {imported} 个事件, "
              f"现有 {len(event_list)} 个事件")

    # ============================================================
    # Step 1-2: 事件发现 + 数据采集
    # ============================================================
    if args.skip_collect:
        print("[Pipeline] 跳过采集,使用已有数据")
        if args.event_id:
            event_id = args.event_id
            event = db.get_event(event_id)
            if not event:
                print(f"[Pipeline] 错误: 事件 {event_id} 不存在")
                return
            print(f"[Pipeline] 使用已有事件: {event['name']} ({event_id})")
        elif args.keyword:
            tracker = EventTracker(db)
            event_id = tracker.discover_or_create_event(args.keyword)
        else:
            # 列出可用事件供选择
            conn = db._connect()
            rows = conn.execute(
                "SELECT id, name, post_count FROM events ORDER BY last_updated DESC LIMIT 10"
            ).fetchall()
            conn.close()
            if not rows:
                print("[Pipeline] 数据库中无事件。请先采集数据:")
                print("  python scripts/run_pipeline.py --keyword \"你的关键词\"")
                return
            print("[Pipeline] 可用事件:")
            for i, r in enumerate(rows):
                print(f"  {i+1}. {r['name']} ({r['id']}) — {r['post_count']} 帖子")
            print("\n请选择: python scripts/run_pipeline.py --skip-collect --event-id <event_id>")
            return
    else:
        if not args.keyword:
            parser.error("采集模式必须指定 --keyword")
        pipeline = Pipeline(args.db)
        event_id = pipeline.run(
            keyword=args.keyword,
            sources=sources,
            max_pages=args.max_pages,
        )

    event = db.get_event(event_id)
    event_name = event.get("name", args.keyword) if event else args.keyword

    # ============================================================
    # Step 3: 文本特征提取
    # ============================================================
    feat_stats = step_extract_features(db, event_id)

    # ============================================================
    # Step 3.5: 图像下载与特征提取
    # ============================================================
    image_stats = step_extract_images(event_id, skip_download=False)

    # ============================================================
    # Step 4: 传播图构建
    # ============================================================
    pg = step_build_graph(db, event_id)

    if pg.node_count == 0:
        print("\n[Pipeline] 无帖子数据，无法继续分析。请先确保采集到数据。")
        elapsed = time.time() - start_time
        print(f"[Pipeline] 耗时 {elapsed:.1f}s, 提前终止")
        return

    # ============================================================
    # Step 5: 源头溯源
    # ============================================================
    candidates = step_trace_source(pg)

    # ============================================================
    # Step 6: 情感演化分析
    # ============================================================
    sentiment_result = step_analyze_sentiment(pg, candidates)

    # ============================================================
    # Step 7: 可视化 + 报告
    # ============================================================
    step_visualize_and_report(
        pg, candidates, sentiment_result,
        event_name, event_id,
        save=do_save,
    )

    # ============================================================
    # 汇总
    # ============================================================
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("流水线完成")
    print("=" * 60)
    print(f"  事件: {event_name} ({event_id})")
    print(f"  节点: {pg.node_count}  边: {pg.edge_count}")
    print(f"  情感标注: {feat_stats.get('with_sentiment', 0)} 条")
    print(f"  源头候选: {len(candidates)} 个")
    print(f"  传播层级: {len(sentiment_result.get('evolution', []))} 层")
    print(f"  整体趋势: {sentiment_result.get('overall_trend', 'N/A')}")
    print(f"  耗时: {elapsed:.1f}s")
    if do_save:
        print(f"  图表: {FIGURES_DIR}/")
        print(f"  报告: {REPORTS_DIR}/{event_id}_report.md")


if __name__ == "__main__":
    main()
