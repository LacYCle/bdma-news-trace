"""新闻传播溯源 — 交互式 CLI 管理器

用法:
  python scripts/cli.py
"""

import sys
import os
import json
import time
from datetime import datetime

# ===== 路径初始化 =====
# 无论从哪个目录运行, 都使用项目根目录的绝对路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_PROJECT_ROOT)
sys.path.insert(0, _PROJECT_ROOT)

# 离线模式避免 HuggingFace 网络超时阻塞 (25s+ 重试)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from src.config import load_config
from src.storage.database import Database
from src.pipeline import Pipeline, EventTracker
from src.features.text import ChineseSentimentAnalyzer
from src.analysis.graph import PropagationGraphBuilder
from src.analysis.tracer import SourceTracer
from src.analysis.sentiment import SentimentEvolutionAnalyzer
from src.visualization.nature_visualizer import NatureVisualizer
from src.visualization.report import ReportGenerator
from src.storage.models import SentimentRecord

_cfg = load_config()
DB_PATH = os.path.join(_PROJECT_ROOT, _cfg.db_path) if not os.path.isabs(_cfg.db_path) else _cfg.db_path
FIGURES_DIR = os.path.join(_PROJECT_ROOT, "data", "figures")
REPORTS_DIR = os.path.join(_PROJECT_ROOT, "data", "reports")
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════╗
║                                                      ║
║     新闻事件传播路径溯源与情感演化分析系统            ║
║    News Event Propagation Trace & Sentiment Analysis ║
║                                                      ║
╚══════════════════════════════════════════════════════╝{RESET}
""")


def press_enter():
    input(f"\n{YELLOW}按 Enter 返回主菜单...{RESET}")


def input_nonempty(prompt: str) -> str:
    while True:
        val = input(prompt).strip()
        if val:
            return val


def input_int(prompt: str, default: int, lo: int = 1, hi: int = 100) -> int:
    while True:
        val = input(prompt).strip()
        if not val:
            return default
        try:
            n = int(val)
            if lo <= n <= hi:
                return n
            print(f"  请输入 {lo}-{hi} 之间的整数")
        except ValueError:
            print("  请输入有效整数")


def input_choice(prompt: str, choices: list[str], default: int = 0) -> int:
    print(f"\n{prompt}")
    for i, c in enumerate(choices):
        marker = f"{GREEN}→{RESET}" if i == default else " "
        print(f"  {marker} [{i+1}] {c}")
    return input_int(f"请选择 [1-{len(choices)}] (默认 {default+1}): ", default + 1, 1, len(choices)) - 1


# ================================================================
# 页面: 主菜单
# ================================================================
def main_menu() -> str:
    """显示主菜单,返回用户选择的操作码"""
    clear()
    banner()
    db = Database(DB_PATH)
    stats = db.stats()
    conn = db._connect()
    latest = conn.execute(
        "SELECT name, last_updated FROM events ORDER BY last_updated DESC LIMIT 3"
    ).fetchall()
    conn.close()

    print(f"  {GREEN}数据库状态{RESET}: {stats['post_count']} 条帖子, {stats['event_count']} 个事件")
    if stats["by_platform"]:
        plat_str = ", ".join(f"{k}: {v}" for k, v in stats["by_platform"].items())
        print(f"  平台分布: {plat_str}")
    if latest:
        print(f"\n  {GREEN}最近事件{RESET}:")
        for r in latest:
            print(f"    · {r['name']} ({r['last_updated'][:16]})")

    print(f"""
  {BOLD}主菜单{RESET}

  {BOLD}[1]{RESET} {CYAN}新建采集{RESET} — 输入关键词,从微博/新闻网站采集数据
  {BOLD}[2]{RESET} {CYAN}分析已有事件{RESET} — 从数据库中选择事件进行溯源分析
  {BOLD}[3]{RESET} {CYAN}快速分析{RESET} — 采集+分析一键完成 (输入关键词即可)
  {BOLD}[4]{RESET} {CYAN}批量评估{RESET} — 对所有事件运行评估指标
  {BOLD}[5]{RESET} {CYAN}数据概览{RESET} — 查看数据库中的事件与帖子详情
  {BOLD}[6]{RESET} {CYAN}导入公开数据集{RESET} — 从 CHEF 等数据集导入
  {BOLD}[7]{RESET} {GREEN}登录微博{RESET} — 扫码获取/刷新微博 Cookie
  {BOLD}[0]{RESET} 退出
