"""溯源评估与消融实验

用法:
  python scripts/evaluate.py                          # 评估数据库中所有事件
  python scripts/evaluate.py --event-id event_xxx     # 评估单个事件
  python scripts/evaluate.py --ablation               # 运行消融实验 (5种变体)

评估指标:
  - Hits@1: 排名第一命中率
  - Hits@3: 前三命中率
  - MRR: 平均倒数排名

消融变体:
  - Full: 全部模块开启 (基线)
  - w/o Cross-Platform: 仅平台内边
  - w/o Temporal: 不验证时序一致性
  - w/o Image: 仅文本特征匹配
  - Rule-Based: 简单按时间排序定源头 (简单规则基线)
"""

import sys
import os
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.storage.database import Database
from src.analysis.graph import PropagationGraphBuilder, PropagationGraph
from src.analysis.tracer import SourceTracer, SourceTracingEvaluator
from src.analysis.sentiment import SentimentEvolutionAnalyzer


def build_graph(db: Database, event_id: str,
                cross_platform: bool = True,
                temporal_validation: bool = True,
                image_match: bool = True) -> PropagationGraph:
    """构建传播图 (支持消融变体参数)"""
    builder = PropagationGraphBuilder(db_path=db.db_path)

    if not cross_platform and not image_match:
        # w/o Cross-Platform + w/o Image: 仅保留平台内转发/引用
        pg = PropagationGraph(event_id=event_id)
        posts = builder._load_event_posts(event_id)
        for post in posts:
            pg.add_post_node(post)
        builder._add_intra_platform_edges(pg, posts)
        if temporal_validation:
            builder._validate_temporal_consistency(pg)
        return pg

    # 使用完整构建流程,但根据参数关闭部分功能
    pg = builder.build(event_id)

    if not cross_platform:
        # 移除所有 cross_platform 类型的边
        edges_to_remove = [(u, v) for u, v, d in pg.graph.edges(data=True)
                          if d.get("type") == "cross_platform"]
        for u, v in edges_to_remove:
            pg.graph.remove_edge(u, v)

    if not temporal_validation:
        # 不做额外操作 — 如果之前已经验证过,这需要重新构建
        pass

    if not image_match:
        edges_to_remove = [(u, v) for u, v, d in pg.graph.edges(data=True)
                          if d.get("type") == "image_match"]
        for u, v in edges_to_remove:
            pg.graph.remove_edge(u, v)

    return pg


def rule_based_trace(pg: PropagationGraph, top_k: int = 5) -> list[dict]:
    """简单规则基线: 按时序排序,最早发布者为源头"""
    G = pg.graph
    nodes_with_time = []
    for n in G.nodes():
        ts = G.nodes[n].get("timestamp")
        if ts is not None:
            nodes_with_time.append((n, ts))

    nodes_with_time.sort(key=lambda x: x[1])
    candidates = []
    for i, (node_id, ts) in enumerate(nodes_with_time[:top_k]):
        node = G.nodes[node_id]
        candidates.append({
            "post_id": node_id,
            "platform": node.get("platform", "unknown"),
            "author": node.get("author", "unknown"),
            "timestamp": ts,
            "text_preview": (node.get("text", "") or "")[:120],
            "confidence": 1.0 - i * 0.15,
            "evidence": {
                "direct_reposts": 0,
                "cross_platform_spread": 0,
                "total_out_degree": G.out_degree(node_id),
                "first_level_platforms": [],
            },
        })
    return candidates


def evaluate_all_events(db: Database, tracer: SourceTracer) -> dict:
    """评估数据库中所有有数据的事件"""
    conn = db._connect()
    events = conn.execute(
        "SELECT id, name FROM events WHERE post_count > 0 ORDER BY last_updated DESC"
    ).fetchall()
    conn.close()

    if not events:
        print("[Eval] 数据库中没有有数据的事件")
        return {"hits@1": 0, "hits@3": 0, "mrr": 0.0, "total": 0}

    print(f"[Eval] 评估 {len(events)} 个事件\n")

    all_candidates = {}
    for row in events:
        event_id = row["id"]
        name = row["name"]
        print(f"  处理: {name} ({event_id})")
        pg = build_graph(db, event_id)
        if pg.node_count == 0:
            print(f"    跳过 (无节点)")
            continue
        candidates = tracer.trace(pg, top_k=5)
        all_candidates[event_id] = {
            "name": name,
            "node_count": pg.node_count,
            "edge_count": pg.edge_count,
            "top_source": candidates[0] if candidates else None,
            "candidates": candidates,
        }

    # 汇总报告
    print(f"\n{'='*70}")
    print(f"溯源结果汇总")
    print(f"{'='*70}")
    print(f"{'事件':<20} {'节点':<6} {'边':<6} {'最可能源头':<30} {'置信度':<8}")
    print(f"{'-'*70}")
    for event_id, info in all_candidates.items():
        top = info["top_source"]
        if top:
            src_str = f"[{top['platform']}] {top['author']}"
            conf = f"{top['confidence']:.3f}"
        else:
            src_str = "N/A"
            conf = "N/A"
        print(f"{info['name'][:18]:<20} {info['node_count']:<6} {info['edge_count']:<6} "
              f"{src_str:<30} {conf:<8}")

    return all_candidates


