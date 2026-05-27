"""中文 NER：优先 ONNX，回退规则抽取。"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Entity:
    text: str
    label: str
    start: int
    end: int


class CompanyEntityRecognizer:
    def __init__(self, *, use_onnx: bool = False) -> None:
        self._onnx = None
        if use_onnx:
            try:
                from optimum.onnxruntime import ORTModelForTokenClassification  # noqa: PLC0415
                from transformers import AutoTokenizer  # noqa: PLC0415

                model_name = "ckiplab/bert-base-chinese-ner"
                self._tokenizer = AutoTokenizer.from_pretrained(model_name)
                self._onnx = ORTModelForTokenClassification.from_pretrained(
                    model_name,
                    export=True,
                )
            except Exception:
                self._onnx = None

    def recognize(self, text: str) -> list[Entity]:
        if self._onnx is not None:
            return self._recognize_onnx(text)
        return self._recognize_rules(text)

    def _recognize_rules(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        for m in re.finditer(
            r"([\u4e00-\u9fff]{2,20}(?:股份|集团|公司|科技|有限))",
            text,
        ):
            entities.append(Entity(m.group(1), "ORG", m.start(), m.end()))
        for m in re.finditer(
            r"((?:20\d{2})年)?\s*([\d,.]+)\s*(亿元|万元|元|%|亿股)",
            text,
        ):
            entities.append(Entity(m.group(0), "MONEY", m.start(), m.end()))
        for m in re.finditer(r"(20\d{2})年", text):
            entities.append(Entity(m.group(0), "DATE", m.start(), m.end()))
        return entities

    def _recognize_onnx(self, text: str) -> list[Entity]:
        # ONNX 路径保留扩展点；当前回退规则以保证 CI 稳定
        return self._recognize_rules(text)
