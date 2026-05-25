"""Cookie 导出工具

从浏览器中导出指定域名的 Cookie 为 JSON 格式，
供 WeiboScraper / CookieManager 使用。

用法:
  python scripts/export_cookies.py --browser chrome --domain weibo.com --output data/cookies/weibo_main.json
  python scripts/export_cookies.py --browser edge --domain .weibo.com

依赖:
  pip install browser-cookie3
"""

import json
import os
import sys
import argparse

try:
    import browser_cookie3
except ImportError:
    print("请先安装 browser-cookie3: pip install browser-cookie3")
    sys.exit(1)


BROWSERS = {
    "chrome": browser_cookie3.chrome,
    "chromium": browser_cookie3.chromium,
    "edge": browser_cookie3.edge,
    "firefox": browser_cookie3.firefox,
    "opera": browser_cookie3.opera,
    "brave": browser_cookie3.brave,
}


def export_cookies(browser_name: str, domain: str,
                   output_path: str = None) -> list[dict]:
    """从浏览器导出指定域名的 Cookie

    Args:
        browser_name: 浏览器名称 (chrome/edge/firefox/...)
        domain: 域名过滤 (如 'weibo.com', '.weibo.com')
        output_path: 输出 JSON 文件路径
    Returns:
        Cookie 列表
    """
    if browser_name not in BROWSERS:
        print(f"不支持的浏览器: {browser_name}")
        print(f"可用: {list(BROWSERS.keys())}")
        sys.exit(1)

    print(f"正在从 {browser_name} 读取 {domain} 的 Cookie...")
    cj = BROWSERS[browser_name](domain_name=domain)

    cookies = []
    for cookie in cj:
        cookies.append({
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path,
            "expires": cookie.expires,
            "secure": cookie.secure,
            "httponly": hasattr(cookie, "httponly") and cookie.httponly,
        })

    print(f"导出 {len(cookies)} 条 Cookie")

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"已保存至: {output_path}")
    else:
        # 打印到 stdout
        print(json.dumps(cookies, ensure_ascii=False, indent=2))

    return cookies


def main():
    parser = argparse.ArgumentParser(
        description="从浏览器导出 Cookie 为 JSON 格式（供新闻溯源爬虫使用）"
    )
    parser.add_argument("--browser", "-b", type=str, default="chrome",
                        choices=list(BROWSERS.keys()),
                        help="浏览器类型 (默认: chrome)")
    parser.add_argument("--domain", "-d", type=str, default=".weibo.com",
                        help="Cookie 域名过滤 (默认: .weibo.com)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="输出 JSON 文件路径 (不指定则打印到 stdout)")

    args = parser.parse_args()
    export_cookies(args.browser, args.domain, args.output)


if __name__ == "__main__":
    main()
