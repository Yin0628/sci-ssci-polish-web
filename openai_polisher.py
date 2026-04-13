"""OpenAI-based academic polishing pipeline with paragraph-level reporting."""

from __future__ import annotations

import copy
import re
import time
from datetime import timedelta
from typing import Callable, Dict, List, Optional, Tuple

from openai import OpenAI

from document_parser import Block

LONG_PARAGRAPH_CHAR_THRESHOLD = 520
MAX_SENTENCES_PER_CHUNK = 4


EVALUATION_SYSTEM_PROMPT = """你是一位严谨的英文学术写作审稿编辑。请对输入段落进行内容与语言质量评估，输出要求：
1) 先给出 1-2 句 Summary；
2) 再给出主要问题（语法、逻辑、术语、学术语体、连贯性）；
3) 最后给出可执行的修改建议；
4) 保持客观、直接，不要寒暄，不要输出与段落无关的信息。"""


FIRST_POLISH_SYSTEM_PROMPT = """你是一位学术英语编辑。请对输入英文段落进行首次润色：
- 修正语法与表达问题；
- 保持原意、数据、引文不变；
- 提升清晰度与学术规范性；
- 当句子过长时主动拆分为更易读的结构，避免连续堆叠超长句；
- 尽量形成“短句 + 中长句”交替节奏，增强可读性与学术表达张力；
- 输出仅包含润色后的英文段落。"""


SECOND_POLISH_SYSTEM_PROMPT = """你是一位顶级期刊英语编辑（Nature/Science/Cell风格）。请在首次润色结果基础上进行深度二次润色：
- 强化学术表达的精准性与凝练性；
- 优化句间衔接与论证节奏；
- 适度使用被动语态，使文风更符合期刊写作；
- 对过长段落进行逻辑分段（2-4段），并保持段间过渡自然；
- 句式节奏尽量长短交替，避免连续多句冗长结构；
- 保留全部原意、引文、术语与事实；
- 输出仅包含再次润色后的英文段落。"""