""")

    while True:
        choice = input(f"{BOLD}请输入选项 [0-7]: {RESET}").strip()
        if choice in ("0", "1", "2", "3", "4", "5", "6", "7"):
            return choice
        print(f"  {RED}无效选项, 请重试{RESET}")


# ================================================================
# 页面 1: 新建采集
# ================================================================
def page_collect():
    clear()
    banner()
    print(f"{BOLD}[1] 新建数据采集{RESET}\n")

    keyword = input_nonempty("  请输入搜索关键词: ")
    print(f"\n  可选数据源: weibo / sina / netease")
    sources_str = input("  数据源 (逗号分隔, 默认 weibo,sina,netease): ").strip()
    sources = [s.strip() for s in sources_str.split(",")] if sources_str else ["weibo", "sina", "netease"]

    # 如果选了微博, 检查 Cookie
    if "weibo" in sources:
        from src.scrapers.cookie_manager import CookieManager
        cm = CookieManager(cookie_dir=os.path.join(_PROJECT_ROOT, "data", "cookies"), auto_auth=False)
        if cm.is_empty:
            print(f"\n  {YELLOW}微博采集需要登录, Cookie 池为空{RESET}")
            resp = input("  是否现在登录? [Y/n]: ").strip().lower()
            if not resp or resp == "y":
                from src.scrapers.weibo_auth import WeiboAuth
                auth = WeiboAuth(headless=False)
                cookies = auth.login(output_name="weibo_main")
                if not cookies:
                    print(f"\n  {RED}登录未成功, 微博采集将跳过{RESET}")
                    sources = [s for s in sources if s != "weibo"]
                else:
                    print(f"\n  {GREEN}登录成功{RESET}")

    max_pages = input_int("  微博最大翻页数 (默认 5): ", 5, 1, 20)

    print(f"\n  {GREEN}即将开始采集:{RESET}")
    print(f"    关键词: {keyword}")
    print(f"    数据源: {', '.join(sources)}")
    print(f"    微博页数: {max_pages}")
    confirm = input(f"\n  {YELLOW}确认开始? [Y/n]: {RESET}").strip().lower()
    if confirm and confirm != "y":
        print("  已取消")
        press_enter()
        return

    print(f"\n  {CYAN}启动采集流水线...{RESET}\n")
    pipeline = Pipeline(DB_PATH)
    try:
        event_id = pipeline.run(keyword=keyword, sources=sources, max_pages=max_pages)
        db = Database(DB_PATH)
        event = db.get_event(event_id)
        post_count = event["post_count"] if event else 0
        print(f"\n  {GREEN}采集完成!{RESET} 事件 ID: {event_id}, 帖子数: {post_count}")
    except Exception as e:
        print(f"\n  {RED}采集失败: {e}{RESET}")

    press_enter()


# ================================================================
# 页面 2: 分析已有事件
# ================================================================
def page_analyze():
    clear()
    banner()
    print(f"{BOLD}[2] 分析已有事件{RESET}\n")

    db = Database(DB_PATH)
    conn = db._connect()
    events = conn.execute(
        "SELECT id, name, post_count, last_updated FROM events WHERE post_count > 0 ORDER BY last_updated DESC"
    ).fetchall()
    conn.close()

    if not events:
        print(f"  {RED}数据库中没有事件数据。请先采集数据。{RESET}")
        press_enter()
        return

    print(f"  可用事件 ({len(events)} 个):\n")
    print(f"  {'':>3} {'事件名':<30} {'帖子':<8} {'更新时间':<20}")
    print(f"  {'':>3} {'-'*30} {'-'*8} {'-'*20}")
    for i, e in enumerate(events):
        name = e["name"][:28]
        print(f"  {BOLD}{i+1}.{RESET} {name:<30} {e['post_count']:<8} {e['last_updated'][:19]}")

    choice = input_int(f"\n  选择事件 [1-{len(events)}]: ", 1, 1, len(events))
    event = events[choice - 1]
    event_id = event["id"]
    event_name = event["name"]

    print(f"\n  {GREEN}已选择: {event_name} ({event_id}){RESET}")

    # 分析选项
    print(f"""
  {BOLD}分析选项:{RESET}
  [1] 完整分析 (图 + 溯源 + 情感 + 可视化 + 报告)
  [2] 仅溯源
  [3] 仅情感演化
  [4] 仅生成可视化
