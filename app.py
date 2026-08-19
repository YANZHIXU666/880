from __future__ import annotations

import html
import os
import re
from pathlib import Path

import streamlit as st

from config import get_content_dir, get_data_dir
from data_loader import DataLoader
from deepseek_client import DeepSeekClient, DeepSeekError
from engine import PaperEngine, PaperRequest
from history import decode_seen, encode_seen
from models import Paper, Question
from pdf_exporter import PDFExportError, PDFExporter

PROJECT_DIR = Path(__file__).resolve().parent
QUESTION_TYPES = ("选择题", "填空题", "解答题")
SECTION_NUMERALS = {"选择题": "一", "填空题": "二", "解答题": "三"}


st.set_page_config(
    page_title="考研数学《880》智能拼好卷",
    page_icon="卷",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --paper: #f3f0e8;
          --paper-deep: #e9e4d8;
          --sheet: #fffdf7;
          --ink: #17221e;
          --ink-soft: #4f5d57;
          --muted: #7c817b;
          --rule: #d6d1c5;
          --jade: #315e52;
          --jade-dark: #23463d;
          --cinnabar: #b53b2f;
          --gold: #bd8b36;
        }

        html, body, [class*="st-"] {
          font-family: "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei",
            "PingFang SC", "Microsoft YaHei", sans-serif;
          color: var(--ink);
        }
        [data-testid="stIconMaterial"], .material-symbols-rounded {
          font-family: "Material Symbols Rounded" !important;
        }
        [data-testid="stAppViewContainer"] {
          background:
            linear-gradient(90deg, rgba(49,94,82,.028) 1px, transparent 1px),
            linear-gradient(rgba(49,94,82,.022) 1px, transparent 1px),
            var(--paper);
          background-size: 32px 32px;
        }
        [data-testid="stHeader"] { background: rgba(243,240,232,.82); backdrop-filter: blur(10px); }
        [data-testid="stToolbar"] { right: .65rem; }
        .block-container { max-width: 1160px; padding: 1.35rem 2.1rem 6rem; }

        [data-testid="stSidebar"] {
          background: var(--paper-deep);
          border-right: 1px solid #c9c2b4;
        }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1.1rem; }
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 { font-family: "Noto Serif CJK SC", "Songti SC", SimSun, serif; }
        [data-testid="stSidebar"] h3 {
          margin: 1.3rem 0 .65rem;
          padding-bottom: .42rem;
          border-bottom: 1px solid #c7bfb0;
          font-size: 1rem;
          letter-spacing: .04em;
        }
        [data-testid="stSidebar"] label { color: #53605a; }
        [data-testid="stSidebar"] [data-baseweb="slider"] { margin-top: -.25rem; }

        .brand-lockup { padding: .5rem 0 1rem; border-bottom: 2px solid var(--ink); }
        .brand-kicker { color: var(--cinnabar); font-size: .68rem; font-weight: 800; letter-spacing: .2em; }
        .brand-title { margin: .28rem 0 0; font: 800 1.42rem/1.2 "Noto Serif CJK SC", "Songti SC", SimSun, serif; }
        .brand-note { margin-top: .36rem; color: var(--muted); font-size: .74rem; }

        .masthead {
          position: relative;
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 2rem;
          align-items: end;
          padding: 2.3rem 0 1.35rem;
          border-top: 1px solid var(--ink);
          border-bottom: 4px double var(--ink);
          animation: settle .55s cubic-bezier(.2,.75,.25,1) both;
        }
        .masthead:before {
          content: "数学一 / 数学二 / 数学三 · 全章节题库";
          position: absolute; top: .42rem; left: 0;
          color: var(--muted); font-size: .66rem; letter-spacing: .14em;
        }
        .masthead h1 {
          margin: 0;
          max-width: 780px;
          font: 900 clamp(2.45rem, 6vw, 5.25rem)/.98 "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", SimSun, serif;
          letter-spacing: -.065em;
        }
        .masthead h1 em { color: var(--cinnabar); font-style: normal; }
        .masthead p { max-width: 640px; margin: 1rem 0 0; color: var(--ink-soft); line-height: 1.8; }
        .seal {
          width: 96px; height: 96px; display: grid; place-items: center;
          border: 3px solid var(--cinnabar); outline: 1px solid var(--cinnabar); outline-offset: 5px;
          color: var(--cinnabar); transform: rotate(2deg);
          font: 900 2rem/1 "Noto Serif CJK SC", "Songti SC", SimSun, serif;
          letter-spacing: -.08em;
        }
        .seal small { display: block; margin-top: .25rem; font: 700 .58rem/1 sans-serif; letter-spacing: .12em; text-align: center; }

        .library-line {
          display: flex; flex-wrap: wrap; align-items: center; gap: .5rem 1.45rem;
          padding: .8rem 0; border-bottom: 1px solid var(--rule); color: var(--muted); font-size: .74rem;
        }
        .library-line strong { color: var(--ink); font-size: .88rem; }
        .library-line .ready { color: var(--jade); font-weight: 800; }
        .ready-dot { display:inline-block; width:7px; height:7px; margin-right:.38rem; border-radius:50%; background:#3d806d; box-shadow:0 0 0 4px rgba(61,128,109,.12); }

        .recipe-bar {
          display: grid; grid-template-columns: 1fr auto; gap: 1.4rem; align-items: center;
          margin: 1.2rem 0 1.6rem; padding: 1rem 1.15rem;
          background: var(--sheet); border: 1px solid var(--rule); border-left: 5px solid var(--jade);
          box-shadow: 0 8px 28px rgba(30,46,40,.045);
        }
        .recipe-label { color: var(--jade); font-size: .66rem; font-weight: 900; letter-spacing: .18em; }
        .recipe-text { margin-top: .18rem; font: 800 1.02rem/1.45 "Noto Serif CJK SC", "Songti SC", SimSun, serif; }
        .recipe-aside { color: var(--muted); font-size: .72rem; text-align: right; }

        .empty-desk {
          position: relative; overflow: hidden; min-height: 370px;
          padding: 3rem clamp(1.4rem,5vw,4rem); background: var(--sheet); border: 1px solid var(--rule);
          box-shadow: 0 16px 50px rgba(33,43,38,.055);
        }
        .empty-desk:after {
          content: "880"; position: absolute; right: -1.2rem; bottom: -4.5rem;
          color: rgba(49,94,82,.045); font: 900 15rem/1 Georgia, serif; letter-spacing: -.1em;
        }
        .empty-kicker { color: var(--cinnabar); font-size: .7rem; font-weight: 900; letter-spacing: .18em; }
        .empty-desk h2 { max-width: 620px; margin: .7rem 0 .8rem; font: 900 clamp(1.8rem,4vw,3.25rem)/1.12 "Noto Serif CJK SC", "Songti SC", SimSun, serif; }
        .empty-desk > p { max-width: 590px; color: var(--ink-soft); line-height: 1.8; }
        .steps { position: relative; z-index: 1; display:grid; grid-template-columns:repeat(3,1fr); gap:1px; max-width:760px; margin-top:2rem; background:var(--rule); border:1px solid var(--rule); }
        .step { background:#faf7ef; padding:1rem; }
        .step b { display:block; margin-bottom:.25rem; color:var(--cinnabar); font:800 .7rem sans-serif; letter-spacing:.12em; }
        .step span { font-size:.82rem; color:var(--ink-soft); }

        .paper-cover {
          display: grid; grid-template-columns: 1fr auto; gap: 2rem; align-items: end;
          padding: 2.25rem 2.5rem 1.5rem; background: var(--sheet); border: 1px solid var(--rule); border-top: 7px solid var(--ink);
          box-shadow: 0 16px 46px rgba(33,43,38,.06);
        }
        .paper-overline { color:var(--cinnabar); font-size:.68rem; font-weight:900; letter-spacing:.17em; }
        .paper-cover h2 { margin:.55rem 0 .35rem; font:900 clamp(1.65rem,4vw,2.7rem)/1.16 "Noto Serif CJK SC", "Songti SC", SimSun, serif; }
        .paper-cover p { margin:0; color:var(--muted); }
        .paper-score { text-align:right; }
        .paper-score strong { display:block; color:var(--jade); font:900 2.5rem/1 Georgia,serif; }
        .paper-score span { color:var(--muted); font-size:.68rem; letter-spacing:.1em; }

        .section-heading { display:flex; align-items:center; gap:1rem; margin:2.5rem 0 .8rem; }
        .section-index { color:var(--cinnabar); font:900 2.2rem/1 Georgia,serif; }
        .section-heading h2 { margin:0; font:900 1.35rem/1.2 "Noto Serif CJK SC", "Songti SC", SimSun,serif; }
        .section-heading i { flex:1; height:1px; background:var(--rule); }
        .section-heading small { color:var(--muted); font-size:.68rem; letter-spacing:.08em; }

        .question-anchor, .export-anchor { display:none; }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.question-anchor) {
          margin: .7rem 0; padding: .35rem .5rem .15rem;
          background: rgba(255,253,247,.96); border-color: var(--rule); border-radius: 2px;
          box-shadow: 0 5px 20px rgba(31,43,37,.025);
          transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.question-anchor):hover {
          border-color:#b7b0a2; transform:translateY(-1px); box-shadow:0 10px 28px rgba(31,43,37,.055);
        }
        .q-head { display:flex; flex-wrap:wrap; gap:.55rem 1rem; align-items:baseline; margin-bottom:.35rem; }
        .q-number { color:var(--cinnabar); font:900 1.06rem Georgia,serif; }
        .q-id { color:var(--muted); font-size:.65rem; letter-spacing:.08em; }
        .q-chapter { color:var(--jade); font-size:.72rem; font-weight:800; }
        .q-level { margin-left:auto; padding:.13rem .45rem; background:#edf1ec; color:var(--jade-dark); font-size:.64rem; font-weight:800; }
        .tag-row { margin:.55rem 0 .08rem; }
        .tag { display:inline-block; margin:.12rem .26rem .12rem 0; padding:.16rem .5rem; border:1px solid #d4cec1; color:#667069; font-size:.66rem; }
        .missing-stem { padding:.8rem 1rem; border-left:3px solid var(--cinnabar); background:#fff3ed; color:#8a4037; }
        [data-testid="stExpander"] { background:#f8f5ed; border-color:var(--rule); border-radius:2px; }

        [data-testid="stVerticalBlockBorderWrapper"]:has(.export-anchor) {
          margin-top:2.2rem; padding:1rem 1.2rem 1.25rem; background:var(--jade-dark); border:0; border-radius:2px;
          color:white; box-shadow:0 18px 44px rgba(23,48,41,.15);
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.export-anchor) h3 { color:white; font-family:"Noto Serif CJK SC","Songti SC",SimSun,serif; }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.export-anchor) p { color:#dbe7e2; }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.export-anchor) button { background:#fffdf7; color:var(--ink); border-color:#fffdf7; }

        .stButton > button, .stDownloadButton > button {
          min-height: 2.65rem; border-radius:2px; border:1px solid #aaa397; font-weight:800;
          transition:transform .15s ease, box-shadow .15s ease, background .15s ease;
        }
        .stButton > button:hover, .stDownloadButton > button:hover { transform:translateY(-1px); box-shadow:0 6px 16px rgba(34,48,41,.1); }
        .stButton > button[kind="primary"] { background:var(--cinnabar); border-color:var(--cinnabar); color:white; }
        .stButton > button[kind="primary"]:hover { background:#992f26; border-color:#992f26; }
        [data-baseweb="select"] > div, [data-baseweb="input"] > div { border-radius:2px; background:#fffdf8; }
        div[data-testid="stAlert"] { border-radius:2px; }
        [data-testid="stCaptionContainer"] { color:var(--muted); }

        @keyframes settle { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:none; } }
        @media (max-width: 760px) {
          .block-container { padding: .75rem .85rem 5rem; }
          .masthead { grid-template-columns:1fr; gap:1.2rem; padding-top:2.2rem; }
          .masthead h1 { font-size:2.65rem; }
          .seal { width:68px; height:68px; position:absolute; right:.4rem; top:2.4rem; font-size:1.4rem; opacity:.88; }
          .masthead p { padding-right:.5rem; font-size:.88rem; }
          .library-line { gap:.35rem .8rem; }
          .library-line span:nth-of-type(3), .library-line span:nth-of-type(4) { display:none; }
          .recipe-bar { grid-template-columns:1fr; gap:.35rem; }
          .recipe-aside { text-align:left; }
          .empty-desk { min-height:0; padding:2rem 1.2rem; }
          .steps { grid-template-columns:1fr; }
          .paper-cover { grid-template-columns:1fr; padding:1.5rem 1.2rem 1.1rem; }
          .paper-score { text-align:left; display:flex; align-items:baseline; gap:.5rem; }
          .section-heading small { display:none; }
          .q-level { margin-left:0; }
          [data-testid="stHorizontalBlock"] { gap:.55rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner="正在校对 1121 道题……")
def load_bank(metadata_path: str, content_path: str):
    return DataLoader(metadata_path, [content_path]).load()


def chapter_number(question: Question) -> int:
    match = re.match(r"(\d+)-", question.id)
    return int(match.group(1)) if match else 999


def unique_chapters(questions: list[Question]) -> list[str]:
    order: dict[str, int] = {}
    for question in questions:
        order[question.chapter] = min(order.get(question.chapter, 999), chapter_number(question))
    return sorted(order, key=lambda chapter: (order[chapter], chapter))


def subject_chapters(chapters: list[str], questions: list[Question]) -> dict[str, list[str]]:
    number_by_chapter = {
        chapter: min((chapter_number(q) for q in questions if q.chapter == chapter), default=999)
        for chapter in chapters
    }
    return {
        "高等数学": [c for c in chapters if 1 <= number_by_chapter[c] <= 9],
        "线性代数": [c for c in chapters if 10 <= number_by_chapter[c] <= 15],
        "概率统计": [c for c in chapters if 16 <= number_by_chapter[c]],
    }


def render_question(question: Question, number: int, ai_generated: bool = False) -> None:
    with st.container(border=True):
        st.markdown('<span class="question-anchor"></span>', unsafe_allow_html=True)
        st.markdown(
            '<div class="q-head">'
            f'<span class="q-number">Q{number:02d}</span>'
            f'<span class="q-id">{html.escape(question.id)}</span>'
            f'<span class="q-chapter">{html.escape(question.chapter)}</span>'
            f'<span class="q-level">{html.escape(question.section)}</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if question.content_missing:
            st.markdown(f'<div class="missing-stem">{html.escape(question.stem)}</div>', unsafe_allow_html=True)
        else:
            st.markdown(question.stem)

        if question.options:
            option_columns = st.columns(2)
            for index, option in enumerate(question.options):
                with option_columns[index % 2]:
                    st.markdown(option)

        tags = list(dict.fromkeys([*question.tags, *question.core_knowledge[:2]]))
        if tags:
            tag_html = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in tags)
            st.markdown(f'<div class="tag-row">{tag_html}</div>', unsafe_allow_html=True)

        with st.expander("查看解析 · 答案 · 易错提醒", expanded=False):
            if ai_generated:
                st.caption("以下内容由 DeepSeek 生成，请以教材与标准答案为准。")
            if question.answer:
                st.markdown("#### 参考答案")
                st.markdown(question.answer)
            st.markdown("#### 解题路径")
            st.markdown(question.analysis or "题库暂未提供独立解析，建议结合考点标签复盘。")
            st.markdown("#### 易错提醒")
            st.markdown(question.pitfall_analysis or "暂无额外易错提示。")


def prepare_pdf(paper: Paper, include_solutions: bool, state_key: str) -> None:
    label = "解析版" if include_solutions else "纯享版"
    try:
        with st.spinner(f"正在生成 {label} A4 PDF……"):
            st.session_state[state_key] = PDFExporter(PROJECT_DIR).export(paper, include_solutions)
    except PDFExportError as exc:
        st.error(str(exc))


def build_paper(
    questions: list[Question],
    title: str,
    counts: dict[str, int],
    selected_chapters: list[str],
    difficulty_weights: dict[str, int],
    selected_tag: str,
    seed: int,
    seen_question_ids: set[str],
    prefer_unseen: bool,
    all_question_ids: list[str],
) -> None:
    if not questions:
        st.error("题库为空，请检查数据源。")
        return
    if not selected_chapters:
        st.error("至少选择一个复习章节。")
        return
    if not any(counts.values()):
        st.error("题量不能全部为 0。")
        return
    if not any(difficulty_weights.values()):
        st.error("至少保留一种难度权重。")
        return

    request = PaperRequest(
        title=title.strip() or "考研数学《880》智能拼好卷",
        counts=counts,
        chapters=set(selected_chapters),
        difficulty_weights=difficulty_weights,
        tag=selected_tag,
        seed=seed,
        seen_question_ids=seen_question_ids,
        prefer_unseen=prefer_unseen,
    )
    st.session_state.paper = PaperEngine(questions).generate(request)
    updated_seen = seen_question_ids | {question.id for question in st.session_state.paper.questions}
    st.session_state.seen_question_ids = updated_seen
    st.query_params["seen"] = encode_seen(updated_seen, all_question_ids)
    st.session_state.pop("pdf_clean", None)
    st.session_state.pop("pdf_solutions", None)


def configured_secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "") or "")
    except Exception:
        return ""


def apply_ai_solutions(paper: Paper, cache: dict[str, dict[str, str]]) -> None:
    for question in paper.questions:
        generated = cache.get(question.id)
        if not generated:
            continue
        question.answer = generated.get("answer") or question.answer
        question.analysis = generated.get("analysis") or question.analysis
        question.pitfall_analysis = generated.get("pitfall") or question.pitfall_analysis


inject_styles()

st.markdown(
    """
    <section class="masthead">
      <div>
        <h1>考研数学 <em>880</em><br>智能拼好卷</h1>
        <p>不是随机凑题，而是按章节、题型与难度组织一次有覆盖面的训练。少一点重复刷题，多一点精准复盘。</p>
      </div>
      <div class="seal">拼卷<small>PAPER LAB</small></div>
    </section>
    """,
    unsafe_allow_html=True,
)

default_path = str(get_data_dir(PROJECT_DIR))
default_content_path = str(get_content_dir(PROJECT_DIR))

with st.sidebar:
    st.markdown(
        """<div class="brand-lockup"><div class="brand-kicker">PAPER WORKBENCH</div>
        <div class="brand-title">本次训练配方</div><div class="brand-note">设定范围，生成一份真正能写的卷子</div></div>""",
        unsafe_allow_html=True,
    )
    with st.expander("数据源与重新扫描", expanded=False):
        data_path = st.text_input("元数据目录", value=default_path)
        content_path = st.text_input("题目正文目录", value=default_content_path)
        if st.button("重新扫描题库", use_container_width=True):
            load_bank.clear()
            st.session_state.pop("paper", None)
            st.rerun()

report = load_bank(data_path, content_path)
questions = report.questions
chapters = unique_chapters(questions)
subjects = subject_chapters(chapters, questions)
all_question_ids = [question.id for question in questions]
query_seen_ids = decode_seen(str(st.query_params.get("seen", "")), all_question_ids)
session_seen_ids = set(st.session_state.get("seen_question_ids", set()))
seen_question_ids = query_seen_ids | session_seen_ids
st.session_state.seen_question_ids = seen_question_ids

with st.sidebar:
    st.markdown("### 01　题量结构")
    choice_count = st.slider("选择题", 0, 15, 5)
    blank_count = st.slider("填空题", 0, 10, 3)
    solution_count = st.slider("解答题", 0, 8, 3)

    st.markdown("### 02　复习范围")
    previous = st.session_state.get("selected_chapters", chapters)
    st.session_state.selected_chapters = [chapter for chapter in previous if chapter in chapters]
    quick_a, quick_b = st.columns(2)
    if quick_a.button("全科 23 章", use_container_width=True):
        st.session_state.selected_chapters = chapters
    if quick_b.button("清空范围", use_container_width=True):
        st.session_state.selected_chapters = []
    for index, (subject, items) in enumerate(subjects.items()):
        if st.button(f"只选 {subject} · {len(items)} 章", key=f"only_{index}", use_container_width=True):
            st.session_state.selected_chapters = items
    selected_chapters = st.multiselect(
        "章节微调",
        chapters,
        key="selected_chapters",
        placeholder="选择当前复习到的章节",
    )

    st.markdown("### 03　难度配方")
    difficulty_weights = {
        "基础题": st.slider("基础 · 稳住基本盘", 0, 5, 3),
        "综合题": st.slider("综合 · 建立连接", 0, 5, 3),
        "拓展题": st.slider("拓展 · 拉开差距", 0, 5, 1),
    }
    available_tags = sorted({tag for question in questions for tag in question.tags})
    preferred = [tag for tag in ("高频真题变式", "易错概念", "压轴题型") if tag in available_tags]
    other = [tag for tag in available_tags if tag not in preferred]
    selected_tag = st.selectbox("专项聚焦", ["全部", *preferred, *other])

    st.markdown("### 04　训练进度")
    prefer_unseen = st.toggle("优先抽取从未出现的题", value=True)
    st.caption(f"已标记 {len(seen_question_ids)} / {len(questions)} 题；记录仅属于当前链接，不会影响其他用户。")
    if st.button("清空已出题记录", use_container_width=True):
        st.query_params.pop("seen", None)
        st.session_state.pop("seen_question_ids", None)
        st.session_state.pop("paper", None)
        st.rerun()

    st.markdown("### 05　DeepSeek 解析")
    secret_key = configured_secret("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
    entered_api_key = st.text_input(
        "API Key",
        value="",
        type="password",
        placeholder="已配置云端密钥" if secret_key else "sk-…",
        help="仅用于当前会话调用 DeepSeek，不会写入题库或 GitHub；云端 Secret 不会回传到浏览器。",
    )
    deepseek_api_key = entered_api_key.strip() or secret_key
    if secret_key and not entered_api_key:
        st.caption("已启用 Streamlit Secrets 中的云端密钥。")
    deepseek_model = st.selectbox("解析模型", ["deepseek-v4-flash", "deepseek-v4-pro"])

    with st.expander("试卷标题与随机种子", expanded=False):
        paper_title = st.text_input("试卷标题", "【拼好卷 01】全科交叉扫描")
        random_seed = st.number_input("随机种子", min_value=0, value=880, step=1, help="相同设置与种子可复现同一套卷。")

    generate_sidebar = st.button("开始智能组卷", type="primary", use_container_width=True, key="generate_sidebar")

st.markdown(
    f"""<div class="library-line">
      <span class="ready"><i class="ready-dot"></i>题库就绪</span>
      <span><strong>{len(questions)}</strong> 道元数据</span>
      <span><strong>{report.matched_bodies}</strong> 道正文已匹配</span>
      <span><strong>{len(chapters)}</strong> 个章节</span>
      <span>数据源 {report.json_files} JSON · {report.markdown_files} Markdown</span>
    </div>""",
    unsafe_allow_html=True,
)

for warning in report.warnings:
    st.warning(warning)

counts = {"选择题": choice_count, "填空题": blank_count, "解答题": solution_count}
total_requested = sum(counts.values())
difficulty_summary = " / ".join(f"{name.removesuffix('题')}{weight}" for name, weight in difficulty_weights.items())
tag_summary = "不限专项" if selected_tag == "全部" else f"{selected_tag}专项"
st.markdown(
    f"""<div class="recipe-bar"><div><div class="recipe-label">CURRENT RECIPE · 当前配方</div>
      <div class="recipe-text">{total_requested} 题 · {len(selected_chapters)} 章 · {html.escape(tag_summary)}</div></div>
      <div class="recipe-aside">选择 {choice_count}　填空 {blank_count}　解答 {solution_count}<br>{difficulty_summary}</div></div>""",
    unsafe_allow_html=True,
)

paper_before: Paper | None = st.session_state.get("paper")
if paper_before is None:
    st.markdown(
        """<section class="empty-desk"><div class="empty-kicker">READY WHEN YOU ARE</div>
        <h2>把复习进度，变成一张可以真正落笔的卷子。</h2>
        <p>左侧调整训练配方。系统会优先分散核心考点，并结合推荐权重无放回抽题，避免同类知识点扎堆。</p>
        <div class="steps"><div class="step"><b>STEP 01</b><span>确定题量与复习章节</span></div>
        <div class="step"><b>STEP 02</b><span>调整基础、综合、拓展倾向</span></div>
        <div class="step"><b>STEP 03</b><span>生成试卷并导出到 GoodNotes</span></div></div></section>""",
        unsafe_allow_html=True,
    )
    st.caption("手机或 iPad：点击左上角箭头展开训练配方，也可以直接按当前默认配方组卷。")
    generate_main = st.button("按当前配方生成第一套卷", type="primary", use_container_width=True, key="generate_main")
else:
    generate_main = False

if generate_sidebar or generate_main:
    build_paper(
        questions,
        paper_title,
        counts,
        selected_chapters,
        difficulty_weights,
        selected_tag,
        int(random_seed),
        seen_question_ids,
        prefer_unseen,
        all_question_ids,
    )

paper: Paper | None = st.session_state.get("paper")
if paper:
    ai_solution_cache: dict[str, dict[str, str]] = st.session_state.setdefault("ai_solution_cache", {})
    apply_ai_solutions(paper, ai_solution_cache)
    for warning in paper.warnings:
        st.warning(warning)

    knowledge_count = len({knowledge for question in paper.questions for knowledge in question.core_knowledge})
    st.markdown(
        f"""<section class="paper-cover"><div><div class="paper-overline">GENERATED PAPER · SEED {paper.seed}</div>
        <h2>{html.escape(paper.title)}</h2><p>已完成考点分散与无放回抽样 · 建议限时完成后再展开解析</p></div>
        <div class="paper-score"><strong>{len(paper.questions)}</strong><span>QUESTIONS<br>{knowledge_count} 个核心考点</span></div></section>""",
        unsafe_allow_html=True,
    )
    if st.button(
        "再组一套 · 优先未见题",
        type="primary",
        use_container_width=True,
        key="regenerate_main",
    ):
        build_paper(
            questions,
            paper_title,
            counts,
            selected_chapters,
            difficulty_weights,
            selected_tag,
            int(random_seed),
            seen_question_ids,
            prefer_unseen,
            all_question_ids,
        )
        st.rerun()

    unresolved = [question for question in paper.questions if not question.answer or not question.analysis]
    if unresolved:
        with st.container(border=True):
            st.markdown("#### DeepSeek 智能解析")
            st.caption(
                f"本卷还有 {len(unresolved)} 题缺少完整答案或解析。可一次生成并自动加入网页预览与解析版 PDF。"
            )
            generate_ai = st.button(
                "用 DeepSeek 补全本卷解析",
                disabled=not bool(deepseek_api_key.strip()),
                use_container_width=True,
            )
            if not deepseek_api_key.strip():
                st.info("请先在左侧填写 DeepSeek API Key。")
            if generate_ai:
                try:
                    with st.spinner(f"正在让 {deepseek_model} 逐题校验并生成解析……"):
                        generated = DeepSeekClient(
                            api_key=deepseek_api_key,
                            model=deepseek_model,
                        ).generate_solutions(unresolved)
                    ai_solution_cache.update(generated)
                    apply_ai_solutions(paper, ai_solution_cache)
                    st.session_state.pop("pdf_solutions", None)
                    st.success(f"已生成 {len(generated)} 题解析；建议结合教材复核关键结论。")
                except DeepSeekError as exc:
                    st.error(str(exc))

    question_index = 0
    for question_type in QUESTION_TYPES:
        group = paper.by_type(question_type)
        if not group:
            continue
        st.markdown(
            f"""<div class="section-heading"><span class="section-index">{SECTION_NUMERALS[question_type]}</span>
            <h2>{question_type}</h2><i></i><small>{len(group)} QUESTIONS</small></div>""",
            unsafe_allow_html=True,
        )
        for question in group:
            question_index += 1
            render_question(question, question_index, question.id in ai_solution_cache)

    with st.container(border=True):
        st.markdown('<span class="export-anchor"></span>', unsafe_allow_html=True)
        st.markdown("### 交付到 GoodNotes / iPad")
        st.markdown("纯享版保留答题空间；解析版在卷末附参考答案与易错提醒。两份均为 A4 中文排版。")
        clean_col, solution_col = st.columns(2)
        with clean_col:
            if st.button("生成纯享版 PDF", use_container_width=True):
                prepare_pdf(paper, False, "pdf_clean")
            if st.session_state.get("pdf_clean"):
                st.download_button(
                    "下载试卷纯享版",
                    st.session_state.pdf_clean,
                    file_name=f"{paper.title}_试卷纯享版.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
        with solution_col:
            if st.button("生成解析版 PDF", use_container_width=True):
                prepare_pdf(paper, True, "pdf_solutions")
            if st.session_state.get("pdf_solutions"):
                st.download_button(
                    "下载试卷+解析版",
                    st.session_state.pdf_solutions,
                    file_name=f"{paper.title}_试卷+解析与踩坑提示版.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
