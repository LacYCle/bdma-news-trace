"""爬虫基类

提供 Scrapling 自适应选择器、指数退避重试、请求延迟等通用能力。
所有平台爬虫继承此类。
"""

import time
import random
from typing import Any, Callable, Optional


class BaseScraper:
    """爬虫基类 — Scrapling 通用能力封装"""

    def __init__(self, adaptive_mode: bool = True, request_delay: float = 2.0,
                 max_retry: int = 3):
        self.adaptive_mode = adaptive_mode
        self.request_delay = request_delay
        self.max_retry = max_retry
        self.is_first_run = True  # 首次采集时 auto_save

    def _delay(self):
        """请求间隔，加入随机抖动"""
        jitter = random.uniform(0.5, 1.5)
        time.sleep(self.request_delay * jitter)

    def _adaptive_kwargs(self, element_name: str = "") -> dict:
        """生成自适应选择器参数

        首次采集: auto_save=True 保存元素指纹
        后续采集: adaptive=True 自动匹配
        """
        if self.is_first_run:
            return {"auto_save": True}
        return {"adaptive": self.adaptive_mode}

    def _css_with_fallback(self, page, platform: str, element: str,
                           extra_css: str = ""):
        """CSS 选择器 + XPath 回退 + find_similar 兜底

        使用 SelectorRegistry 中注册的 CSS/XPath，
        按优先级尝试: CSS → XPath → find_similar()
        """
        from .selector_registry import SelectorRegistry

        try:
            sel = SelectorRegistry.get(platform, element)
        except KeyError:
            # 未注册的选择器，直接用传入的 CSS
            return page.css(extra_css, **self._adaptive_kwargs(element))

        # 1. CSS 主方案
        css_sel = sel["css"]
        if extra_css:
            css_sel = f"{css_sel}, {extra_css}"
        result = page.css(css_sel, **self._adaptive_kwargs(element))
        if result:
            return result

        # 2. XPath 回退
        xpath_sel = sel["xpath"]
        result = page.xpath(xpath_sel)
        if result:
            return result

        # 3. find_similar 兜底
        similar = page.find_similar()
        if similar:
            return similar

        return result  # 空结果

    def execute_with_retry(self, func: Callable, *args,
                           error_msg: str = "") -> Any:
        """指数退避重试包装器

        Args:
            func: 要执行的函数
            error_msg: 失败时的日志前缀
        Returns:
            函数返回值，全部失败则 raise
        """
        last_error = None
        for attempt in range(self.max_retry):
            try:
                return func(*args)
            except Exception as e:
                last_error = e
                if attempt < self.max_retry - 1:
                    delay = 2.0 * (2 ** attempt)
                    print(f"[RETRY] {error_msg} 第 {attempt+1}/{self.max_retry} 次, "
                          f"等待 {delay:.0f}s: {e}")
                    time.sleep(delay)
                else:
                    print(f"[FAIL] {error_msg} 全部 {self.max_retry} 次重试失败: {e}")
                    raise last_error

    def mark_first_run_complete(self):
        """标记首次采集完成，后续使用 adaptive 模式"""
        self.is_first_run = False