""")
    opt = input("  请选择 [1-4] (默认 1): ").strip() or "1"

    db = Database(DB_PATH)
    post_count = db.get_post_count(event_id)

    # Step 3: 特征提取
    print(f"\n  {CYAN}提取文本情感特征...{RESET}")
    analyzer = ChineseSentimentAnalyzer()
    posts = db.get_event_posts(event_id)
    sent_count = 0
    for post in posts:
        text = post.get("text", "")
        if not text:
            continue
        try:
            result = analyzer.analyze(text)
            db.insert_sentiment(SentimentRecord(
                post_id=post["id"],
                sentiment_label=result.get("dominant", "中性"),
                sentiment_score=result.get("polarity", 0.0),
                arousal_score=result.get("arousal", 0.0),
                emotions=result.get("emotions", {}),
                model_version="rule-v1",
            ))
            sent_count += 1
        except Exception as e:
            pass
    print(f"  {GREEN}已标注 {sent_count}/{len(posts)} 条帖子{RESET}")

    # Step 4: 传播图
    print(f"\n  {CYAN}构建传播图...{RESET}")
    builder = PropagationGraphBuilder(db_path=DB_PATH)
    pg = builder.build(event_id)
    print(f"  {GREEN}{pg.node_count} 节点, {pg.edge_count} 边{RESET}")

    if pg.node_count == 0:
        print(f"  {RED}图为空, 无法继续{RESET}")
        press_enter()
        return

    candidates = []
    sentiment_result = {}

    if opt in ("1", "2"):
        # Step 5: 溯源
        print(f"\n  {CYAN}源头溯源...{RESET}")
        tracer = SourceTracer()
        candidates = tracer.trace(pg, top_k=5)
        if candidates:
            top = candidates[0]
            print(f"  {GREEN}最可能源头: [{top['platform']}] {top['author']}")
            print(f"  置信度: {top['confidence']:.3f}")
            print(f"  证据: 直接转发={top['evidence']['direct_reposts']}, "
                  f"跨平台={top['evidence']['cross_platform_spread']}{RESET}")
            if len(candidates) > 1:
                print(f"\n  其他候选:")
                for i, c in enumerate(candidates[1:3]):
                    print(f"    {i+2}. [{c['platform']}] {c['author']} ({c['confidence']:.3f})")

    if opt in ("1", "3"):
        # Step 6: 情感
        print(f"\n  {CYAN}情感演化分析...{RESET}")
        analyzer = SentimentEvolutionAnalyzer()
        source_id = candidates[0]["post_id"] if candidates else list(pg.graph.nodes())[0]
        path = analyzer.analyze_path(pg, source_id)
        cross = analyzer.cross_platform_sentiment(pg)
        sentiment_result = {
            "evolution": path.get("evolution", []),
            "turning_points": path.get("turning_points", []),
            "overall_trend": path.get("overall_trend", ""),
            "cross_platform": cross,
        }

        print(f"  {GREEN}传播深度: {len(path.get('evolution', []))} 层")
        print(f"  整体趋势: {path.get('overall_trend', 'N/A')}")
        for tp in path.get("turning_points", []):
            print(f"  转折点: L{tp['from_level']}→L{tp['to_level']} {tp['direction']} Δ={tp['magnitude']:.3f}")

        if cross:
            print(f"\n  跨平台情感:")
            for plat, s in cross.items():
                print(f"    {plat}: 极性={s['avg_polarity']:+.3f} 主导={s['dominant_emotion']}")

    if opt in ("1", "4"):
        # Step 7: 可视化 + 报告
        print(f"\n  {CYAN}生成可视化...{RESET}")
        visualizer = NatureVisualizer(output_dir=FIGURES_DIR)
        figures = visualizer.generate_all(pg, candidates, sentiment_result, save=True)
        print(f"  {GREEN}已生成 {len(figures)} 张图表 → data/figures/{RESET}")

        print(f"\n  {CYAN}生成分析报告...{RESET}")
        reporter = ReportGenerator(output_dir=REPORTS_DIR)
        report = reporter.generate(event_name, event_id, pg, candidates, sentiment_result, figures)
        path = reporter.save(report, event_id)
        print(f"  {GREEN}报告已保存 → {path}{RESET}")

    print(f"\n  {GREEN}分析完成!{RESET}")
    press_enter()


# ================================================================
# 页面 3: 快速分析 (采集+分析一键)
# ================================================================
def page_quick():
    clear()
    banner()
    print(f"{BOLD}[3] 快速分析 — 采集 + 全流程分析{RESET}\n")

    keyword = input_nonempty("  请输入搜索关键词: ")
    max_pages = input_int("  微博最大翻页数 (默认 3): ", 3, 1, 10)

    print(f"\n  {CYAN}Step 1/4: 数据采集...{RESET}")
    pipeline = Pipeline(DB_PATH)
    try:
        event_id = pipeline.run(keyword=keyword, sources=["weibo", "sina", "netease"], max_pages=max_pages)
    except Exception as e:
        print(f"\n  {RED}采集失败: {e}{RESET}")
        press_enter()
        return

    db = Database(DB_PATH)
    event = db.get_event(event_id)
    event_name = event["name"] if event else keyword

    # 特征提取
    print(f"\n  {CYAN}Step 2/4: 文本情感分析...{RESET}")
    analyzer = ChineseSentimentAnalyzer()
    posts = db.get_event_posts(event_id)
    for post in posts:
        text = post.get("text", "")
        if not text:
            continue
        try:
            result = analyzer.analyze(text)
            db.insert_sentiment(SentimentRecord(
                post_id=post["id"],
                sentiment_label=result.get("dominant", "中性"),
                sentiment_score=result.get("polarity", 0.0),
                arousal_score=result.get("arousal", 0.0),
                emotions=result.get("emotions", {}),
                model_version="rule-v1",
            ))
        except Exception:
            pass

    # 图 + 溯源 + 情感
    print(f"\n  {CYAN}Step 3/4: 传播图构建 + 溯源 + 情感分析...{RESET}")
    builder = PropagationGraphBuilder(db_path=DB_PATH)
    pg = builder.build(event_id)

    tracer = SourceTracer()
    candidates = tracer.trace(pg, top_k=5)

    analyzer = SentimentEvolutionAnalyzer()
    source_id = candidates[0]["post_id"] if candidates else list(pg.graph.nodes())[0]
    path = analyzer.analyze_path(pg, source_id)
    cross = analyzer.cross_platform_sentiment(pg)
    sentiment_result = {
        "evolution": path.get("evolution", []),
        "turning_points": path.get("turning_points", []),
        "overall_trend": path.get("overall_trend", ""),
        "cross_platform": cross,
    }

    # 可视化 + 报告
    print(f"\n  {CYAN}Step 4/4: 可视化 + 报告...{RESET}")
    visualizer = NatureVisualizer(output_dir=FIGURES_DIR)
    figures = visualizer.generate_all(pg, candidates, sentiment_result, save=True)

    reporter = ReportGenerator(output_dir=REPORTS_DIR)
    report = reporter.generate(event_name, event_id, pg, candidates, sentiment_result, figures)
    path = reporter.save(report, event_id)

    # 汇总
    print(f"\n  {'='*56}")
    print(f"  {BOLD}{GREEN}分析汇总{RESET}")
    print(f"  {'='*56}")
    print(f"  事件: {event_name}")
    print(f"  节点: {pg.node_count}  边: {pg.edge_count}")
    print(f"  源头: [{candidates[0]['platform']}] {candidates[0]['author']}" if candidates else "  源头: N/A")
    print(f"  趋势: {sentiment_result.get('overall_trend', 'N/A')}")
    print(f"  图表: data/figures/ ({len(figures)} 张)")
    print(f"  报告: {path}")
    print(f"  {'='*56}")

    press_enter()


# ================================================================
# 页面 4: 批量评估
# ================================================================
def page_evaluate():
    clear()
    banner()
    print(f"{BOLD}[4] 批量评估{RESET}\n")

    db = Database(DB_PATH)
    conn = db._connect()
    events = conn.execute(
        "SELECT id, name, post_count FROM events WHERE post_count >= 3 ORDER BY last_updated DESC"
    ).fetchall()
    conn.close()

    if not events:
        print(f"  {RED}没有满足条件的事件 (>= 3 条帖子){RESET}")
        press_enter()
        return

    print(f"  将对 {len(events)} 个事件进行评估\n")

    tracer = SourceTracer()
    for e in events:
        event_id = e["id"]
        name = e["name"]
        print(f"  {CYAN}处理: {name}{RESET}")

        builder = PropagationGraphBuilder(db_path=DB_PATH)
        pg = builder.build(event_id)
        if pg.node_count < 3:
            print(f"    跳过 (节点数 < 3)")
            continue

        candidates = tracer.trace(pg, top_k=5)
        if not candidates:
            print(f"    无候选")
            continue

        top = candidates[0]
        print(f"    {GREEN}源头: [{top['platform']}] {top['author']} ({top['confidence']:.3f}){RESET}")
        print(f"    节点/边: {pg.node_count}/{pg.edge_count}")
        print(f"    证据: 直转={top['evidence']['direct_reposts']} "
              f"跨平台={top['evidence']['cross_platform_spread']} "
              f"出度={top['evidence']['total_out_degree']}")

    print(f"\n  {GREEN}评估完成{RESET}")
    press_enter()


# ================================================================
# 页面 5: 数据概览
# ================================================================
def page_overview():
    clear()
    banner()
    print(f"{BOLD}[5] 数据概览{RESET}\n")

    db = Database(DB_PATH)
    stats = db.stats()

    print(f"  {BOLD}总体统计{RESET}")
    print(f"  帖子总数: {stats['post_count']}")
    print(f"  事件总数: {stats['event_count']}")
    print(f"  平台分布: {json.dumps(stats['by_platform'], ensure_ascii=False)}")
    print()

    conn = db._connect()
    events = conn.execute(
        "SELECT id, name, keywords, post_count, first_seen, last_updated "
        "FROM events ORDER BY last_updated DESC"
    ).fetchall()
    conn.close()

    if events:
        print(f"  {BOLD}事件列表{RESET}\n")
        print(f"  {'ID':<35} {'名称':<30} {'帖子':<6}")
        print(f"  {'-'*35} {'-'*30} {'-'*6}")
        for e in events:
            print(f"  {e['id']:<35} {e['name'][:28]:<30} {e['post_count']:<6}")

    press_enter()


# ================================================================
# 页面 7: 登录微博
# ================================================================
def page_login():
    clear()
    banner()
    print(f"{BOLD}[7] 登录微博 — 扫码获取 Cookie{RESET}\n")

    from src.scrapers.weibo_auth import WeiboAuth
    from src.scrapers.cookie_manager import CookieManager

    cm = CookieManager(cookie_dir=os.path.join(_PROJECT_ROOT, "data", "cookies"), auto_auth=False)
    pool_size = cm.size

    if pool_size > 0:
        print(f"  当前 Cookie 池: {pool_size} 个可用")
        print(f"\n  [1] 新增账号 (追加到池中)")
        print(f"  [2] 刷新现有 Cookie (替换)")
        print(f"  [0] 返回")
        choice = input(f"\n  请选择 [0-2]: ").strip()
        if choice == "0":
            return
        suffix = input("  账号标识 (默认 weibo_main): ").strip() or "weibo_main"
    else:
        print(f"  {YELLOW}Cookie 池为空, 采集微博数据必须登录{RESET}\n")
        suffix = input("  账号标识 (默认 weibo_main): ").strip() or "weibo_main"

    print(f"\n  {GREEN}即将打开浏览器, 请准备用微博 APP 扫码{RESET}")
    print(f"  提示: 浏览器窗口会打开 weibo.com 登录页")
    print(f"  如果二维码不显示, 可点击页面上的刷新按钮\n")

    confirm = input(f"  确认开始登录? [Y/n]: ").strip().lower()
    if confirm and confirm != "y":
        return

    auth = WeiboAuth(headless=False)
    cookies = auth.login(output_name=suffix)

    if cookies:
        print(f"\n  {GREEN}登录成功! Cookie 已保存到池中{RESET}")
        cm.refresh_pool()
        print(f"  当前 Cookie 池: {cm.size} 个可用")
    else:
        print(f"\n  {RED}登录未成功, 请重试{RESET}")

    press_enter()


# ================================================================
# 页面 6: 导入公开数据集
# ================================================================
def page_import():
    clear()
    banner()
    print(f"{BOLD}[6] 导入公开数据集{RESET}\n")

    print(f"  支持的数据集:")
    print(f"    [1] CHEF — 中文突发事件数据集")
    print(f"    [2] 自定义 JSON 目录\n")

    choice = input("  请选择 [1-2]: ").strip()

    if choice == "1":
        path = input("  CHEF 数据集路径 (默认 data/datasets/CHEF): ").strip()
        if not path:
            path = "data/datasets/CHEF"

        if not os.path.isdir(path):
            print(f"  {RED}目录不存在: {path}{RESET}")
            print(f"  请先从 GitHub 下载: https://github.com/THU-KEG/CHEF")
            press_enter()
            return

        from src.data import CHEFDataset
        try:
            ds = CHEFDataset(path)
            total = ds.to_db(Database(DB_PATH), event_prefix="CHEF")
            print(f"\n  {GREEN}导入完成: {total} 条帖子{RESET}")
        except Exception as e:
            print(f"\n  {RED}导入失败: {e}{RESET}")

    elif choice == "2":
        path = input("  JSON 文件或目录路径: ").strip()
        if not os.path.exists(path):
            print(f"  {RED}路径不存在{RESET}")
            press_enter()
            return
        print(f"  {YELLOW}自定义导入功能待完善, 请使用 CHEF 格式{RESET}")

    press_enter()


# ================================================================
# 主循环
# ================================================================
def main():
    while True:
        choice = main_menu()
        if choice == "0":
            clear()
            print(f"\n{GREEN}再见!{RESET}\n")
            break
        elif choice == "1":
            page_collect()
        elif choice == "2":
            page_analyze()
        elif choice == "3":
            page_quick()
        elif choice == "4":
            page_evaluate()
        elif choice == "5":
            page_overview()
        elif choice == "6":
            page_import()
        elif choice == "7":
            page_login()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{GREEN}已退出{RESET}\n")
