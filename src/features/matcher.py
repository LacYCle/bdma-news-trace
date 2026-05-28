"""跨平台内容匹配器

利用文本语义 + 图像指纹 + 时间窗口进行跨平台关联，
用于发现不同平台上对同一新闻事件的报道。

依赖:
  numpy, PIL, src.features.text, src.features.image
"""

import numpy as np
from typing import Optional
from datetime import datetime, timedelta
from PIL import Image

from .text import TextEncoder
from .image import CLIPImageEncoder, ImageHasher


class CrossPlatformMatcher:
    """跨平台帖子匹配器 — 三维度加权融合"""

    def __init__(self, device: str = None):
        self.text_encoder: Optional[TextEncoder] = None
        self.img_encoder: Optional[CLIPImageEncoder] = None
        self.img_hasher = ImageHasher()

        try:
            self.text_encoder = TextEncoder(device=device)
        except Exception as e:
            print(f"[Matcher] 文本编码器加载失败: {e}")

        try:
            self.img_encoder = CLIPImageEncoder(device=device)
        except Exception as e:
            print(f"[Matcher] 图像编码器加载失败: {e}")

    def match_posts(self, post_a: dict, post_b: dict) -> float:
        """计算两个帖子属于同一事件的综合置信度 (0-1)

        post_a / post_b 格式:
          - text: str
          - images: list[str] (本地文件路径)
          - timestamp: datetime
        """
        scores = []

        # 1. 文本语义相似度 (权重 0.5)
        if post_a.get("text") and post_b.get("text"):
            text_score = self._text_similarity(post_a["text"], post_b["text"])
            scores.append(("text", text_score, 0.5))

        # 2. 图像相似度 (权重 0.35)
        imgs_a = post_a.get("images", []) or []
        imgs_b = post_b.get("images", []) or []
        if imgs_a and imgs_b:
            img_score = self._image_similarity(imgs_a, imgs_b)
            scores.append(("image", img_score, 0.35))

        # 3. 时间窗口得分 (权重 0.15)
        time_a = post_a.get("timestamp")
        time_b = post_b.get("timestamp")
        if time_a and time_b:
            time_score = self._time_similarity(time_a, time_b)
            scores.append(("time", time_score, 0.15))

        if not scores:
            return 0.0

        total_weight = sum(w for _, _, w in scores)
        return float(sum(s * w for _, s, w in scores) / total_weight)

    def batch_match(self, source_post: dict,
                    candidates: list[dict],
                    threshold: float = 0.5) -> list[dict]:
        """从候选池中匹配与源帖子高度关联的帖子"""
        matches = []
        for candidate in candidates:
            score = self.match_posts(source_post, candidate)
            if score >= threshold:
                matches.append({**candidate, "match_score": score})
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        return matches

    def _text_similarity(self, text_a: str, text_b: str) -> float:
        """文本语义余弦相似度"""
        if self.text_encoder is None:
            # 回退: Jaccard 字符级相似度
            set_a = set(text_a[:200])
            set_b = set(text_b[:200])
            if not set_a or not set_b:
                return 0.0
            return len(set_a & set_b) / len(set_a | set_b)

        emb_a = self.text_encoder.encode(text_a[:256])
        emb_b = self.text_encoder.encode(text_b[:256])
        norm = np.linalg.norm(emb_a) * np.linalg.norm(emb_b)
        return float(np.dot(emb_a, emb_b) / norm) if norm > 0 else 0.0

    def _image_similarity(self, img_paths_a: list[str],
                          img_paths_b: list[str]) -> float:
        """图像维度相似度 — 取最优匹配对"""
        best = 0.0
        limit = 5
        for path_a in img_paths_a[:limit]:
            try:
                img_a = Image.open(path_a)
            except Exception:
                continue
            for path_b in img_paths_b[:limit]:
                try:
                    img_b = Image.open(path_b)
                except Exception:
                    continue
                # 先快速检查感知哈希
                if self.img_hasher.is_same_image(img_a, img_b, threshold=8):
                    best = max(best, 1.0)
                elif self.img_encoder and self.img_encoder.is_available:
                    sim = self.img_encoder.similarity(img_a, img_b)
                    best = max(best, max(0, sim))
                else:
                    # 哈希距离作为相似度
                    ph1, ph2 = self.img_hasher.phash(img_a), self.img_hasher.phash(img_b)
                    dist = self.img_hasher.hamming_distance(ph1, ph2)
                    best = max(best, max(0, 1.0 - dist / 64.0))
        return best

    def _time_similarity(self, time_a: datetime, time_b: datetime) -> float:
        """时间窗口相似度 — 24 小时内线性衰减"""
        diff_hours = abs((time_a - time_b).total_seconds()) / 3600
        return max(0.0, 1.0 - diff_hours / 24.0)
