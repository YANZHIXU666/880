from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from models import Question


class DeepSeekError(RuntimeError):
    pass


@dataclass(slots=True)
class DeepSeekClient:
    api_key: str
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    timeout: int = 120

    def generate_solutions(self, questions: list[Question]) -> dict[str, dict[str, str]]:
        if not self.api_key.strip():
            raise DeepSeekError("请先配置 DeepSeek API Key。")
        if not questions:
            return {}

        items = [
            {
                "id": question.id,
                "题型": question.question_type,
                "章节": question.chapter,
                "难度": question.section,
                "题干": question.stem,
                "选项": question.options,
                "核心考点": question.core_knowledge,
                "已有易错提示": question.pitfall_analysis,
            }
            for question in questions
        ]
        system_prompt = (
            "你是严谨的考研数学教研员。请逐题给出可核验的参考答案、分步骤解析和易错提醒。"
            "所有数学公式必须保留标准 LaTeX（行内用 $...$，独立公式用 $$...$$）。"
            "只输出 JSON，不要 Markdown 代码围栏。JSON 格式必须为："
            '{"items":[{"id":"题目ID","answer":"参考答案","analysis":"详细解析",'
            '"pitfall":"易错提醒"}]}。不确定时要明确说明，不得虚构题目条件。'
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请解析以下试题并输出 json：\n" + json.dumps(items, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": 12000,
            "stream": False,
        }
        request = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key.strip()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise DeepSeekError(f"DeepSeek API 返回 {exc.code}：{detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise DeepSeekError(f"DeepSeek API 调用失败：{exc}") from exc

        try:
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            parsed_items = parsed["items"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise DeepSeekError("DeepSeek 返回内容无法解析，请重试。") from exc

        allowed_ids = {question.id for question in questions}
        solutions: dict[str, dict[str, str]] = {}
        for item in parsed_items:
            question_id = str(item.get("id") or "").strip()
            if question_id not in allowed_ids:
                continue
            solutions[question_id] = {
                "answer": str(item.get("answer") or "").strip(),
                "analysis": str(item.get("analysis") or "").strip(),
                "pitfall": str(item.get("pitfall") or "").strip(),
            }
        if not solutions:
            raise DeepSeekError("DeepSeek 未返回任何可关联的题目解析，请重试。")
        return solutions
