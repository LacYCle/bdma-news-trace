"""特征提取层 — 文本 + 图像 + 跨平台匹配"""

from .text import TextEncoder, ChineseSentimentAnalyzer, TextStatistics, TextFeatureExtractor
from .image import (CLIPImageEncoder, ImageHasher, ImageOCR,
                    ImageColorSentiment, ImageFeatureExtractor)
from .matcher import CrossPlatformMatcher
