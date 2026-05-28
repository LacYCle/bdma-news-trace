"""BDMA News Trace — Flask 测试面板

启动: python -m src.web.app
访问: http://localhost:5000
"""

import io
import json
import sys
import os
import traceback
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template, request, jsonify

from src.storage.database import Database
from src.pipeline import Pipeline
from src.analysis.graph import PropagationGraphBuilder
from src.analysis.tracer import SourceTracer
from src.analysis.sentiment import SentimentEvolutionAnalyzer
from src.features.text import ChineseSentimentAnalyzer, TextEncoder
from src.features.image import ImageFeatureExtractor
from src.features.matcher import CrossPlatformMatcher
from src.visualization.visualizer import PropagationVisualizer
from src.visualization.report import ReportGenerator

app = Flask(__name__)
db = Database(str(project_root / "data" / "news_trace.db"))


# ═══════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ── 事件 ──────────────────────────────────

@app.route("/api/events")
def api_events():
    events = []
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT id, name, keywords, first_seen, last_updated, post_count "
            "FROM events ORDER BY last_updated DESC"
        ).fetchall()
        for r in rows:
            events.append(dict(r))
    return jsonify(events)


@app.route("/api/events/<event_id>/posts")
def api_event_posts(event_id: str):
    posts = db.get_event_posts(event_id)
    for p in posts:
        p["images"] = json.loads(p["images"]) if isinstance(p.get("images"), str) else p.get("images") or []
        p["image_urls"] = json.loads(p["image_urls"]) if isinstance(p.get("image_urls"), str) else p.get("image_urls") or []
    return jsonify(posts)


# ── 数据采集 ──────────────────────────────

@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    data = request.get_json()
    keyword = data.get("keyword", "").strip()
    sources = data.get("sources", ["weibo"])
    max_pages = int(data.get("max_pages", 3))

    if not keyword:
        return jsonify({"error": "关键词不能为空"}), 400

    logs = []
    errors = []

    def log_handler(msg):
        logs.append(msg)

    try:
        # 捕获 stdout/stderr
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            pipeline = Pipeline()
            event_id = pipeline.run(keyword=keyword, sources=sources, max_pages=max_pages)

        stdout_text = buf_out.getvalue()
        stderr_text = buf_err.getvalue()

        # 提取日志行
        for line in stdout_text.split("\n"):
            stripped = line.strip()
            if stripped:
                logs.append(stripped)
        for line in stderr_text.split("\n"):
            stripped = line.strip()
            if stripped:
                errors.append(stripped)

        # 获取采集的帖子预览
        posts = db.get_event_posts(event_id)
        preview = []
        for p in posts[:20]:
            preview.append({
                "platform": p["platform"],
                "author": p["author_name"] or "?",
                "text": (p["text"] or "")[:100],
                "timestamp": p["timestamp"],
                "repost": p["repost_count"] or 0,
                "comment": p["comment_count"] or 0,
                "like": p["like_count"] or 0,
            })

        stats = db.stats()
        return jsonify({
            "success": True,
            "event_id": event_id,
            "keyword": keyword,
            "total_posts": len(posts),
            "preview": preview,
            "stats": stats,
            "logs": logs[-30:],
            "errors": errors,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "logs": logs[-30:],
        }), 500


# ── 特征提取 ──────────────────────────────

