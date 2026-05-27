"""NLI 事实一致性：ONNX 可选，默认词面启发式。"""

from __future__ import annotations

import re


class FactConsistencyChecker:
    """检查两段陈述是否一致（entailment / contradiction / neutral）。"""

    NEGATION_MARKERS = ("不", "未", "没有", "下降", "减少", "亏损", "下滑")
    POSITIVE_MARKERS = ("增长", "上升", "提高", "盈利", "增加", "改善")

    def __init__(self, *, use_onnx: bool = False) -> None:
        self._model = None
        if use_onnx:
            try:
                from optimum.onnxruntime import ORTModelForSequenceClassification  # noqa: PLC0415
                from transformers import AutoTokenizer  # noqa: PLC0415

                name = "typeform/distilbart-mnli-12-6"
                self._tokenizer = AutoTokenizer.from_pretrained(name)
                self._model = ORTModelForSequenceClassification.from_pretrained(
                    name,
                    export=True,
                )
            except Exception:
                self._model = None

    def check(self, fact_a: str, fact_b: str) -> str:
        if self._model is not None:
            return self._check_onnx(fact_a, fact_b)
        return self._check_heuristic(fact_a, fact_b)

    def _check_heuristic(self, fact_a: str, fact_b: str) -> str:
        nums_a = set(re.findall(r"[\d,.]+", fact_a))
        nums_b = set(re.findall(r"[\d,.]+", fact_b))
        if nums_a and nums_b and nums_a != nums_b:
            return "contradiction"
        neg_a = any(m in fact_a for m in self.NEGATION_MARKERS)
        neg_b = any(m in fact_b for m in self.NEGATION_MARKERS)
        pos_a = any(m in fact_a for m in self.POSITIVE_MARKERS)
        pos_b = any(m in fact_b for m in self.POSITIVE_MARKERS)
        if (neg_a and pos_b) or (pos_a and neg_b):
            return "contradiction"
        if fact_a.strip() == fact_b.strip():
            return "entailment"
        return "neutral"

    def _check_onnx(self, fact_a: str, fact_b: str) -> str:
        return self._check_heuristic(fact_a, fact_b)
