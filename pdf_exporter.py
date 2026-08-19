from __future__ import annotations

import html
import base64
import io
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import markdown

from models import Paper, Question

INLINE_MATH = re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", re.S)
BLOCK_MATH = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.S)


class PDFExportError(RuntimeError):
    pass


class PDFExporter:
    TYPE_LABELS = (("选择题", "一、选择题"), ("填空题", "二、填空题"), ("解答题", "三、解答题"))

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or Path.cwd())

    def export(self, paper: Paper, include_solutions: bool = False) -> bytes:
        document = self.render_html(paper, include_solutions)
        if sys.platform == "win32":
            try:
                return self._export_with_chromium(document)
            except Exception:
                pass
        try:
            from weasyprint import HTML
            return HTML(string=document, base_url=str(self.base_dir)).write_pdf()
        except Exception as weasy_error:
            try:
                return self._export_with_chromium(document)
            except Exception as chromium_error:
                raise PDFExportError(
                    "PDF 生成失败：WeasyPrint 缺少 GTK/Pango，且未找到可用的 Edge/Chrome。"
                    f" WeasyPrint: {weasy_error}; Chromium: {chromium_error}"
                ) from chromium_error

    @staticmethod
    def _export_with_chromium(document: str) -> bytes:
        candidates = [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ]
        browser = next((path for path in candidates if path.exists()), None)
        if browser is None:
            raise FileNotFoundError("系统中未检测到 Edge 或 Chrome")
        with tempfile.TemporaryDirectory(prefix="math880_pdf_") as temp_name:
            temp_dir = Path(temp_name)
            html_path = temp_dir / "paper.html"
            pdf_path = temp_dir / "paper.pdf"
            html_path.write_text(document, encoding="utf-8")
            result = subprocess.run(
                [
                    str(browser), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    "--disable-extensions", f"--print-to-pdf={pdf_path}", html_path.as_uri(),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0 or not pdf_path.exists():
                raise RuntimeError(result.stderr.strip() or f"浏览器退出码 {result.returncode}")
            return pdf_path.read_bytes()

    def render_html(self, paper: Paper, include_solutions: bool = False) -> str:
        body: list[str] = [self._cover(paper)]
        number = 0
        for question_type, heading in self.TYPE_LABELS:
            questions = paper.by_type(question_type)
            if not questions:
                continue
            body.append(f'<section class="question-section"><h2>{heading}</h2>')
            for question in questions:
                number += 1
                body.append(self._question_html(question, number))
            body.append("</section>")

        if include_solutions:
            body.append('<div class="page-break"></div><section class="solutions"><h1>参考答案与踩坑提示</h1>')
            for index, question in enumerate(paper.questions, 1):
                answer = self._markdown(question.answer or "暂无独立参考答案。")
                analysis = self._markdown(question.analysis or "暂无详细解析。")
                pitfall = self._markdown(question.pitfall_analysis or "暂无踩坑提示。")
                body.append(
                    f'<article class="solution"><h3>{index}. <code>{html.escape(question.id)}</code></h3>'
                    f'<div class="answer"><strong>参考答案</strong>{answer}</div>'
                    f'<div><strong>详细解析</strong>{analysis}</div>'
                    f'<div class="pitfall"><strong>踩坑提示</strong>{pitfall}</div></article>'
                )
            body.append("</section>")
        return self._document("".join(body), paper.title)

    def _question_html(self, question: Question, number: int) -> str:
        options = ""
        if question.options:
            options = '<div class="options">' + "".join(
                f'<div class="option">{self._markdown(option)}</div>' for option in question.options
            ) + "</div>"
        answer_space = '<div class="answer-space"></div>' if question.question_type == "解答题" else ""
        return (
            f'<article class="question {"missing" if question.content_missing else ""}">'
            f'<div class="question-no">{number}</div><div class="question-body">'
            f'{self._markdown(question.stem)}{options}{answer_space}</div></article>'
        )

    @staticmethod
    def _cover(paper: Paper) -> str:
        return (
            '<header class="paper-header"><div class="edition">880 · SMART PAPER</div>'
            f'<h1>{html.escape(paper.title)}</h1>'
            '<div class="student-line"><span>姓名：________________</span><span>日期：________________</span>'
            '<span>用时：________ 分钟</span></div></header>'
        )

    @classmethod
    def _markdown(cls, value: str) -> str:
        rendered = markdown.markdown(value or "", extensions=["extra", "sane_lists"])
        return cls._math_to_vector(rendered)

    @classmethod
    def _math_to_vector(cls, rendered: str) -> str:
        def block(match: re.Match[str]) -> str:
            return cls._formula_html(match.group(1), block=True)

        def inline(match: re.Match[str]) -> str:
            return cls._formula_html(match.group(1), block=False)

        rendered = BLOCK_MATH.sub(block, rendered)
        return INLINE_MATH.sub(inline, rendered)

    @staticmethod
    @lru_cache(maxsize=4096)
    def _formula_svg(latex: str) -> str:
        from matplotlib.mathtext import math_to_image

        buffer = io.BytesIO()
        math_to_image(
            f"${html.unescape(latex.strip())}$",
            buffer,
            format="svg",
            dpi=144,
            color="#1d1c18",
        )
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    @classmethod
    def _formula_html(cls, latex: str, block: bool) -> str:
        try:
            encoded = cls._formula_svg(latex)
            image = f'<img class="math-formula" alt="{html.escape(latex.strip())}" src="data:image/svg+xml;base64,{encoded}">'
            return f'<div class="math-block">{image}</div>' if block else image
        except Exception:
            return cls._formula_mathml(latex, block)

    @staticmethod
    def _formula_mathml(latex: str, block: bool) -> str:
        try:
            from latex2mathml.converter import convert
        except Exception:
            return f"$${latex}$$" if block else f"${latex}$"
        try:
            converted = convert(html.unescape(latex.strip()))
            return f'<div class="math-block">{converted}</div>' if block else converted
        except Exception:
            return f"$${latex}$$" if block else f"${latex}$"

    @staticmethod
    def _document(body: str, title: str) -> str:
        return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{html.escape(title)}</title><style>
@page {{ size: A4; margin: 17mm 16mm 18mm; @bottom-center {{ content: counter(page) " / " counter(pages); color:#777; font-size:9pt; }} }}
* {{ box-sizing:border-box; }} body {{ color:#1d1c18; font-family:"Noto Sans CJK SC","WenQuanYi Micro Hei","WenQuanYi Zen Hei","PingFang SC","Microsoft YaHei",sans-serif; font-size:11pt; line-height:1.72; }}
.paper-header {{ border-top:5px solid #9f2d20; border-bottom:1px solid #aaa; padding:8mm 0 7mm; margin-bottom:8mm; }}
.edition {{ color:#9f2d20; font:700 8pt "Noto Sans CJK SC","WenQuanYi Micro Hei",sans-serif; letter-spacing:2px; }} h1 {{ font-size:20pt; margin:3mm 0 6mm; line-height:1.35; }}
.student-line {{ display:flex; justify-content:space-between; font-size:9.5pt; }} h2 {{ font-size:14pt; border-left:4px solid #9f2d20; padding-left:3mm; margin:9mm 0 5mm; }}
.question {{ display:grid; grid-template-columns:8mm 1fr; gap:2mm; break-inside:avoid; margin:0 0 5mm; }} .question-no {{ font-weight:800; color:#9f2d20; }}
.question-body p {{ margin:0 0 2mm; }} .options {{ display:grid; grid-template-columns:1fr 1fr; gap:1mm 5mm; margin-top:2mm; }} .option p {{ margin:0; }}
.answer-space {{ height:120mm; margin-top:5mm; background:repeating-linear-gradient(to bottom, transparent 0, transparent 11mm, #e3dfd4 11.2mm); border-top:1px dashed #bbb; }}
.missing {{ opacity:.72; }} .missing .question-body {{ border:1px dashed #c9a79f; padding:3mm; }} .page-break {{ break-before:page; }}
.solutions h1 {{ color:#9f2d20; }} .solution {{ break-inside:avoid; border-bottom:1px solid #ddd; padding:0 0 5mm; margin-bottom:5mm; }}
.solution h3 {{ margin-bottom:2mm; }} .solution strong {{ display:block; color:#9f2d20; margin:2mm 0 1mm; }} .pitfall {{ background:#f5eee8; border-left:3px solid #9f2d20; padding:2mm 3mm; }}
code {{ font-family:monospace; font-size:9pt; }} math {{ font-size:1.02em; }}
.math-formula {{ display:inline-block; width:auto; max-width:100%; vertical-align:-0.25em; }}
.math-block {{ text-align:center; margin:3mm 0; }} .math-block .math-formula {{ display:block; margin:0 auto; max-height:38mm; }}
</style></head><body>{body}</body></html>"""
