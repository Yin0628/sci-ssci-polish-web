"""Public-ready Streamlit portal for SCI/SSCI polishing (OpenAI + DeepSeek)."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from deepseek_polisher import DeepSeekAcademicPolisher
from document_parser import count_characters, parse_uploaded_file
from openai_polisher import OpenAIAcademicPolisher
from report_writer import build_html_report
from text_splitter import count_tokens


APP_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=APP_DIR / ".env", override=False)

st.set_page_config(
    page_title="SCI/SSCI 在线润色平台",
    page_icon="🧪",
    layout="wide",
)

st.markdown(
    """
<style>
.block-container {max-width: 1100px; padding-top: 1.2rem; padding-bottom: 1.2rem;}
.log-box pre {font-size: 0.84rem !important; line-height: 1.45 !important;}
@media (max-width: 768px) {
  .block-container {padding-left: 0.75rem; padding-right: 0.75rem;}
  h1 {font-size: 1.45rem !important;}
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("SCI/SSCI 在线润色平台")
st.caption("支持 OpenAI / DeepSeek 双引擎，手机与电脑浏览器均可使用")

if "logs" not in st.session_state:
    st.session_state.logs = []
if "report_html" not in st.session_state:
    st.session_state.report_html = None
if "result_base_name" not in st.session_state:
    st.session_state.result_base_name = "result"
if "stats" not in st.session_state:
    st.session_state.stats = {}


def reset_run_state() -> None:
    st.session_state.logs = []
    st.session_state.report_html = None
    st.session_state.stats = {}


log_placeholder = st.empty()


def add_log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{timestamp}] {message}")
    log_placeholder.code("\n".join(st.session_state.logs[-350:]), language="text")


with st.sidebar:
    st.header("引擎与密钥")
    provider = st.radio("润色引擎", options=["OpenAI", "DeepSeek"], index=0, horizontal=True)

    openai_env_key = os.getenv("OPENAI_API_KEY", "").strip()
    deepseek_env_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    if provider == "OpenAI":
        if openai_env_key:
            st.success("已检测到环境变量 OPENAI_API_KEY")
        else:
            st.warning("未检测到 OPENAI_API_KEY")

        api_key_input = st.text_input(
            "OpenAI API Key（可覆盖环境变量）",
            value="",
            type="password",
            placeholder="留空使用环境变量",
        )
        api_key = api_key_input.strip() or openai_env_key
        model = st.selectbox("OpenAI 模型", ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], index=0)

    else:
        if deepseek_env_key:
            st.success("已检测到环境变量 DEEPSEEK_API_KEY")
        else:
            st.warning("未检测到 DEEPSEEK_API_KEY")

        api_key_input = st.text_input(
            "DeepSeek API Key（可覆盖环境变量）",
            value="",
            type="password",
            placeholder="留空使用环境变量",
        )
        api_key = api_key_input.strip() or deepseek_env_key
        model = st.selectbox("DeepSeek 模型", ["deepseek-chat", "deepseek-reasoner"], index=0)

uploaded_file = st.file_uploader("上传待润色文件（.docx / .pdf）", type=["docx", "pdf"])
start_btn = st.button("开始润色", type="primary", disabled=uploaded_file is None)
progress_bar = st.progress(0.0)

if start_btn:
    reset_run_state()

    if not api_key:
        add_log("错误：未提供 API Key。")
        st.error("未提供 API Key。请在侧边栏输入或在 .env 中配置后重试。")
        st.stop()

    try:
        add_log("开始解析上传文档...")
        blocks = parse_uploaded_file(uploaded_file)
        source_chars = count_characters(blocks)
        source_text = "\n".join(block.text for block in blocks if block.text)
        token_model = "gpt-4o"
        source_tokens = count_tokens(source_text, model=token_model)
        progress_bar.progress(0.05)

        add_log(f"解析完成：共 {len(blocks)} 个文本块，{source_chars} 字符，估算 {source_tokens} tokens。")

        if provider == "OpenAI":
            polisher = OpenAIAcademicPolisher(api_key=api_key, model=model, max_retries=3)
        else:
            polisher = DeepSeekAcademicPolisher(api_key=api_key, model=model, max_retries=3)

        def on_progress(done: int, total: int) -> None:
            if total <= 0:
                return
            percent = 0.05 + 0.90 * (done / total)
            progress_bar.progress(min(percent, 0.95))

        _first_blocks, _second_blocks, report_rows, stats = polisher.polish_blocks(
            blocks=blocks,
            logger=add_log,
            progress_callback=on_progress,
        )

        add_log("正在生成 HTML 报告...")
        report_html = build_html_report(report_rows)

        st.session_state.report_html = report_html
        st.session_state.result_base_name = Path(uploaded_file.name).stem
        st.session_state.stats = {
            "source_chars": source_chars,
            "source_tokens": source_tokens,
            "provider": provider,
            "model": model,
            **stats,
        }

        progress_bar.progress(1.0)
        add_log("润色完成。")
        st.success("润色已完成，可下载HTML报告。")

    except Exception as exc:  # noqa: BLE001
        add_log(f"处理失败：{exc}")
        st.error(f"处理失败：{exc}")

if st.session_state.report_html:
    stats = st.session_state.stats
    st.subheader("处理结果")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("引擎", stats.get("provider", "-"))
    c2.metric("模型", stats.get("model", "-"))
    c3.metric("原文字符数", stats.get("source_chars", 0))
    c4.metric("报告条目", stats.get("report_rows", 0))

    base_name = st.session_state.result_base_name
    st.download_button(
        label="下载段落级润色报告.html",
        data=st.session_state.report_html,
        file_name=f"{base_name}_polish_report.html",
        mime="text/html",
        use_container_width=True,
    )

if not st.session_state.logs:
    st.code("等待文件上传与处理指令。", language="text")
