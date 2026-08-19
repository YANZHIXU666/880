from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from models import Paper, Question


@dataclass(slots=True)
class PaperRequest:
    title: str
    counts: dict[str, int]
    chapters: set[str]
    difficulty_weights: dict[str, float] = field(default_factory=dict)
    tag: str = "全部"
    seed: int | None = None
    seen_question_ids: set[str] = field(default_factory=set)
    prefer_unseen: bool = True


class PaperEngine:
    """Weighted sampling without replacement, biased toward knowledge diversity."""

    TYPE_ORDER = ("选择题", "填空题", "解答题")

    def __init__(self, questions: Iterable[Question]):
        self.questions = list(questions)

    def generate(self, request: PaperRequest) -> Paper:
        rng = random.Random(request.seed)
        selected: list[Question] = []
        warnings: list[str] = []
        seen_knowledge: Counter[str] = Counter()

        for question_type in self.TYPE_ORDER:
            desired = max(0, int(request.counts.get(question_type, 0)))
            pool = [
                question
                for question in self.questions
                if question.question_type == question_type
                and (not request.chapters or question.chapter in request.chapters)
                and (request.tag == "全部" or request.tag in question.tags)
                and request.difficulty_weights.get(question.section, 1.0) > 0
            ]
            if len(pool) < desired:
                warnings.append(f"{question_type}仅找到 {len(pool)} 题，少于请求的 {desired} 题。")
            for _ in range(min(desired, len(pool))):
                active_pool = pool
                if request.prefer_unseen:
                    unseen_pool = [q for q in pool if q.id not in request.seen_question_ids]
                    if unseen_pool:
                        active_pool = unseen_pool
                weights = [self._score(q, request.difficulty_weights, seen_knowledge) for q in active_pool]
                chosen_index = self._weighted_index(weights, rng)
                chosen = active_pool[chosen_index]
                pool.remove(chosen)
                selected.append(chosen)
                seen_knowledge.update(set(chosen.core_knowledge))

        selected.sort(key=lambda q: (self.TYPE_ORDER.index(q.question_type), q.id))
        return Paper(title=request.title.strip() or "考研数学《880》智能拼好卷", questions=selected, warnings=warnings, seed=request.seed)

    @staticmethod
    def _score(question: Question, difficulty_weights: dict[str, float], seen: Counter[str]) -> float:
        base = max(0.01, question.recommend_weight)
        difficulty = max(0.0, difficulty_weights.get(question.section, 1.0))
        if not question.core_knowledge:
            novelty = 0.85
        else:
            repeats = sum(seen[item] for item in set(question.core_knowledge))
            unseen = sum(1 for item in set(question.core_knowledge) if seen[item] == 0)
            novelty = 1.0 + 1.6 * unseen / len(set(question.core_knowledge))
            novelty /= 1.0 + 0.9 * repeats
        return max(1e-9, base * difficulty * novelty)

    @staticmethod
    def _weighted_index(weights: list[float], rng: random.Random) -> int:
        total = math.fsum(weights)
        if total <= 0:
            return rng.randrange(len(weights))
        target = rng.random() * total
        running = 0.0
        for index, weight in enumerate(weights):
            running += weight
            if running >= target:
                return index
        return len(weights) - 1