class OpenAIAcademicPolisher:
    """Run paragraph-level evaluation + two-pass polishing with OpenAI API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.2,
        max_retries: int = 3,
        timeout: int = 180,
    ) -> None:
        self.client = OpenAI(api_key=api_key, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries

    def polish_blocks(
        self,
        blocks: List[Block],
        logger: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Tuple[List[Block], List[Block], List[Dict[str, str]], Dict[str, int]]:
        """
        Process all eligible blocks.

        Returns:
            first_polish_blocks: DOCX-ready blocks after first polishing pass.
            second_polish_blocks: DOCX-ready blocks after second polishing pass.
            report_rows: paragraph-level report entries for HTML output.
            stats: summary statistics.
        """
        first_polish_blocks = copy.deepcopy(blocks)
        second_polish_blocks = copy.deepcopy(blocks)

        segments = self._collect_segments(blocks)
        report_rows: List[Dict[str, str]] = []
        total_steps = max(len(segments) * 3, 1)
        done_steps = 0

        if logger:
            logger(f"可处理段落数: {len(segments)}")

        first_polish_map: Dict[int, List[str]] = {}
        second_polish_map: Dict[int, List[str]] = {}

        for idx, seg in enumerate(segments, start=1):
            original = seg["text"]
            block_idx = seg["block_idx"]
            t0 = time.perf_counter()

            if logger:
                logger(f"段落 {idx}/{len(segments)}：内容评价中...")
            evaluation = self._chat_with_retry(
                system_prompt=EVALUATION_SYSTEM_PROMPT,
                user_prompt=f"请评估以下段落：\n\n{original}",
                stage="evaluation",
                logger=logger,
            )
            done_steps += 1
            if progress_callback:
                progress_callback(done_steps, total_steps)

            if logger:
                logger(f"段落 {idx}/{len(segments)}：首次润色中...")
            first_polish = self._chat_with_retry(
                system_prompt=FIRST_POLISH_SYSTEM_PROMPT,
                user_prompt=original,
                stage="first_polish",
                logger=logger,
            )
            done_steps += 1
            if progress_callback:
                progress_callback(done_steps, total_steps)

            if logger:
                logger(f"段落 {idx}/{len(segments)}：再次润色中...")
            second_polish = self._chat_with_retry(
                system_prompt=SECOND_POLISH_SYSTEM_PROMPT,
                user_prompt=first_polish,
                stage="second_polish",
                logger=logger,
            )
            done_steps += 1
            if progress_callback:
                progress_callback(done_steps, total_steps)

            elapsed = _format_elapsed(time.perf_counter() - t0)

            first_polish_map.setdefault(block_idx, []).append(first_polish)
            second_polish_map.setdefault(block_idx, []).append(second_polish)

            report_rows.append(
                {
                    "original": original,
                    "evaluation": evaluation,
                    "first_polish": first_polish,
                    "second_polish": second_polish,
                    "elapsed": elapsed,
                }
            )

        self._apply_outputs_to_blocks(first_polish_blocks, first_polish_map)
        self._apply_outputs_to_blocks(second_polish_blocks, second_polish_map)

        stats = {
            "segment_count": len(segments),
            "report_rows": len(report_rows),
        }
        return first_polish_blocks, second_polish_blocks, report_rows, stats

    def _chat_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        stage: str,
        logger: Optional[Callable[[str], None]] = None,
    ) -> str:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                if logger:
                    logger(f"API 调用中（{stage}，第 {attempt}/{self.max_retries} 次）...")

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]

                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    messages=messages,
                )
                content = response.choices[0].message.content or ""
                text = _normalize_output(content)

                if not text.strip():
                    raise RuntimeError("API 返回为空")

                if logger:
                    logger(f"API 调用成功（{stage}）。")
                return text

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if logger:
                    logger(f"API 调用失败（{stage}，第 {attempt} 次）: {exc}")
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))

        raise RuntimeError(f"API 调用连续失败 {self.max_retries} 次: {last_error}")

    @staticmethod
    def _collect_segments(blocks: List[Block]) -> List[Dict[str, str]]:
        segments: List[Dict[str, str]] = []
        for i, block in enumerate(blocks):
            text = (block.text or "").strip()
            if not text:
                continue
            if block.kind == "blank":
                continue
            if block.kind == "reference":
                continue
            sub_parts = _split_long_paragraph(text)
            if not sub_parts:
                continue
            for part in sub_parts:
                segments.append({"block_idx": i, "text": part})
        return segments

    @staticmethod
    def _apply_outputs_to_blocks(blocks: List[Block], output_map: Dict[int, List[str]]) -> None:
        for block_idx, parts in output_map.items():
            cleaned = [p.strip() for p in parts if p and p.strip()]
            blocks[block_idx].text = "\n\n".join(cleaned)


def _normalize_output(text: str) -> str:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:text|markdown)?", "", clean).strip()
        if clean.endswith("```"):
            clean = clean[:-3].strip()
    return clean


def _split_long_paragraph(text: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    if len(normalized) <= LONG_PARAGRAPH_CHAR_THRESHOLD:
        return [normalized]

    sentences = _split_into_sentences(normalized)
    if len(sentences) <= 1:
        return _hard_split_by_length(normalized, LONG_PARAGRAPH_CHAR_THRESHOLD)

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sentence in sentences:
        sent = sentence.strip()
        if not sent:
            continue
        sent_len = len(sent)
        should_break = (
            current
            and (
                current_len + sent_len > LONG_PARAGRAPH_CHAR_THRESHOLD
                or len(current) >= MAX_SENTENCES_PER_CHUNK
            )
        )
        if should_break:
            chunks.append(" ".join(current).strip())
            current = []
            current_len = 0

        current.append(sent)
        current_len += sent_len

    if current:
        chunks.append(" ".join(current).strip())

    return [c for c in chunks if c]


def _split_into_sentences(text: str) -> List[str]:
    raw = re.split(r"(?<=[。！？!?;；\.])\s+", text)
    sentences = [s.strip() for s in raw if s and s.strip()]
    if not sentences:
        return [text]
    return sentences


def _hard_split_by_length(text: str, max_len: int) -> List[str]:
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_len, n)
        if end < n:
            cut = max(
                text.rfind("，", start, end),
                text.rfind("。", start, end),
                text.rfind(",", start, end),
                text.rfind(";", start, end),
            )
            if cut > start + 60:
                end = cut + 1
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def _format_elapsed(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    total_seconds = td.total_seconds()
    whole = int(total_seconds)
    ms = int((total_seconds - whole) * 1_000_000)

    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    return f"{hours}:{minutes:02d}:{secs:02d}.{ms:06d}"
