"""图像特征提取器

Chinese-CLIP 语义编码 + 感知哈希 (pHash/dHash) + PaddleOCR + 色彩情感。

依赖:
  torch, PIL, cv2, cn_clip (可选), paddleocr (可选)
"""

import os
import numpy as np
from typing import Optional
from PIL import Image

_is_cv2_available = False
try:
    import cv2
    _is_cv2_available = True
except ImportError:
    pass


class CLIPImageEncoder:
    """基于 Chinese-CLIP 的图像语义编码器 (512-dim)

    加载优先级:
      1. cn_clip (Chinese-CLIP, 最佳中文图文对齐)
      2. OpenAI CLIP (需 pip install git+https://github.com/openai/CLIP.git)
      3. HuggingFace transformers CLIPModel (回退, 无需额外安装)
    """

    def __init__(self, device: str = None):
        self._device = device or "cpu"
        self._model = None
        self._preprocess = None
        self._hf_processor = None  # HuggingFace variant

        import torch
        loaded = False

        # 1. 尝试 cn_clip
        try:
            import cn_clip.clip as clip
            model, preprocess = clip.load(
                "ViT-B/16", device=self._device,
                download_root=os.path.expanduser("~/.cache/clip")
            )
            self._model = model
            self._preprocess = preprocess
            self._dim = 512
            loaded = True
        except ImportError:
            pass

        # 2. 尝试 OpenAI CLIP
        if not loaded:
            try:
                import clip
                self._model, self._preprocess = clip.load("ViT-B/32", device=self._device)
                self._dim = 512
                loaded = True
            except (ImportError, Exception):
                pass

        # 3. HuggingFace transformers CLIPModel 回退
        if not loaded:
            try:
                from transformers import CLIPModel, CLIPProcessor
                self._hf_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
                self._model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(self._device)
                self._model.eval()
                self._dim = self._model.config.projection_dim
                loaded = True
            except Exception:
                pass

        if not loaded:
            print("[CLIP] 所有 CLIP 后端均未安装，使用零向量回退")

    @property
    def dim(self) -> int:
        return getattr(self, '_dim', 512)

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def encode(self, image: Image.Image) -> np.ndarray:
        """提取 CLIP 图像嵌入 (512-dim)"""
        if not self.is_available:
            return np.zeros(self.dim, dtype=np.float32)
        import torch
        with torch.no_grad():
            if self._hf_processor is not None:
                inputs = self._hf_processor(images=image, return_tensors="pt").to(self._device)
                features = self._model.get_image_features(**inputs)
            else:
                img_tensor = self._preprocess(image).unsqueeze(0).to(self._device)
                features = self._model.encode_image(img_tensor)
            return features.cpu().numpy().squeeze()

    def similarity(self, img1: Image.Image, img2: Image.Image) -> float:
        f1 = self.encode(img1)
        f2 = self.encode(img2)
        norm = np.linalg.norm(f1) * np.linalg.norm(f2)
        return float(np.dot(f1, f2) / norm) if norm > 0 else 0.0


class ImageHasher:
    """感知哈希 — 跨平台图像重复/近似检测"""

    @staticmethod
    def phash(image: Image.Image, hash_size: int = 8) -> str:
        """感知哈希 (pHash): 基于 DCT，对缩放/压缩鲁棒"""
        if not _is_cv2_available:
            return "0" * (hash_size * hash_size)
        img = np.array(image.convert("L"), dtype=np.float32)
        img = cv2.resize(img, (32, 32))
        dct = cv2.dct(img)
        dct_low = dct[:hash_size, :hash_size]
        mean = dct_low.mean()
        return ''.join('1' if b > mean else '0' for b in dct_low.flatten())

    @staticmethod
    def dhash(image: Image.Image, hash_size: int = 8) -> str:
        """差异哈希 (dHash): 基于相邻像素梯度，对亮度变化鲁棒"""
        if not _is_cv2_available:
            return "0" * (hash_size * hash_size)
        img = np.array(image.convert("L"), dtype=np.float32)
        img = cv2.resize(img, (hash_size + 1, hash_size))
        diff = img[:, 1:] > img[:, :-1]
        return ''.join('1' if b else '0' for b in diff.flatten())

    @staticmethod
    def hamming_distance(h1: str, h2: str) -> int:
        return sum(c1 != c2 for c1, c2 in zip(h1, h2))

    def is_same_image(self, img1: Image.Image, img2: Image.Image,
                      threshold: int = 10) -> bool:
        return self.hamming_distance(self.phash(img1), self.phash(img2)) <= threshold


class ImageColorSentiment:
    """基于色彩统计的图像情感倾向 (HSV 3-dim)"""

    def extract(self, image: Image.Image) -> np.ndarray:
        if not _is_cv2_available:
            return np.zeros(3, dtype=np.float32)
        img = np.array(image.convert("RGB"))
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        warm_mask = ((hsv[:, :, 0] < 30) | (hsv[:, :, 0] > 150))
        warm_ratio = warm_mask.mean()
        avg_saturation = hsv[:, :, 1].mean() / 255.0
        avg_brightness = hsv[:, :, 2].mean() / 255.0
        return np.array([warm_ratio, avg_saturation, avg_brightness], dtype=np.float32)
