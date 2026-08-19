from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from models import Question

LOGGER = logging.getLogger(__name__)
ID_PATTERN = re.compile(r"(?<![\w-])(\d{1,2}[-—–_](?:基础|综合|拓展)[-—–_]\d{1,3})(?![\w-])", re.I)
HEADING_ID_PATTERN = re.compile(
    r"(?m)^\s{0,3}(?:#{1,6}\s*)?(?:题目\s*)?[\[【(（]?"
    r"(?P<id>\d{1,2}[-—–_](?:基础|综合|拓展)[-—–_]\d{1,3})[\]】)）]?[^\n]*$",
    re.I,
)
SOLUTION_PATTERN = re.compile(r"(?im)^\s{0,3}#{1,6}\s*(?:参考答案|答案|详细解析|解析|解答|踩坑点)[：:]?\s*$")
ANSWER_LINE_PATTERN = re.compile(r"(?im)^\s*(?:\*\*)?(?:参考答案|答案)(?:\*\*)?\s*[：:]\s*(.+?)\s*$")
GROUP_HEADING_PATTERN = re.compile(r"(?m)^#{2,4}\s+(.+?)\s*$")
GROUP_QUESTION_PATTERN = re.compile(
    r"(?m)^(?:\*\*\((?P<bold>\d+)\)\*\*|(?P<plain>\d+)[.．、]|（(?P<full>\d+)）)\s*"
)


@dataclass(slots=True)
class LoadReport:
    questions: list[Question] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    json_files: int = 0
    markdown_files: int = 0
    matched_bodies: int = 0
    missing_bodies: int = 0


