"""Минимальное демо для защиты ВКР: загрузить тендерный документ
→ парсинг → LLM baseline → подсветка проблемных span-ов в исходном тексте.

Запуск:
    streamlit run apps/demo.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st  # noqa: E402

from tender_anomaly.models.baseline_llm import make_predictor  # noqa: E402
from tender_anomaly.models.schema import Flag, RiskReport  # noqa: E402
from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

st.set_page_config(page_title="Tender Anomaly Detection", layout="wide")
st.title("Tender Anomaly Detection — demo")
st.caption("Демо детекции аномалий в тендерной документации 223-ФЗ. Модель: LLM API + классификационная схема v1.0 (8 меток).")

with st.sidebar:
    st.header("Параметры")
    provider = st.selectbox("LLM провайдер", options=["openai", "anthropic"], index=0)
    default_model = "gpt-4o" if provider == "openai" else "claude-opus-4-7"
    model_id = st.text_input("Model ID", value=default_model)
    show_low_conf = st.checkbox("Показывать flags с confidence < 0.5", value=False)

uploaded = st.file_uploader(
    "Загрузить тендерный документ (PDF / DOCX / RTF)",
    type=["pdf", "docx", "rtf"],
)

LEVEL_COLOR = {"low": "#2e7d32", "medium": "#ed6c02", "high": "#c62828"}
LABEL_COLOR = {
    "restrictive_tech_specs": "#fff59d",
    "brand_or_model_targeting": "#ffab91",
    "disproportionate_qualification": "#ce93d8",
    "ambiguous_evaluation_criteria": "#90caf9",
    "unusual_short_deadlines": "#a5d6a7",
    "unusual_contract_terms": "#ffcc80",
    "documentary_burden": "#b39ddb",
    "conflict_of_interest_signals": "#ef9a9a",
}


def highlight(text: str, flags: list[Flag]) -> str:
    """Подсвечивает span-ы в HTML."""
    if not flags:
        return text.replace("\n", "<br/>")
    chunks = []
    cursor = 0
    spans = []
    for f in flags:
        idx = text.find(f.span_text)
        if idx >= 0:
            spans.append((idx, idx + len(f.span_text), f))
    spans.sort()
    for s, e, f in spans:
        if s < cursor:
            continue
        chunks.append(text[cursor:s])
        color = LABEL_COLOR.get(f.label, "#fff176")
        chunks.append(
            f'<mark style="background:{color};padding:1px 3px;border-radius:3px;" '
            f'title="{f.label} (conf {f.confidence:.2f}): {f.rationale}">'
            f'{text[s:e]}</mark>'
        )
        cursor = e
    chunks.append(text[cursor:])
    return "".join(chunks).replace("\n", "<br/>")


if uploaded:
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as fp:
        fp.write(uploaded.getvalue())
        tmp_path = Path(fp.name)

    with st.spinner(f"Парсинг {uploaded.name}…"):
        extracted = extract(tmp_path)
    if extracted.error or not extracted.text:
        st.error(f"Не удалось извлечь текст: {extracted.error}")
        st.stop()

    sections = merge_sections(segment(extracted.text))
    st.success(
        f"Извлечено: {len(extracted.text):,} символов, {len(sections)} секций "
        f"({extracted.extraction_method})"
    )

    if st.button("Запустить LLM-baseline", type="primary"):
        try:
            predictor = make_predictor(provider=provider, model=model_id)
        except RuntimeError as exc:
            st.error(str(exc)); st.stop()

        progress = st.progress(0.0, "Анализ секций…")
        report_holder: dict = {}

        with st.spinner("LLM thinking…"):
            report = predictor.predict_document(
                tender_id=uploaded.name,
                sections=sections,
            )
            report_holder["r"] = report
        progress.progress(1.0, "Готово.")

        report = report_holder["r"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Risk score", f"{report.overall_risk_score:.2f}")
        c2.metric(
            "Risk level",
            report.risk_level.upper(),
            delta_color="off",
        )
        c3.metric("Flags found", len(report.flags))

        st.markdown(
            f'<div style="height:10px;background:{LEVEL_COLOR[report.risk_level]};'
            'border-radius:5px;margin-bottom:18px;"></div>',
            unsafe_allow_html=True,
        )

        st.subheader("Flags")
        visible = [f for f in report.flags if show_low_conf or f.confidence >= 0.5]
        if not visible:
            st.info("Признаков ограничения конкуренции не обнаружено.")
        else:
            for f in visible:
                with st.expander(
                    f"[{f.label}] conf {f.confidence:.2f} · section: {f.section}",
                    expanded=False,
                ):
                    st.markdown(f"**Цитата:** «{f.span_text}»")
                    st.markdown(f"**Обоснование:** {f.rationale}")
                    st.markdown(f"**Регулирование:** `{f.regulatory_reference}`")

        st.subheader("Текст с подсветкой")
        for sec_name, sec_text in sections.items():
            sec_flags = [f for f in visible if f.section == sec_name]
            label = f"**{sec_name}**"
            if sec_flags:
                label += f" — {len(sec_flags)} flag(s)"
            with st.expander(label, expanded=bool(sec_flags)):
                st.markdown(highlight(sec_text, sec_flags), unsafe_allow_html=True)

        st.subheader("JSON отчёт (полный)")
        st.code(report.model_dump_json(indent=2), language="json")
        st.download_button(
            "Скачать JSON",
            report.model_dump_json(indent=2),
            file_name=f"{uploaded.name}.report.json",
            mime="application/json",
        )
else:
    st.info("Загрузи документ, чтобы запустить анализ.")
