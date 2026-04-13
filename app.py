"""Public-ready Streamlit portal for SCI/SSCI polishing (OpenAI + DeepSeek)."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from deepseek_polisher import DeepSeekAcademicPolisher
from document_parser import count_characters, parse_uploaded_file
from openai_polisher import OpenAIAcademicPolisher
from order_manager import create_order, get_model_pricing, get_order, mark_order_paid, submit_payment_claim
from report_writer import build_html_report
from text_splitter import count_tokens


APP_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=APP_DIR / ".env", override=True)

USAGE_FILE = Path("/tmp/sci_ssci_usage.json")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_SOURCE_CHARS = int(os.getenv("MAX_SOURCE_CHARS", "120000"))
MAX_BLOCK_COUNT = int(os.getenv("MAX_BLOCK_COUNT", "400"))
MAX_REPORT_ROWS = int(os.getenv("MAX_REPORT_ROWS", "400"))
MIN_SECONDS_BETWEEN_JOBS = int(os.getenv("MIN_SECONDS_BETWEEN_JOBS", "30"))
DAILY_REQUEST_LIMIT = int(os.getenv("DAILY_REQUEST_LIMIT", "80"))
SITE_ACCESS_CODE = os.getenv("SITE_ACCESS_CODE", "").strip()
ALLOW_USER_SUPPLIED_KEYS = os.getenv("ALLOW_USER_SUPPLIED_KEYS", "false").lower() == "true"
ADMIN_REVIEW_CODE = os.getenv("ADMIN_REVIEW_CODE", "").strip()
WECHAT_PAY_QR_URL = os.getenv("WECHAT_PAY_QR_URL", "").strip()
ALIPAY_PAY_QR_URL = os.getenv("ALIPAY_PAY_QR_URL", "").strip()


def _normalize_api_key(raw: str) -> str:
    key = (raw or "").strip().replace("\r", "").replace("\n", "")
    if key.startswith("OPENAI_API_KEY=") or key.startswith("DEEPSEEK_API_KEY="):
        key = key.split("=", 1)[1].strip()
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    key = "".join(key.split())
    return key


def _load_usage() -> dict:
    if not USAGE_FILE.exists():
        return {}
    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_usage(data: dict) -> None:
    USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _check_and_increment_daily_usage(fingerprint: str) -> tuple[bool, int]:
    today = datetime.now().strftime("%Y-%m-%d")
    data = _load_usage()
    day_bucket = data.get(today, {})
    count = int(day_bucket.get(fingerprint, 0))
    if count >= DAILY_REQUEST_LIMIT:
        return False, count

    day_bucket[fingerprint] = count + 1
    data[today] = day_bucket
    _save_usage(data)
    return True, count + 1


st.set_page_config(
    page_title="PaperPolish.cn",
    page_icon="🧪",
    layout="wide",
)

st.markdown(
    """
<style>
.block-container {max-width: 1120px; padding-top: 0.8rem; padding-bottom: 1.2rem;}
.hero {
  border: 1px solid rgba(69,220,255,.36);
  border-radius: 18px;
  padding: 20px 22px;
  background:
    radial-gradient(1200px 300px at -20% -50%, rgba(0,255,224,.18), transparent 55%),
    radial-gradient(900px 280px at 120% -40%, rgba(75,121,255,.22), transparent 55%),
    linear-gradient(135deg, #0a1225 0%, #112a52 45%, #123c68 100%);
  color: #f8fbff;
  margin-bottom: 16px;
  box-shadow: 0 10px 28px rgba(8, 22, 55, .28);
}
.hero h2 {margin: 0; font-size: 1.55rem; letter-spacing: .2px;}
.hero p {margin: 6px 0 0; opacity: .92}
.glass {
  border: 1px solid #dce8ff;
  border-radius: 14px;
  padding: 12px 14px 10px;
  background: linear-gradient(180deg, #fbfdff 0%, #f4f8ff 100%);
  min-height: 94px;
}
.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 4px 10px;
  margin-right: 6px;
  font-size: .8rem;
  border: 1px solid #d0ddf8;
  background: #eef4ff;
}
.step-title {
  font-weight: 700;
  color: #17325f;
  margin-top: 6px;
}
@media (max-width: 768px) {
  .block-container {padding-left: 0.75rem; padding-right: 0.75rem;}
  .hero h2 {font-size: 1.18rem !important;}
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hero">
  <h2>PaperPolish.cn · SCI/SSCI Translation & Polishing Lab</h2>
  <p>流程：1) 检测字数并生成订单 2) 支付并提交凭证 3) 审核通过后开始润色</p>
