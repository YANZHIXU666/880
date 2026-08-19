from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Question:
    id: str
    chapter: str = "未分类章节"
    section: str = "基础题"
    question_type: str = "解答题"
    core_knowledge: list[str] = field(default_factory=list)
    pitfall_analysis: str = ""
    tags: list[str] = field(default_factory=list)
    recommend_weight: float = 1.0
    dimension: str = ""
    stem: str = ""
    options: list[str] = field(default_factory=list)
    answer: str = ""
    analysis: str = ""
    source_file: str = ""
    content_missing: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Question":
        def as_list(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            return [part.strip() for part in str(value).split(",") if part.strip()]

        question_id = str(raw.get("id") or raw.get("question_id") or "").strip()
        return cls(
            id=question_id,
            chapter=str(raw.get("chapter") or "未分类章节").strip(),
            section=str(raw.get("section") or raw.get("difficulty") or "基础题").strip(),
            question_type=str(raw.get("question_type") or raw.get("type") or "解答题").strip(),
            core_knowledge=as_list(raw.get("core_knowledge") or raw.get("knowledge_points")),
            pitfall_analysis=str(raw.get("pitfall_analysis") or raw.get("pitfall") or "").strip(),
            tags=as_list(raw.get("tags")),
            recommend_weight=max(0.01, float(raw.get("recommend_weight") or 1.0)),
            dimension=str(raw.get("dimension") or "").strip(),
            stem=str(raw.get("stem") or raw.get("question") or raw.get("content") or "").strip(),
            options=as_list(raw.get("options")),
            answer=str(raw.get("answer") or raw.get("reference_answer") or "").strip(),
            analysis=str(raw.get("analysis") or raw.get("solution") or raw.get("explanation") or "").strip(),
            source_file=str(raw.get("source_file") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Paper:
    title: str
    questions: list[Question]
    warnings: list[str] = field(default_factory=list)
    seed: int | None = None

    def by_type(self, question_type: str) -> list[Question]:
        return [question for question in self.questions if question.question_type == question_type]