class DataLoader:
    """Scan metadata and Markdown, joining both by a normalized question ID."""

    def __init__(self, data_dir: str | Path, content_dirs: Iterable[str | Path] | None = None):
        self.data_dir = Path(data_dir).expanduser()
        self.content_dirs = [Path(path).expanduser() for path in (content_dirs or []) if str(path).strip()]

    @staticmethod
    def normalize_id(value: str) -> str:
        cleaned = str(value).strip().replace("—", "-").replace("–", "-").replace("_", "-")
        parts = [part.strip() for part in cleaned.split("-") if part.strip()]
        if len(parts) == 3 and parts[0].isdigit() and parts[2].isdigit():
            return f"{int(parts[0]):02d}-{parts[1]}-{int(parts[2]):02d}"
        return cleaned

    def load(self) -> LoadReport:
        report = LoadReport()
        if not self.data_dir.exists():
            report.warnings.append(f"数据目录不存在：{self.data_dir}")
            return report
        if not self.data_dir.is_dir():
            report.warnings.append(f"数据路径不是目录：{self.data_dir}")
            return report

        json_files = sorted(self.data_dir.rglob("*.json"))
        markdown_roots = [self.data_dir, *self.content_dirs]
        markdown_files = sorted({
            path
            for root in markdown_roots
            if root.exists() and root.is_dir()
            for pattern in ("*.md", "*.markdown")
            for path in root.rglob(pattern)
        })
        report.json_files = len(json_files)
        report.markdown_files = len(markdown_files)

        metadata: dict[str, dict[str, Any]] = {}
        for path in json_files:
            try:
                for raw in self._read_json_records(path):
                    question_id = self.normalize_id(raw.get("id") or raw.get("question_id") or "")
                    if not question_id:
                        continue
                    candidate = dict(raw)
                    candidate["id"] = question_id
                    candidate.setdefault("source_file", str(path))
                    metadata[question_id] = self._merge_record(metadata.get(question_id), candidate)
            except Exception as exc:  # one bad source must not break the whole bank
                message = f"跳过无法读取的 JSON：{path.name}（{exc}）"
                LOGGER.warning(message)
                report.warnings.append(message)

        bodies: dict[str, dict[str, Any]] = {}
        for path in markdown_files:
            try:
                text = path.read_text(encoding="utf-8-sig")
                parsed = self._parse_markdown(text, path)
                if not parsed:
                    parsed, grouped_warnings = self._parse_grouped_markdown(text, path, metadata)
                    report.warnings.extend(grouped_warnings)
                for question_id, body in parsed.items():
                    bodies[question_id] = self._merge_record(bodies.get(question_id), body)
            except Exception as exc:
                message = f"跳过无法解析的 Markdown：{path.name}（{exc}）"
                LOGGER.warning(message)
                report.warnings.append(message)

        all_ids = list(metadata)
        all_ids.extend(question_id for question_id in bodies if question_id not in metadata)
        for question_id in all_ids:
            raw = self._merge_record(metadata.get(question_id), bodies.get(question_id))
            raw["id"] = question_id
            question = Question.from_dict(raw)
            if question.stem:
                report.matched_bodies += 1
            else:
                question.content_missing = True
                question.stem = f"> **题干待补录**　未在 Markdown 中找到 `{question.id}` 的正文。"
                report.missing_bodies += 1
            report.questions.append(question)

        report.questions.sort(key=self._sort_key)
        if not report.questions:
            report.warnings.append("未加载到有效题目。请检查 JSON 是否包含 id 字段。")
        elif report.missing_bodies:
            report.warnings.append(
                f"已加载 {len(report.questions)} 条元数据，其中 {report.missing_bodies} 题缺少正文；"
                "放入带题目 ID 标题的 Markdown 后会自动关联。"
            )
        return report

    @classmethod
    def _parse_grouped_markdown(
        cls, text: str, path: Path, metadata: dict[str, dict[str, Any]]
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """Parse chapter/difficulty/type grouped files that do not contain explicit IDs."""
        chapter_number = cls._chapter_number_from_text(path.stem + "\n" + text[:300])
        if chapter_number is None:
            return {}, [f"无法从文件名识别章节编号：{path.name}"]
        prefix = f"{chapter_number:02d}-"
        headings = list(GROUP_HEADING_PATTERN.finditer(text))
        current_difficulty: str | None = None
        parsed: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        difficulties = ("基础题", "综合题", "拓展题")
        question_types = ("选择题", "填空题", "解答题")

        for index, heading in enumerate(headings):
            label = heading.group(1).strip()
            difficulty = next((item for item in difficulties if item in label), None)
            question_type = next((item for item in question_types if item in label), None)
            if difficulty and not question_type:
                current_difficulty = difficulty
                continue
            if not question_type or not current_difficulty:
                continue
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            section_text = text[heading.end() : end]
            markers = list(GROUP_QUESTION_PATTERN.finditer(section_text))
            target_ids = sorted(
                (
                    question_id
                    for question_id, raw in metadata.items()
                    if question_id.startswith(prefix)
                    and raw.get("section") == current_difficulty
                    and raw.get("question_type") == question_type
                ),
                key=lambda value: int(value.rsplit("-", 1)[-1]),
            )
            if len(markers) != len(target_ids):
                warnings.append(
                    f"{path.name} / {current_difficulty} / {question_type}："
                    f"正文 {len(markers)} 题，元数据 {len(target_ids)} 题，仅关联可确认的前 {min(len(markers), len(target_ids))} 题。"
                )
            for item_index, (marker, question_id) in enumerate(zip(markers, target_ids)):
                block_end = markers[item_index + 1].start() if item_index + 1 < len(markers) else len(section_text)
                block = section_text[marker.end() : block_end].strip()
                stem, options = cls._split_options(block)
                parsed[question_id] = {
                    "id": question_id,
                    "stem": stem,
                    "options": options,
                    "source_file": str(path),
                }
        return parsed, warnings

    @staticmethod
    def _chapter_number_from_text(value: str) -> int | None:
        digit_match = re.search(r"第\s*(\d{1,2})\s*章", value)
        if digit_match:
            return int(digit_match.group(1))
        match = re.search(r"第([零〇一二三四五六七八九十两]+)章", value)
        if not match:
            return None
        token = match.group(1)
        digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                  "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        if token == "十":
            return 10
        if "十" in token:
            left, right = token.split("十", 1)
            return (digits.get(left, 1) * 10) + digits.get(right, 0)
        return digits.get(token)

    @staticmethod
    def _read_json_records(path: Path) -> Iterable[dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, list):
            yield from (item for item in payload if isinstance(item, dict))
            return
        if isinstance(payload, dict):
            for key in ("questions", "items", "data", "records"):
                if isinstance(payload.get(key), list):
                    yield from (item for item in payload[key] if isinstance(item, dict))
                    return
            if payload.get("id") or payload.get("question_id"):
                yield payload
                return
            for key, value in payload.items():
                if isinstance(value, dict):
                    record = dict(value)
                    record.setdefault("id", key)
                    yield record

    @classmethod
    def _parse_markdown(cls, text: str, path: Path) -> dict[str, dict[str, Any]]:
        matches = list(HEADING_ID_PATTERN.finditer(text))
        if not matches:
            # Fallback for documents where IDs appear in HTML comments or plain prose.
            matches = list(ID_PATTERN.finditer(text))
        parsed: dict[str, dict[str, Any]] = {}
        for index, match in enumerate(matches):
            question_id = cls.normalize_id(match.groupdict().get("id") or match.group(1))
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[start:end].strip()
            if not block:
                continue
            solution_match = SOLUTION_PATTERN.search(block)
            stem_part = block[: solution_match.start()].strip() if solution_match else block
            solution_part = block[solution_match.end() :].strip() if solution_match else ""
            answer_match = ANSWER_LINE_PATTERN.search(solution_part or stem_part)
            answer = answer_match.group(1).strip() if answer_match else ""
            stem, options = cls._split_options(stem_part)
            parsed[question_id] = {
                "id": question_id,
                "stem": stem,
                "options": options,
                "answer": answer,
                "analysis": solution_part,
                "source_file": str(path),
            }
        return parsed

    @staticmethod
    def _split_options(text: str) -> tuple[str, list[str]]:
        option_pattern = re.compile(r"(?m)^\s*([A-DＡ-Ｄ])[.．、:]\s*(.+(?:\n(?!\s*[A-DＡ-Ｄ][.．、:]).+)*)")
        matches = list(option_pattern.finditer(text))
        if len(matches) < 2:
            return text.strip(), []
        stem = text[: matches[0].start()].strip()
        options = [f"{match.group(1).upper()}. {match.group(2).strip()}" for match in matches]
        return stem, options

    @staticmethod
    def _merge_record(base: dict[str, Any] | None, extra: dict[str, Any] | None) -> dict[str, Any]:
        result = dict(base or {})
        for key, value in (extra or {}).items():
            if value not in (None, "", [], {}):
                if key in {"tags", "core_knowledge"} and result.get(key):
                    existing = result[key] if isinstance(result[key], list) else [result[key]]
                    incoming = value if isinstance(value, list) else [value]
                    result[key] = list(dict.fromkeys([*existing, *incoming]))
                else:
                    result[key] = value
        return result

    @staticmethod
    def _sort_key(question: Question) -> tuple[int, int, str]:
        match = re.match(r"(\d+)-(?:基础|综合|拓展)-(\d+)", question.id)
        return (int(match.group(1)), int(match.group(2)), question.id) if match else (999, 999, question.id)