</div>
""",
    unsafe_allow_html=True,
)
st.info("站点已启用访问控制、限流与配额限制。")

pricing_cols = st.columns(5)
for col, name in zip(
    pricing_cols,
    ["gpt-3.5-turbo", "deepseek-chat", "gpt-4o-mini", "deepseek-reasoner", "gpt-4o"],
):
    per_1k, min_fee = get_model_pricing(name)
    col.markdown(
        f'<div class="glass"><div><span class="badge">{name}</span></div>'
        f'<div>¥ {per_1k:.1f} / 1000字</div><div>最低 ¥ {min_fee:.1f}</div></div>',
        unsafe_allow_html=True,
    )

if "logs" not in st.session_state:
    st.session_state.logs = []
if "report_html" not in st.session_state:
    st.session_state.report_html = None
if "result_base_name" not in st.session_state:
    st.session_state.result_base_name = "result"
if "stats" not in st.session_state:
    st.session_state.stats = {}
if "last_submit_ts" not in st.session_state:
    st.session_state.last_submit_ts = 0.0
if "client_fingerprint" not in st.session_state:
    st.session_state.client_fingerprint = str(uuid.uuid4())
if "current_order_id" not in st.session_state:
    st.session_state.current_order_id = ""
if "detected_chars" not in st.session_state:
    st.session_state.detected_chars = 0
if "detected_tokens" not in st.session_state:
    st.session_state.detected_tokens = 0
if "openai_key_override" not in st.session_state:
    st.session_state.openai_key_override = ""
if "deepseek_key_override" not in st.session_state:
    st.session_state.deepseek_key_override = ""


def reset_run_state() -> None:
    st.session_state.logs = []
    st.session_state.report_html = None
    st.session_state.stats = {}


def add_log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{timestamp}] {message}")


with st.sidebar:
    st.header("访问与引擎")

    if SITE_ACCESS_CODE:
        access_code = st.text_input("访问口令", value="", type="password")
        if access_code.strip() != SITE_ACCESS_CODE:
            st.warning("请输入正确访问口令后再使用。")
            st.stop()

    provider = st.radio("润色引擎", options=["OpenAI", "DeepSeek"], index=0, horizontal=True)

    openai_env_key = _normalize_api_key(os.getenv("OPENAI_API_KEY", ""))
    deepseek_env_key = _normalize_api_key(os.getenv("DEEPSEEK_API_KEY", ""))

    st.caption(f"单次文件上限：{MAX_UPLOAD_MB} MB")
    st.caption(f"单次文本上限：{MAX_SOURCE_CHARS} 字符")
    st.caption(f"同会话最小间隔：{MIN_SECONDS_BETWEEN_JOBS} 秒")

    api_key: str = ""
    if provider == "OpenAI":
        if openai_env_key:
            st.success("已检测到环境变量 OPENAI_API_KEY")
        else:
            st.warning("未检测到 OPENAI_API_KEY")

        if ALLOW_USER_SUPPLIED_KEYS:
            api_key_input = st.text_input(
                "OpenAI API Key（可覆盖环境变量）",
                value=st.session_state.openai_key_override,
                type="password",
            )
            st.session_state.openai_key_override = api_key_input
            api_key = _normalize_api_key(api_key_input) or openai_env_key
        else:
            api_key = openai_env_key
            st.caption("安全模式：已禁用前端覆盖 API Key")

        model = st.selectbox("OpenAI 模型", ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], index=0)
    else:
        if deepseek_env_key:
            st.success("已检测到环境变量 DEEPSEEK_API_KEY")
        else:
            st.warning("未检测到 DEEPSEEK_API_KEY")

        if ALLOW_USER_SUPPLIED_KEYS:
            api_key_input = st.text_input(
                "DeepSeek API Key（可覆盖环境变量）",
                value=st.session_state.deepseek_key_override,
                type="password",
            )
            st.session_state.deepseek_key_override = api_key_input
            api_key = _normalize_api_key(api_key_input) or deepseek_env_key
        else:
            api_key = deepseek_env_key
            st.caption("安全模式：已禁用前端覆盖 API Key")

        model = st.selectbox("DeepSeek 模型", ["deepseek-chat", "deepseek-reasoner"], index=0)

st.markdown('<div class="step-title">步骤 1：上传文件并检测字数</div>', unsafe_allow_html=True)
uploaded_file = st.file_uploader("上传待润色文件（.docx / .pdf）", type=["docx", "pdf"], key="upload_main")
scan_btn = st.button("检测字数并生成订单", type="secondary", disabled=uploaded_file is None)

if scan_btn:
    reset_run_state()

    if uploaded_file is not None:
        file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
        if file_size_mb > MAX_UPLOAD_MB:
            st.error(f"文件过大：{file_size_mb:.1f} MB。当前上限为 {MAX_UPLOAD_MB} MB。")
            st.stop()

    try:
        blocks = parse_uploaded_file(uploaded_file)
        if len(blocks) > MAX_BLOCK_COUNT:
            st.error(f"段落块数量过多（{len(blocks)}），当前上限为 {MAX_BLOCK_COUNT}。")
            st.stop()

        source_chars = count_characters(blocks)
        if source_chars > MAX_SOURCE_CHARS:
            st.error(f"文本过长（{source_chars} 字符），当前上限为 {MAX_SOURCE_CHARS}。")
            st.stop()

        source_text = "\n".join(block.text for block in blocks if block.text)
        source_tokens = count_tokens(source_text, model="gpt-4o")

        order = create_order(source_chars, provider=provider, model=model)
        st.session_state.current_order_id = order.order_id
        st.session_state.detected_chars = source_chars
        st.session_state.detected_tokens = source_tokens
        st.session_state.result_base_name = Path(uploaded_file.name).stem

        st.success("字数检测完成，订单已生成。")
        st.metric("检测字符数", source_chars)
        st.metric("估算 Tokens", source_tokens)
        st.metric("应付金额（CNY）", f"¥ {order.amount_cny:.2f}")
        st.caption(
            f"计费规则：{order.model}，¥ {order.unit_price_per_1k:.1f} / 1000字，最低 ¥ {order.min_price_cny:.1f}"
        )
        st.code(f"订单号：{order.order_id}")

    except Exception as exc:  # noqa: BLE001
        st.error(f"检测失败：{exc}")

st.markdown('<div class="step-title">步骤 2：支付并提交订单校验</div>', unsafe_allow_html=True)
if st.session_state.current_order_id:
    order = get_order(st.session_state.current_order_id)
else:
    order = None

if order:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("订单号", order.order_id)
    c2.metric("金额", f"¥ {order.amount_cny:.2f}")
    c3.metric("状态", order.status)
    c4.metric("模型", order.model or model)

    qr_col1, qr_col2 = st.columns(2)
    with qr_col1:
        st.markdown("**微信支付**")
        if WECHAT_PAY_QR_URL:
            st.image(WECHAT_PAY_QR_URL, use_container_width=True)
        else:
            st.caption("未配置 WECHAT_PAY_QR_URL")
    with qr_col2:
        st.markdown("**支付宝支付**")
        if ALIPAY_PAY_QR_URL:
            st.image(ALIPAY_PAY_QR_URL, use_container_width=True)
        else:
            st.caption("未配置 ALIPAY_PAY_QR_URL")

    channel = st.selectbox("支付渠道", ["微信", "支付宝"], index=0)
    payer_note = st.text_input("付款人备注（姓名/昵称）")
    payment_ref = st.text_input("支付流水号或截图备注")
    proof_file = st.file_uploader("上传支付截图（可选）", type=["jpg", "jpeg", "png"], key="pay_proof")

    claim_btn = st.button("我已支付，提交校验", type="secondary")
    if claim_btn:
        proof_name = proof_file.name if proof_file else ""
        order = submit_payment_claim(order.order_id, channel, payer_note, payment_ref, proof_name)
        st.success("已提交支付凭证，等待审核。")

    st.markdown("### 管理员审核（仅内部）")
    admin_code_input = st.text_input("管理员审核码", type="password")
    approve_btn = st.button("审核通过并放行订单")
    if approve_btn:
        if not ADMIN_REVIEW_CODE:
            st.error("服务器未配置 ADMIN_REVIEW_CODE，无法审核。")
        elif admin_code_input.strip() != ADMIN_REVIEW_CODE:
            st.error("审核码错误。")
        else:
            order = mark_order_paid(order.order_id)
            st.success("订单已标记为已支付，可进入润色。")

st.markdown('<div class="step-title">步骤 3：订单通过后执行润色</div>', unsafe_allow_html=True)
start_btn = st.button("开始润色", type="primary", disabled=uploaded_file is None)
progress_bar = st.progress(0.0)
log_placeholder = st.empty()

if start_btn:
    reset_run_state()

    if not order:
        st.error("请先检测字数并生成订单。")
        st.stop()

    order = get_order(order.order_id)
    if not order or order.status != "paid":
        st.error("订单尚未通过校验，暂不能润色。")
        st.stop()

    effective_provider = order.provider or provider
    effective_model = order.model or model
    openai_runtime_key = _normalize_api_key(st.session_state.openai_key_override) or openai_env_key
    deepseek_runtime_key = _normalize_api_key(st.session_state.deepseek_key_override) or deepseek_env_key
    effective_api_key = openai_runtime_key if effective_provider == "OpenAI" else deepseek_runtime_key

    if not effective_api_key:
        add_log(f"错误：{effective_provider} 未提供 API Key。")
        st.error(f"未提供 {effective_provider} API Key。请在环境变量或侧边栏中配置后重试。")
        st.stop()

    now_ts = time.time()
    elapsed_since_last = now_ts - float(st.session_state.last_submit_ts)
    if elapsed_since_last < MIN_SECONDS_BETWEEN_JOBS:
        wait_sec = int(MIN_SECONDS_BETWEEN_JOBS - elapsed_since_last)
        st.error(f"请求过于频繁，请 {wait_sec} 秒后重试。")
        st.stop()

    allowed, new_count = _check_and_increment_daily_usage(st.session_state.client_fingerprint)
    if not allowed:
        st.error("今日配额已用完，请明日再试。")
        st.stop()

    st.session_state.last_submit_ts = now_ts

    try:
        add_log("开始解析上传文档...")
        blocks = parse_uploaded_file(uploaded_file)
        source_chars = count_characters(blocks)
        source_text = "\n".join(block.text for block in blocks if block.text)
        source_tokens = count_tokens(source_text, model="gpt-4o")
        progress_bar.progress(0.05)

        add_log(
            f"解析完成：共 {len(blocks)} 个文本块，{source_chars} 字符，估算 {source_tokens} tokens。今日请求计数：{new_count}/{DAILY_REQUEST_LIMIT}。"
        )

        if effective_provider == "OpenAI":
            polisher = OpenAIAcademicPolisher(api_key=effective_api_key, model=effective_model, max_retries=3)
        else:
            polisher = DeepSeekAcademicPolisher(api_key=effective_api_key, model=effective_model, max_retries=3)

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

        if len(report_rows) > MAX_REPORT_ROWS:
            st.error(f"报告条目过多（{len(report_rows)}），当前上限为 {MAX_REPORT_ROWS}。")
            st.stop()

        add_log("正在生成 HTML 报告...")
        report_html = build_html_report(report_rows)

        st.session_state.report_html = report_html
        st.session_state.stats = {
            "source_chars": source_chars,
            "source_tokens": source_tokens,
            "provider": effective_provider,
            "model": effective_model,
            "daily_count": f"{new_count}/{DAILY_REQUEST_LIMIT}",
            "order_id": order.order_id,
            "amount": f"¥ {order.amount_cny:.2f}",
            **stats,
        }

        progress_bar.progress(1.0)
        add_log("润色完成。")
        st.success("润色已完成，可下载HTML报告。")

    except Exception as exc:  # noqa: BLE001
        add_log(f"处理失败：{exc}")
        st.error(f"处理失败：{exc}")

log_placeholder.code("\n".join(st.session_state.logs[-350:]) if st.session_state.logs else "等待文件上传与处理指令。", language="text")

if st.session_state.report_html:
    stats = st.session_state.stats
    st.subheader("处理结果")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("引擎", stats.get("provider", "-"))
    c2.metric("模型", stats.get("model", "-"))
    c3.metric("订单", stats.get("order_id", "-"))
    c4.metric("金额", stats.get("amount", "-"))
    c5.metric("今日配额", stats.get("daily_count", "-"))

    base_name = st.session_state.result_base_name
    st.download_button(
        label="下载段落级润色报告.html",
        data=st.session_state.report_html,
        file_name=f"{base_name}_polish_report.html",
        mime="text/html",
        use_container_width=True,
    )
