from __future__ import annotations

import json

from data_loader import DataLoader
from engine import PaperEngine, PaperRequest
from models import Question
from pdf_exporter import PDFExporter


def test_loader_joins_markdown_and_metadata(tmp_path):
    metadata = [{
        "id": "01-基础-01", "chapter": "第一章", "section": "基础题",
        "question_type": "选择题", "core_knowledge": ["极限"], "recommend_weight": 3,
    }]
    (tmp_path / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "第一章.md").write_text(
        "## 01-基础-01\n求 $\\lim_{x\\to0}x$。\n\nA. 0\nB. 1\nC. 2\nD. 不存在\n\n### 解析\n答案：A\n由定义可得。",
        encoding="utf-8",
    )
    report = DataLoader(tmp_path).load()
    assert len(report.questions) == 1
    assert "lim" in report.questions[0].stem
    assert len(report.questions[0].options) == 4
    assert report.questions[0].analysis
    assert not report.questions[0].content_missing


def test_loader_survives_bad_file_and_missing_body(tmp_path):
    (tmp_path / "bad.json").write_text("not-json", encoding="utf-8")
    (tmp_path / "good.json").write_text(
        json.dumps([{"id": "07_综合_5", "chapter": "第七章"}], ensure_ascii=False), encoding="utf-8"
    )
    report = DataLoader(tmp_path).load()
    assert report.questions[0].id == "07-综合-05"
    assert report.questions[0].content_missing
    assert any("bad.json" in warning for warning in report.warnings)


def test_engine_is_reproducible_without_replacement_and_diverse():
    questions = [
        Question(id=f"01-基础-{i:02d}", chapter="第一章", section="基础题", question_type="选择题",
                 core_knowledge=[f"考点{i}"], recommend_weight=i)
        for i in range(1, 9)
    ]
    request = PaperRequest("测试卷", {"选择题": 5}, {"第一章"}, {"基础题": 1}, seed=42)
    first = PaperEngine(questions).generate(request)
    second = PaperEngine(questions).generate(request)
    assert [q.id for q in first.questions] == [q.id for q in second.questions]
    assert len({q.id for q in first.questions}) == 5
    assert len({k for q in first.questions for k in q.core_knowledge}) == 5


def test_pdf_html_contains_answer_space_and_solution():
    question = Question(
        id="01-综合-01", question_type="解答题", stem="计算 $x^2$", answer="$x^2$",
        analysis="步骤", pitfall_analysis="不要漏项",
    )
    from models import Paper
    exporter = PDFExporter()
    clean = exporter.render_html(Paper("测试", [question]), False)
    solved = exporter.render_html(Paper("测试", [question]), True)
    assert "answer-space" in clean
    assert "height:120mm" in clean
    assert '"Noto Sans CJK SC","WenQuanYi Micro Hei"' in clean
    assert "参考答案与踩坑提示" not in clean
    assert "参考答案与踩坑提示" in solved


def test_zero_difficulty_weight_excludes_that_section():
    questions = [
        Question(id="01-基础-01", chapter="第一章", section="基础题", question_type="选择题"),
        Question(id="01-拓展-01", chapter="第一章", section="拓展题", question_type="选择题"),
    ]
    request = PaperRequest("测试卷", {"选择题": 2}, {"第一章"}, {"基础题": 1, "拓展题": 0}, seed=1)
    paper = PaperEngine(questions).generate(request)
    assert [question.section for question in paper.questions] == ["基础题"]
    assert paper.warnings


def test_loader_maps_grouped_markdown_without_explicit_ids(tmp_path):
    metadata_dir = tmp_path / "metadata"
    content_dir = tmp_path / "content"
    metadata_dir.mkdir()
    content_dir.mkdir()
    metadata = [
        {"id": "11-基础-01", "chapter": "第十一章 矩阵", "section": "基础题", "question_type": "选择题"},
        {"id": "11-基础-02", "chapter": "第十一章 矩阵", "section": "基础题", "question_type": "填空题"},
        {"id": "11-基础-03", "chapter": "第十一章 矩阵", "section": "基础题", "question_type": "解答题"},
    ]
    (metadata_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    (content_dir / "第十一章 矩阵.md").write_text(
        "# 第十一章 矩阵\n\n## 基础题\n\n### 选择题\n\n1. 选择题干 $x$\n\nA. 甲\n\nB. 乙"
        "\n\n### 填空题\n\n**(1)** 填空题干 $y$\n\n### 解答题\n\n（1）证明题干 $z$",
        encoding="utf-8",
    )
    report = DataLoader(metadata_dir, [content_dir]).load()
    assert report.matched_bodies == 3
    assert report.missing_bodies == 0
    assert report.markdown_files == 1
    assert [question.id for question in report.questions] == ["11-基础-01", "11-基础-02", "11-基础-03"]
    assert report.questions[0].options == ["A. 甲", "B. 乙"]
