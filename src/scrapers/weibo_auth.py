"""微博自动登录 — 基于 Playwright 的交互式 Cookie 获取

用法:
  python -m src.scrapers.weibo_auth              # 交互式登录并保存 Cookie
  python -m src.scrapers.weibo_auth --output data/cookies/weibo_main.json
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class WeiboAuth:
    """微博自动登录 — 使用 Playwright 打开可见浏览器让用户扫码"""

    LOGIN_URL = "https://weibo.com/login.php"
    HOME_URL = "https://weibo.com"
    WEIBO_DOMAIN = ".weibo.com"
    COOKIE_DIR = "data/cookies/"

    # 登录成功后的页面特征
    SUCCESS_INDICATORS = [
        "weibo.com/home",      # 登录后重定向到首页
        "weibo.com/u/",        # 个人主页
        "weibo.com/fav",       # 收藏页
    ]

    def __init__(self, headless: bool = False):
        self.headless = headless

    def login(self, output_name: str = "weibo_main") -> list[dict]:
        """打开浏览器让用户扫码登录，返回 Cookie 列表

        Args:
            output_name: 保存的 Cookie 文件名 (不含扩展名)
        Returns:
            标准化后的 Cookie 列表
        """
        if not HAS_PLAYWRIGHT:
            raise ImportError(
                "playwright 未安装。请运行: pip install playwright && playwright install chromium"
            )

        print("\n" + "=" * 56)
        print("[WeiboAuth] 正在打开浏览器进行微博登录...")
        print("[WeiboAuth] 请在浏览器中完成登录（扫码或账号密码）")
        print("=" * 56)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            try:
                # 1. 进入微博登录页
                print("[WeiboAuth] 导航到微博登录页...")
                page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)

                # 2. 等待用户完成登录（最长等待 3 分钟）
                print("[WeiboAuth] 等待登录完成... (请用微博 APP 扫描页面上的二维码)")
                print("[WeiboAuth] 提示: 如二维码未加载, 可点击'账号密码登录'切换")
                print()

                cookies = self._wait_for_login(page, timeout=180)

                if cookies:
                    print(f"\n[WeiboAuth] 登录成功! 获取到 {len(cookies)} 条 Cookie")

                    # 保存到文件
                    output_path = os.path.join(self.COOKIE_DIR, f"{output_name}.json")
                    self._save_cookies(cookies, output_path)
                    print(f"[WeiboAuth] Cookie 已保存: {output_path}")

                    # 验证关键 Cookie
                    key_names = {"SUB", "SUBP", "SSOLoginState"}
                    found_keys = {c["name"] for c in cookies} & key_names
                    if found_keys:
                        print(f"[WeiboAuth] 检测到关键 Cookie: {', '.join(found_keys)}")
                    else:
                        print("[WeiboAuth] 警告: 未检测到 SUB/SUBP Cookie, 登录可能不完整")
                else:
                    print("\n[WeiboAuth] 登录超时或失败, 未获取到有效 Cookie")

            except Exception as e:
                print(f"\n[WeiboAuth] 错误: {e}")
                # 即使出错也尝试获取已有 Cookie
                try:
                    cookies = self._extract_cookies(context)
                    if cookies:
                        output_path = os.path.join(self.COOKIE_DIR, f"{output_name}.json")
                        self._save_cookies(cookies, output_path)
                        print(f"[WeiboAuth] 已保存当前浏览器 Cookie: {output_path}")
                except Exception:
                    pass
                cookies = []

            finally:
                browser.close()

        return cookies or []

    def _wait_for_login(self, page, timeout: int = 180) -> list[dict]:
        """轮询等待登录成功

        检测策略:
          1. URL 变为首页/个人主页
          2. 页面出现已登录特征元素
          3. Cookie 中出现 SUB 字段
        """
        start = time.time()
        last_url = ""

        while time.time() - start < timeout:
            try:
                current_url = page.url

                # 打印 URL 变化
                if current_url != last_url:
                    print(f"  [页面] {current_url[:100]}")
                    last_url = current_url

                # 检测 1: URL 特征
                for indicator in self.SUCCESS_INDICATORS:
                    if indicator in current_url:
                        time.sleep(1)  # 等 Cookie 完全写入
                        return self._extract_cookies(page.context)

                # 检测 2: 已登录页面元素 (导航栏用户头像等)
                try:
                    logged_in = page.locator(
                        '[class*="gn_nav"], [class*="nav"], [class*="woo-box"], '
                        '.gn_position, [href*="/u/"], [class*="avatar"]'
                    ).first
                    if logged_in.is_visible(timeout=1000):
                        # 排除仍在登录页的情况
                        if "login" not in current_url.lower():
                            time.sleep(1)
                            return self._extract_cookies(page.context)
                except Exception:
                    pass

                # 检测 3: Cookie 特征 (SUB 是微博核心认证 Cookie)
                try:
                    raw_cookies = page.context.cookies()
                    cookie_names = {c["name"] for c in raw_cookies}
                    if "SUB" in cookie_names and "login" not in current_url.lower():
                        time.sleep(0.5)
                        return self._extract_cookies(page.context)
                except Exception:
                    pass

                time.sleep(2)

            except Exception as e:
                print(f"  [检测异常] {e}")
                time.sleep(2)

        # 超时, 最后尝试提取
        return self._extract_cookies(page.context)

    def _extract_cookies(self, context) -> list[dict]:
        """从 Playwright 上下文提取 Cookie 并标准化"""
        try:
            raw_cookies = context.cookies()
        except Exception:
            return []

        cookies = []
        for c in raw_cookies:
            # 只保留 weibo.com 域名的 Cookie
            domain = c.get("domain", "")
            if "weibo.com" in domain or "sina.com" in domain:
                cookies.append({
                    "name": c.get("name", ""),
                    "value": c.get("value", ""),
                    "domain": domain,
                    "path": c.get("path", "/"),
                    "expires": c.get("expires", -1),
                    "httpOnly": c.get("httpOnly", False),
                    "secure": c.get("secure", False),
                    "sameSite": c.get("sameSite", "Lax"),
                })

        return cookies

    def _save_cookies(self, cookies: list[dict], output_path: str):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

    @classmethod
    def ensure_cookies(cls, cookie_dir: str = "data/cookies/",
                       silent: bool = False) -> bool:
        """确保 Cookie 池中至少有一个可用 Cookie

        如果池为空, 自动启动登录流程。
        用于在采集前检查 Cookie 状态。

        Returns:
            True 表示 Cookie 池中有可用 Cookie
        """
        import glob
        json_files = glob.glob(os.path.join(cookie_dir, "*.json"))
        if json_files:
            if not silent:
                print(f"[WeiboAuth] Cookie 池: {len(json_files)} 个文件")
            return True

        if silent:
            return False

        print("\n[WeiboAuth] Cookie 池为空, 需要登录微博")
        print("[WeiboAuth] 即将打开浏览器, 请准备用微博 APP 扫码\n")

        resp = input("是否现在登录? [Y/n]: ").strip().lower()
        if resp and resp != "y":
            print("[WeiboAuth] 已跳过登录。微博采集可能受限。")
            return False

        auth = cls(headless=False)
        cookies = auth.login(output_name="weibo_main")
        return len(cookies) > 0


def main():
    parser = argparse.ArgumentParser(description="微博自动登录 — 获取 Cookie")
    parser.add_argument("--output", "-o", type=str, default="weibo_main",
                        help="Cookie 文件名 (不含扩展名, 默认 weibo_main)")
    parser.add_argument("--cookie-dir", "-d", type=str, default="data/cookies/",
                        help="Cookie 存储目录")
    parser.add_argument("--headless", action="store_true",
                        help="无头模式 (仅用于测试, 无法扫码)")

    args = parser.parse_args()
    auth = WeiboAuth(headless=args.headless)
    cookies = auth.login(output_name=args.output)
    print(f"\n获取到 {len(cookies)} 条微博 Cookie")


if __name__ == "__main__":
    main()