@app.route("/api/features/<event_id>", methods=["POST"])
def api_features(event_id: str):
    posts = db.get_event_posts(event_id)
    if not posts:
        return jsonify({"error": "事件无帖子"}), 404

    data = request.get_json() or {}
    modules = data.get("modules", ["text", "image", "match"])

    results = {"event_id": event_id, "post_count": len(posts)}

    if "text" in modules:
        sentiment_analyzer = ChineseSentimentAnalyzer()
        encoder = TextEncoder()
        text_samples = []
        for p in posts[:10]:
            if p["text"]:
                s = sentiment_analyzer.analyze(p["text"])
                text_samples.append({
                    "post_id": p["id"][:20],
                    "platform": p["platform"],
                    "text_preview": p["text"][:80],
                    "polarity": s["polarity"],
                    "arousal": s["arousal"],
                    "dominant": s["dominant"],
                })
        embedding = encoder.encode(posts[0]["text"]) if posts[0].get("text") else None
        results["text"] = {
            "samples": text_samples,
            "embedding_dim": embedding.shape[0] if embedding is not None else None,
        }

    if "image" in modules:
        posts_with_images = [p for p in posts if p.get("image_urls") or p.get("images")]
        results["image"] = {
            "posts_with_images": len(posts_with_images),
            "status": "OK (CLIP/pHash/dHash ready)",
        }

    if "match" in modules and len(posts) >= 2:
        matcher = CrossPlatformMatcher()
        post_a = posts[0]
        post_b = posts[-1]
        score = matcher.match_posts(post_a, post_b)
        results["match"] = {
            "pair": f"{post_a['platform']} ↔ {post_b['platform']}",
            "score": round(score, 4),
            "threshold": 0.4,
            "matched": score >= 0.4,
        }

    return jsonify(results)


# ── 分析层 ────────────────────────────────

@app.route("/api/analysis/<event_id>", methods=["POST"])
def api_analysis(event_id: str):
    builder = PropagationGraphBuilder(str(project_root / "data" / "news_trace.db"))
    pg = builder.build(event_id)

    tracer = SourceTracer()
    trace_result = tracer.trace(pg, top_k=5)

    sa = SentimentEvolutionAnalyzer()
    source_id = trace_result[0]["post_id"] if trace_result else None
    sentiment_result = sa.analyze_path(pg, source_id) if source_id else {}
    sentiment_result["cross_platform"] = sa.cross_platform_sentiment(pg)

    return jsonify({
        "event_id": event_id,
        "graph": {
            "nodes": pg.graph.number_of_nodes(),
            "edges": pg.graph.number_of_edges(),
            "platforms": list(set(pg.graph.nodes[n].get("platform", "?") for n in pg.graph.nodes())),
        },
        "tracing": trace_result,
        "sentiment": {
            "overall_trend": sentiment_result.get("overall_trend", ""),
            "levels": len(sentiment_result.get("evolution", [])),
            "turning_points": len(sentiment_result.get("turning_points", [])),
            "evolution": sentiment_result.get("evolution", []),
            "turning_points_detail": sentiment_result.get("turning_points", []),
            "cross_platform": sentiment_result.get("cross_platform", {}),
        },
    })


# ── 可视化 ────────────────────────────────

@app.route("/api/visualize/<event_id>", methods=["POST"])
def api_visualize(event_id: str):
    builder = PropagationGraphBuilder(str(project_root / "data" / "news_trace.db"))
    pg = builder.build(event_id)

    tracer = SourceTracer()
    trace_result = tracer.trace(pg, top_k=5)

    sa = SentimentEvolutionAnalyzer()
    source_id = trace_result[0]["post_id"] if trace_result else None
    sentiment_result = sa.analyze_path(pg, source_id) if source_id else {}
    sentiment_result["cross_platform"] = sa.cross_platform_sentiment(pg)

    event = db.get_event(event_id)
    event_name = event["name"] if event else event_id

    viz = PropagationVisualizer(str(project_root / "data" / "figures"))
    figures = viz.generate_all(pg, trace_result, sentiment_result, save=True)

    report_gen = ReportGenerator(str(project_root / "data" / "reports"))
    report_content = report_gen.generate(
        event_name, event_id, pg, trace_result, sentiment_result, figures,
    )
    report_path = report_gen.save(report_content, event_id)

    return jsonify({
        "event_id": event_id,
        "figures": list(figures.keys()),
        "report_path": report_path,
    })


@app.route("/api/report/<event_id>")
def api_report(event_id: str):
    report_path = project_root / "data" / "reports" / f"{event_id}_report.md"
    if not report_path.exists():
        return jsonify({"error": "报告不存在，请先生成"}), 404
    return jsonify({"content": report_path.read_text(encoding="utf-8")})


@app.route("/data/figures/<name>")
def serve_figure(name: str):
    figure_path = project_root / "data" / "figures" / name
    if figure_path.exists():
        return figure_path.read_text(encoding="utf-8")
    return jsonify({"error": "图表不存在"}), 404


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
