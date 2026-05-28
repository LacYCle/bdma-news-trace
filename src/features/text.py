"""文本特征提取器

基于 Chinese-RoBERTa 的语义编码 + 细粒度情感分析 + 语言学统计特征。

依赖:
  transformers, torch, numpy
"""

import numpy as np
from typing import Optional

_is_torch_available = False
try:
    import torch
    from transformers import AutoTokenizer, AutoModel
    _is_torch_available = True
except ImportError:
    pass


class TextEncoder:
    """中文文本语义编码器 — CLS embedding (768-dim)"""

    def __init__(self, model_name: str = "hfl/chinese-roberta-wwm-ext",
                 device: str = None):
        if not _is_torch_available:
            raise ImportError("TextEncoder 需要安装 torch 和 transformers")
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self._device)
        self.model.eval()
        self._dim = self.model.config.hidden_size

    @property
    def dim(self) -> int:
        return self._dim

    @torch.no_grad()
    def encode(self, text: str, max_length: int = 256) -> np.ndarray:
        """提取单条文本的 CLS 嵌入 (768-dim)"""
        if not text or not text.strip():
            return np.zeros(self._dim, dtype=np.float32)
        inputs = self.tokenizer(
            text[:max_length * 2], max_length=max_length,
            padding=True, truncation=True, return_tensors="pt"
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        outputs = self.model(**inputs)
        return outputs.last_hidden_state[:, 0, :].cpu().numpy().squeeze()

    @torch.no_grad()
    def encode_batch(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        """批量编码"""
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            inputs = self.tokenizer(
                batch, max_length=256, padding=True,
                truncation=True, return_tensors="pt"
            )
            inputs = {k: v.to(self._device) for k, v in inputs.items()}
            outputs = self.model(**inputs)
            cls_emb = outputs.last_hidden_state[:, 0, :].cpu().numpy()
            embeddings.append(cls_emb)
        return np.vstack(embeddings) if embeddings else np.empty((0, self._dim))


class ChineseSentimentAnalyzer:
    """中文细粒度情感分析器 — 7 类情感 + 极性 + 唤起度"""

    EMOTION_LABELS = ["愤怒", "悲伤", "惊讶", "喜悦", "恐惧", "厌恶", "中性"]
    POLARITY_MAP = {
        "愤怒": -0.8, "悲伤": -0.6, "惊讶": 0.1,
        "喜悦": 0.9, "恐惧": -0.4, "厌恶": -0.7, "中性": 0.0,
    }

    def __init__(self, model_name: str = "uer/roberta-base-finetuned-jd-binary-chinese",
                 device: str = None):
        if not _is_torch_available:
            raise ImportError("ChineseSentimentAnalyzer 需要安装 torch 和 transformers")
        from transformers import pipeline
        dev = 0 if (device or ("cuda" if torch.cuda.is_available() else "cpu")) == "cuda" else -1
        # 使用 text-classification pipeline
        try:
            self.classifier = pipeline(
                "text-classification", model=model_name,
                device=dev, top_k=None,
            )
            self._model_loaded = True
        except Exception:
            # 模型不可用时回退到简单规则
            self.classifier = None
            self._model_loaded = False
            print("[Sentiment] 模型加载失败，使用规则回退")

    def analyze(self, text: str) -> dict:
        if self.classifier is not None and self._model_loaded:
            return self._analyze_with_model(text)
        return self._analyze_with_rules(text)

    def _analyze_with_model(self, text: str) -> dict:
        results = self.classifier(text[:512])
        scores = {}
        if isinstance(results, list) and len(results) > 0:
            first = results[0]
            if isinstance(first, dict):
                scores[first.get("label", "")] = first.get("score", 1.0)
            elif isinstance(first, list):
                for r in first:
                    scores[r.get("label", "")] = r.get("score", 0.0)

        # 映射模型输出标签到统一情感维度
        # uer/roberta-base-finetuned-jd-binary-chinese: positive/negative
        # 通用模型可能返回英语或中文标签
        pos_score = 0.0
        neg_score = 0.0
        for label, score in scores.items():
            label_lower = label.lower()
            if any(w in label_lower for w in ["positive", "正面", "喜悦", "pos", "4", "5"]):
                pos_score = max(pos_score, score)
            elif any(w in label_lower for w in ["negative", "负面", "愤怒", "悲伤", "neg", "1", "2", "3"]):
                neg_score = max(neg_score, score)

        emotions = {"正面": pos_score, "负面": neg_score}
        polarity = pos_score * 0.8 - neg_score * 0.8
        arousal = max(pos_score, neg_score)
        dominant = "正面" if pos_score >= neg_score else "负面"
        return {"emotions": emotions, "polarity": float(polarity),
                "arousal": float(arousal), "dominant": dominant}

    def _analyze_with_rules(self, text: str) -> dict:
        """基于词典的简单情感规则回退"""
        pos_words = ["好", "棒", "赞", "优秀", "厉害", "美", "爱", "喜", "乐", "赢",
                     "成功", "突破", "创新", "进步", "支持", "感谢", "希望"]
        neg_words = ["差", "烂", "糟", "悲", "怒", "恨", "恶", "失败", "崩溃",
                     "暴跌", "丑闻", "造假", "腐败", "谴责", "抗议"]
        pos_count = sum(1 for w in pos_words if w in text)
        neg_count = sum(1 for w in neg_words if w in text)
        total = max(pos_count + neg_count, 1)
        pos_score = pos_count / total
        neg_score = neg_count / total
        polarity = pos_score * 0.7 - neg_score * 0.7
        emotions = {"正面": pos_score, "负面": neg_score}
        dominant = "正面" if pos_score >= neg_score else "负面"
        return {"emotions": emotions, "polarity": float(polarity),
                "arousal": float(max(pos_score, neg_score)), "dominant": dominant}


class TextStatistics:
    """文本语言学统计特征"""

    def extract(self, text: str) -> dict:
        if not text:
            return {k: 0.0 for k in self._feature_names()}
        length = max(len(text), 1)
        sentences = max(text.count("。") + text.count("！") + text.count("？") + text.count("\n"), 1)
        return {
            "char_count": min(len(text), 10000) / 1000.0,
            "sentence_count": float(sentences),
            "avg_sentence_len": length / sentences / 100.0,
            "exclamation_ratio": text.count("！") / length * 10,
            "question_ratio": text.count("？") / length * 10,
            "has_hashtag": 1.0 if "#" in text else 0.0,
            "has_mention": 1.0 if "@" in text else 0.0,
            "url_count": min(text.count("http"), 5) / 5.0,
        }

    def _feature_names(self) -> list[str]:
        return ["char_count", "sentence_count", "avg_sentence_len",
                "exclamation_ratio", "question_ratio", "has_hashtag",
                "has_mention", "url_count"]


class TextFeatureExtractor:
    """文本特征统一提取器 — 输出 ~784-dim 向量"""

    def __init__(self, device: str = None, load_encoder: bool = True,
                 load_sentiment: bool = True):
        self.encoder: Optional[TextEncoder] = None
        self.sentiment: Optional[ChineseSentimentAnalyzer] = None
        self.stats = TextStatistics()

        if load_encoder and _is_torch_available:
            try:
                self.encoder = TextEncoder(device=device)
            except Exception as e:
                print(f"[TextFeature] 编码器加载失败: {e}")

        if load_sentiment and _is_torch_available:
            try:
                self.sentiment = ChineseSentimentAnalyzer(device=device)
            except Exception as e:
                print(f"[TextFeature] 情感分析器加载失败: {e}")

    @property
    def dim(self) -> int:
        d = 0
        if self.encoder:
            d += self.encoder.dim  # 768
        if self.sentiment:
            d += 8  # polarity + arousal + 6 emotions (non-neutral)
        d += 8  # statistics
        return d

    def extract(self, text: str) -> np.ndarray:
        vectors = []

        if self.encoder:
            try:
                vectors.append(self.encoder.encode(text))
            except Exception:
                vectors.append(np.zeros(self.encoder.dim, dtype=np.float32))

        if self.sentiment:
            try:
                result = self.sentiment.analyze(text)
                vec = np.array([
                    result["polarity"],
                    result["arousal"],
                    result["emotions"].get("愤怒", 0),
                    result["emotions"].get("喜悦", 0),
                    result["emotions"].get("悲伤", 0),
                    result["emotions"].get("惊讶", 0),
                    result["emotions"].get("恐惧", 0),
                    result["emotions"].get("厌恶", 0),
                ], dtype=np.float32)
                vectors.append(vec)
            except Exception:
                vectors.append(np.zeros(8, dtype=np.float32))

        stats = self.stats.extract(text)
        vectors.append(np.array(list(stats.values()), dtype=np.float32))

        return np.concatenate(vectors)

    def extract_sentiment_summary(self, text: str) -> dict:
        """仅提取情感摘要 (不编码语义)"""
        if self.sentiment:
            return self.sentiment.analyze(text)
        return ChineseSentimentAnalyzer()._analyze_with_rules(text)
