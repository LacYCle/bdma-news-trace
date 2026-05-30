"""文本特征提取器

基于 Chinese-RoBERTa 的语义编码 + 细粒度情感分析。

依赖:
  transformers, torch, numpy
"""

import numpy as np

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