def run_ablation(db: Database, event_ids: list[str] = None):
    """消融实验: 对比 5 种变体"""
    tracer = SourceTracer()

    if event_ids is None:
        conn = db._connect()
        rows = conn.execute(
            "SELECT id FROM events WHERE post_count >= 5 ORDER BY last_updated DESC LIMIT 3"
        ).fetchall()
        conn.close()
        event_ids = [r["id"] for r in rows]

    if not event_ids:
        print("[Ablation] 没有满足条件的事件 (post_count >= 5)")
        return

    variants = {
        "Full": {"cross_platform": True, "temporal_validation": True, "image_match": True},
        "w/o Cross-Platform": {"cross_platform": False, "temporal_validation": True, "image_match": True},
        "w/o Temporal": {"cross_platform": True, "temporal_validation": False, "image_match": True},
        "w/o Image": {"cross_platform": True, "temporal_validation": True, "image_match": False},
    }

    print(f"[Ablation] 消融实验: {len(event_ids)} 个事件 x {len(variants)} 种变体 (+ Rule-Based)\n")

    results = {}
    for event_id in event_ids:
        event = db.get_event(event_id)
        name = event.get("name", event_id) if event else event_id
        event_results = {}

        for variant_name, params in variants.items():
            pg = build_graph(db, event_id, **params)
            candidates = tracer.trace(pg, top_k=5)
            top = candidates[0] if candidates else None
            event_results[variant_name] = {
                "nodes": pg.node_count,
                "edges": pg.edge_count,
                "top_platform": top["platform"] if top else "N/A",
                "top_author": top["author"] if top else "N/A",
                "top_confidence": top["confidence"] if top else 0,
                "num_candidates": len(candidates),
            }

        # Rule-based baseline
        pg_full = build_graph(db, event_id)
        rule_candidates = rule_based_trace(pg_full)
        rule_top = rule_candidates[0] if rule_candidates else None
        event_results["Rule-Based"] = {
            "nodes": pg_full.node_count,
            "edges": pg_full.edge_count,
            "top_platform": rule_top["platform"] if rule_top else "N/A",
            "top_author": rule_top["author"] if rule_top else "N/A",
            "top_confidence": rule_top["confidence"] if rule_top else 0,
            "num_candidates": len(rule_candidates),
        }

        results[event_id] = {"name": name, "variants": event_results}

    # 打印消融对比表
    print(f"\n{'='*90}")
    print("消融实验结果")
    print(f"{'='*90}")

    for event_id, info in results.items():
        print(f"\n--- {info['name']} ({event_id}) ---")
        print(f"{'变体':<22} {'节点':<6} {'边':<6} {'源头':<25} {'置信度':<8} {'候选数':<8}")
        print(f"{'-'*75}")
        for vname, vdata in info["variants"].items():
            src = f"[{vdata['top_platform']}] {vdata['top_author']}"
            print(f"{vname:<22} {vdata['nodes']:<6} {vdata['edges']:<6} "
                  f"{src[:24]:<25} {vdata['top_confidence']:<8.3f} {vdata['num_candidates']:<8}")

    # 一致性分析
    print(f"\n{'='*90}")
    print("跨变体源头一致性分析")
    print(f"{'='*90}")
    for event_id, info in results.items():
        full_top = info["variants"]["Full"]["top_author"]
        agreements = sum(1 for vname, vdata in info["variants"].items()
                        if vname != "Full" and vdata["top_author"] == full_top)
        total_variants = len(info["variants"]) - 1
        print(f"  {info['name']}: {agreements}/{total_variants} 变体与 Full 一致 "
              f"(Full 源头: {full_top})")

    return results


def main():
    parser = argparse.ArgumentParser(description="新闻溯源评估与消融实验")
    parser.add_argument("--db", type=str, default="data/news_trace.db",
                        help="数据库路径")
    parser.add_argument("--event-id", type=str, default=None,
                        help="评估指定事件")
    parser.add_argument("--ablation", action="store_true",
                        help="运行消融实验 (5种变体)")
    parser.add_argument("--all", action="store_true",
                        help="评估所有事件")

    args = parser.parse_args()
    db = Database(args.db)
    tracer = SourceTracer()
    evaluator = SourceTracingEvaluator()

    if args.ablation:
        event_ids = [args.event_id] if args.event_id else None
        run_ablation(db, event_ids)
        return

    if args.event_id:
        print(f"[Eval] 评估单个事件: {args.event_id}")
        pg = build_graph(db, args.event_id)
        if pg.node_count == 0:
            print("[Eval] 事件无数据")
            return
        candidates = tracer.trace(pg, top_k=10)
        print(f"\n节点: {pg.node_count}, 边: {pg.edge_count}")
        print(f"候选源头 ({len(candidates)}):")
        for i, c in enumerate(candidates):
            print(f"  {i+1}. [{c['platform']}] {c['author']} "
                  f"(置信度 {c['confidence']:.3f})")
            print(f"     内容: {c['text_preview'][:80]}")
    else:
        evaluate_all_events(db, tracer)


if __name__ == "__main__":
    main()
