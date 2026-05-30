"""图像批量下载器

基于 aiohttp 的异步并发下载, 支持重试/超时/并发控制。
从帖子 image_urls 字段读取 URL, 下载到 data/images/{post_id}/ 目录。

依赖:
  aiohttp, PIL
"""

import os
import asyncio
import hashlib
from pathlib import Path
from typing import Optional

import aiohttp


class ImageDownloader:
    """异步批量图片下载器"""

    # 常见图片扩展名映射
    MIME_TO_EXT = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
    }

    def __init__(self, save_root: str = "data/images",
                 concurrency: int = 8, timeout: int = 15,
                 max_retries: int = 2):
        self.save_root = Path(save_root)
        self.concurrency = concurrency
        self.timeout = timeout
        self.max_retries = max_retries
        self.save_root.mkdir(parents=True, exist_ok=True)

    def download_all(self, post_images: dict[str, list[str]]) -> dict[str, list[str]]:
        """批量下载所有帖子的图片。

        Parameters
        ----------
        post_images: {post_id: [url, ...]}

        Returns
        -------
        {post_id: [local_path, ...]} — 仅成功下载的文件
        """
        return asyncio.run(self._download_all_async(post_images))

    async def _download_all_async(self, post_images: dict[str, list[str]]
                                  ) -> dict[str, list[str]]:
        semaphore = asyncio.Semaphore(self.concurrency)
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(limit=self.concurrency, limit_per_host=4)

        async with aiohttp.ClientSession(timeout=timeout,
                                          connector=connector) as session:
            tasks = []
            for post_id, urls in post_images.items():
                if not urls:
                    continue
                post_dir = self.save_root / post_id
                post_dir.mkdir(parents=True, exist_ok=True)
                for i, url in enumerate(urls):
                    if not url or not url.startswith("http"):
                        continue
                    tasks.append(self._download_one(
                        session, semaphore, post_id, url, i))

            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate by post_id
        by_post: dict[str, list[str]] = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            if result is None:
                continue
            pid, path = result
            by_post.setdefault(pid, []).append(path)

        total_urls = sum(len(v) for v in post_images.values())
        total_downloaded = sum(len(v) for v in by_post.values())
        print(f"[ImageDL] {total_downloaded}/{total_urls} images downloaded "
              f"({len(by_post)} posts)")
        return by_post

    async def _download_one(self, session: aiohttp.ClientSession,
                            semaphore: asyncio.Semaphore,
                            post_id: str, url: str, idx: int
                            ) -> Optional[tuple[str, str]]:
        async with semaphore:
            for attempt in range(self.max_retries + 1):
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            if attempt < self.max_retries:
                                await asyncio.sleep(1)
                                continue
                            return None

                        content = await resp.read()
                        if len(content) < 100:  # 太小, 可能是错误页
                            return None

                        # Determine extension
                        ext = self._guess_ext(resp.content_type, url)

                        filename = f"{idx:02d}{ext}"
                        filepath = self.save_root / post_id / filename
                        filepath.write_bytes(content)

                        return (post_id, str(filepath))
                except (aiohttp.ClientError, asyncio.TimeoutError,
                        OSError) as e:
                    if attempt < self.max_retries:
                        await asyncio.sleep(1)
                        continue
                    return None
        return None

    def _guess_ext(self, content_type: str, url: str) -> str:
        """从 Content-Type 或 URL 推断文件扩展名"""
        if content_type and content_type in self.MIME_TO_EXT:
            return self.MIME_TO_EXT[content_type]
        # Fallback: URL path extension
        url_path = url.split("?")[0]
        _, ext = os.path.splitext(url_path)
        if ext.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
            return ext.lower()
        return ".jpg"  # default


def parse_image_urls(posts: list[dict]) -> dict[str, list[str]]:
    """从帖子列表中提取 image_urls → {post_id: [url, ...]}

    支持两种存储格式:
      - 纯字符串列表: ["https://...", "https://..."]  (微博)
      - dict 列表: [{"u": "https://...", "w": 550}, ...]  (新浪新闻)
    """
    import json
    result = {}
    for post in posts:
        pid = post.get("post_id") or post.get("id", "")
        raw = post.get("image_urls", "")
        if not raw:
            continue
        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not items or not isinstance(items, list):
            continue

        urls = []
        for item in items:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                url = item.get("u") or item.get("url") or item.get("src")
                if url:
                    urls.append(url)
        if urls:
            result[pid] = urls
    return result
