"""图像特征流水线

将图片下载 + 特征提取 + DB 存储串联为一个步骤。
由 run_pipeline.py Step 3.5 调用。

依赖:
  PIL, numpy, sqlite3 (+ aiohttp, cv2 用于下载/处理)
"""

import os
import sqlite3
import json
import time
from pathlib import Path
from typing import Optional

from PIL import Image
import numpy as np

from .image_downloader import ImageDownloader, parse_image_urls


def run_image_pipeline(event_id: str, db_path: str = "data/news_trace.db",
                       save_root: str = "data/images",
                       concurrency: int = 6, skip_download: bool = False
                       ) -> dict:
    """图像特征提取完整流水线。

    1. 从 DB 加载带 image_urls 的帖子
    2. 异步批量下载图片 (可跳过)
    3. 提取 pHash/dHash/颜色特征
    4. 写入 images 表

    Returns
    -------
    {downloaded: int, extracted: int, stored: int, skipped: int}
    """
    save_root = os.path.abspath(save_root)

    # ── 1. 加载帖子 ──────────────────────────────────────────
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, platform, image_urls FROM posts WHERE event_id=?",
        (event_id,)
    ).fetchall()
    conn.close()

    posts = [dict(r) for r in rows]
    post_images = parse_image_urls(posts)

    if not post_images:
        print("[ImagePipeline] 无图片 URL 可处理")
        return {"downloaded": 0, "extracted": 0, "stored": 0, "skipped": 0}

    total_urls = sum(len(v) for v in post_images.values())
    print(f"[ImagePipeline] {len(post_images)} posts, {total_urls} URLs")

    # ── 2. 下载 ──────────────────────────────────────────────
    local_map: dict[str, list[str]] = {}
    if not skip_download:
        downloader = ImageDownloader(
            save_root=save_root, concurrency=concurrency, timeout=15)
        local_map = downloader.download_all(post_images)
    else:
        # 从本地目录扫描已有文件
        for pid in post_images:
            post_dir = Path(save_root) / pid
            if post_dir.is_dir():
                files = sorted(post_dir.glob("*"))
                if files:
                    local_map[pid] = [str(f) for f in files]

    if not local_map:
        print("[ImagePipeline] 无图片可提取 (下载失败或全部跳过)")
        return {"downloaded": 0, "extracted": 0, "stored": 0,
                "skipped": total_urls}

    # ── 3. 特征提取 ──────────────────────────────────────────
    from ..features.image import ImageHasher, ImageColorSentiment

    hasher = ImageHasher()
    color_extractor = ImageColorSentiment()

    extracted = 0
    stored = 0
    skipped = total_urls - sum(len(v) for v in local_map.values())

    conn = sqlite3.connect(db_path)
    for post_id, filepaths in local_map.items():
        for fp in filepaths:
            extracted += 1
            try:
                img = Image.open(fp).convert("RGB")
                w, h = img.size
                fsize = os.path.getsize(fp)

                phash_val = hasher.phash(img)
                dhash_val = hasher.dhash(img)
                color_vec = color_extractor.extract(img)
                color_json = json.dumps([round(float(x), 6) for x in color_vec])

                img_id = f"{post_id}_img{Path(fp).stem}"

                conn.execute("""
                    INSERT OR REPLACE INTO images
                    (id, post_id, local_path, url, phash, dhash,
                     ocr_text, width, height, file_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    img_id, post_id, fp, "",
                    phash_val, dhash_val,
                    "",  # OCR skipped — PaddleOCR heavy dependency
                    w, h, fsize,
                ))
                stored += 1
            except Exception as e:
                skipped += 1
                # 静默跳过损坏的图片
                continue

    conn.commit()
    conn.close()

    print(f"[ImagePipeline] 提取 {extracted}, 存储 {stored}, "
          f"跳过 {skipped}")
    return {"downloaded": sum(len(v) for v in local_map.values()),
            "extracted": extracted, "stored": stored, "skipped": skipped}
