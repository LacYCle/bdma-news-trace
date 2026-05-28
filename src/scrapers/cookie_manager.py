"""Cookie 池管理器

管理多个微博账号的 Cookie，支持轮询、失效标记和过期提醒。
与 Scrapling Session 协同工作。

Cookie 获取方式:
  1. 浏览器安装 EditThisCookie 或类似插件
  2. 登录微博后导出 Cookie 为 JSON 数组
  3. 保存到 data/cookies/weibo_<账号名>.json
  4. 每个 JSON 文件格式: [{"name": "...", "value": "...", ...}, ...]
"""

import json
import glob
import os
from datetime import datetime
from typing import Optional


class CookieManager:
    """多账号 Cookie 池管理"""

    # EditThisCookie/browser-cookie3 → Scrapling SetCookieParam 字段映射
    _SAMESITE_MAP = {
        "no_restriction": "None",
        "unspecified": None,
        "lax": "Lax",
        "strict": "Strict",
    }

    def __init__(self, cookie_dir: str = "data/cookies/"):
        self.cookie_dir = cookie_dir
        self.pool: list[dict] = []          # 每个元素: {"cookies": [...], "source": "weibo_alice"}
        self.current_index = 0
        self._load_all()

    @classmethod
    def normalize_cookie(cls, raw: dict) -> dict:
        """将 EditThisCookie / browser-cookie3 格式标准化为 Scrapling SetCookieParam

        主要处理:
          - sameSite: no_restriction → None
          - expirationDate → expires
          - 移除 hostOnly / storeId / session 等多余字段
        """
        cookie = {"name": raw.get("name", ""), "value": raw.get("value", "")}

        if "domain" in raw and raw["domain"]:
            cookie["domain"] = raw["domain"]
        if "path" in raw and raw["path"]:
            cookie["path"] = raw["path"]

        # 过期时间
        if "expirationDate" in raw and raw["expirationDate"]:
            cookie["expires"] = float(raw["expirationDate"])
        elif "expires" in raw and raw["expires"]:
            cookie["expires"] = float(raw["expires"])

        if "httpOnly" in raw:
            cookie["httpOnly"] = bool(raw["httpOnly"])
        if "secure" in raw:
            cookie["secure"] = bool(raw["secure"])

        # sameSite 标准化
        if "sameSite" in raw and raw["sameSite"]:
            val = raw["sameSite"]
            if val in cls._SAMESITE_MAP:
                mapped = cls._SAMESITE_MAP[val]
                if mapped is not None:
                    cookie["sameSite"] = mapped
            else:
                cookie["sameSite"] = val

        return cookie

    def _load_all(self):
        """加载所有预先导出的 Cookie 文件"""
        os.makedirs(self.cookie_dir, exist_ok=True)

        pattern = os.path.join(self.cookie_dir, "*.json")
        for filepath in glob.glob(pattern):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    cookies = json.load(f)

                if isinstance(cookies, list):
                    normalized = [self.normalize_cookie(c) for c in cookies]
                    source = os.path.splitext(os.path.basename(filepath))[0]
                    self.pool.append({
                        "cookies": normalized,
                        "source": source,
                        "filepath": filepath,
                        "added": datetime.now(),
                        "failures": 0,
                    })
                    print(f"[CookieManager] 加载: {source} ({len(normalized)} 条 Cookie)")
            except Exception as e:
                print(f"[CookieManager] 跳过 {filepath}: {e}")

        if not self.pool:
            print("[CookieManager] 警告: Cookie 池为空！请将 Cookie JSON 文件放入 data/cookies/")
            print("[CookieManager] 获取方式: 浏览器登录微博 → EditThisCookie 导出 → 保存为 JSON")

    @property
    def size(self) -> int:
        return len(self.pool)

    @property
    def is_empty(self) -> bool:
        return len(self.pool) == 0

    def get_next(self) -> Optional[dict]:
        """轮询获取下一个可用 Cookie 的完整条目"""
        if not self.pool:
            return None

        active = [entry for entry in self.pool if entry.get("failures", 0) < 3]
        if not active:
            print("[CookieManager] 所有 Cookie 均已失效，请重新登录")
            return None

        entry = active[self.current_index % len(active)]
        self.current_index += 1
        return entry

    def get_cookies_list(self) -> Optional[list[dict]]:
        """获取下一个可用 Cookie 列表（用于 requests/Scrapling）"""
        entry = self.get_next()
        return entry["cookies"] if entry else None

    def mark_failure(self, cookie_entry: dict):
        """标记 Cookie 失败次数"""
        cookie_entry["failures"] = cookie_entry.get("failures", 0) + 1
        source = cookie_entry.get("source", "unknown")
        failures = cookie_entry["failures"]
        if failures >= 3:
            print(f"[CookieManager] {source} 已失效 3 次，从池中移除")
        else:
            print(f"[CookieManager] {source} 请求失败 ({failures}/3)")

    def mark_success(self, cookie_entry: dict):
        """重置失败计数"""
        cookie_entry["failures"] = 0

    def status(self) -> str:
        """Cookie 池状态摘要"""
        active = sum(1 for e in self.pool if e.get("failures", 0) < 3)
        return (f"Cookie 池状态: {active}/{len(self.pool)} 可用, "
                f"总 {len(self.pool)} 个账号")

    def refresh_pool(self):
        """重新扫描并加载 Cookie 目录"""
        self.pool.clear()
        self._load_all()

    def prompt_export_guide(self):
        """打印 Cookie 导出指引"""
        print("""
========== 微博 Cookie 导出指南 ==========

方法 1: EditThisCookie 插件 (推荐)
  1. Chrome/Edge 安装 "EditThisCookie" 插件
  2. 打开 weibo.com 并登录
  3. 点击插件图标 → Export
  4. 保存为 data/cookies/weibo_<账号名>.json

方法 2: browser-cookie3 (命令行)
  pip install browser-cookie3
  python scripts/export_cookies.py --browser chrome --domain weibo.com

方法 3: 浏览器开发者工具
  1. F12 → Application → Cookies → weibo.com
  2. 手动复制每个 Cookie 的 name/value
  3. 按 JSON 格式保存:
     [{"name": "SUB", "value": "xxx"}, {"name": "SUBP", "value": "yyy"}]

============================================
        """)
