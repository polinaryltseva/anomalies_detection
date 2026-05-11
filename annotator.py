"""Streamlit-разметчик флагов: открывает каждый из ~123 LLM-предсказаний,
показывает контекст из исходного документа, кнопки TRUE/FALSE/PARTIAL.

Запуск:
    cd C:\\Users\\Marks\\Polina
    streamlit run apps/annotator.py

Результат: data/labeled/flag_annotations.jsonl — по строке на каждое решение.
Можно прервать в любой момент, при следующем запуске — продолжит с того места.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from hashlib import md5
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st  # noqa: E402

from tender_anomaly.parse.extractor import extract  # noqa: E402

# === Configuration ===
REPORTS_DIRS = [ROOT / "data/reports/real_lots", ROOT / "data/reports/lots_v2"]
RAW_DIRS = [ROOT / "data/raw/manual", ROOT / "data/raw/lots"]
ANNOTATIONS_FILE = ROOT / "data/labeled/flag_annotations.jsonl"
ANNOTATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Flag Annotator", layout="wide")

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

VERDICT_COLORS = {"TRUE": "#2e7d32", "FALSE": "#c62828", "PARTIAL": "#ed6c02"}


@st.cache_data(show_spinner=False)
def _load_lot_text(lot_id: str) -> str:
    """Текст лота — все .docx/.pdf в его папке, объединены."""
    for raw_root in RAW_DIRS:
        d = raw_root / lot_id
        if d.exists() and d.is_dir():
            parts: list[str] = []
            for f in sorted(d.iterdir()):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in {".docx", ".pdf", ".rtf", ".xlsx", ".xls"}:
                    continue
                ed = extract(f)
                if ed.text:
                    parts.append(f"\n\n=== {f.name} ===\n\n{ed.text}")
            return "\n".join(parts)
    return ""


def _flag_id(tender_id: str, label: str, span_text: str) -> str:
    return md5(f"{tender_id}|{label}|{span_text[:200]}".encode()).hexdigest()[:16]


@st.cache_data(show_spinner=False)
def _load_all_flags() -> list[dict]:
    """Все флаги из всех report-ов как плоский список."""
    flags: list[dict] = []
    for d in REPORTS_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            if p.name == "_summary.json":
                continue
            try:
                report = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for f in report.get("flags", []):
                flag = dict(f)
                flag["tender_id"] = report["tender_id"]
                flag["report_path"] = str(p.relative_to(ROOT))
                flag["flag_id"] = _flag_id(
                    report["tender_id"], f["label"], f["span_text"]
                )
                flags.append(flag)
    return flags


def _load_annotations() -> dict[str, dict]:
    """Возвращает dict: flag_id → annotation."""
    if not ANNOTATIONS_FILE.exists():
        return {}
    out: dict[str, dict] = {}
    for line in ANNOTATIONS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            out[rec["flag_id"]] = rec
        except Exception:  # noqa: BLE001
            continue
    return out


def _save_annotation(flag_id: str, verdict: str, comment: str, flag: dict) -> None:
    """Append-write annotation. Если уже есть — перезаписываем файл."""
    annotations = _load_annotations()
    annotations[flag_id] = {
        "flag_id": flag_id,
        "tender_id": flag["tender_id"],
        "label": flag["label"],
        "section": flag.get("section", ""),
        "span_text": flag["span_text"],
        "confidence": flag.get("confidence", 0.0),
        "rationale": flag.get("rationale", ""),
        "regulatory_reference": flag.get("regulatory_reference", ""),
        "verdict": verdict,
        "comment": comment,
        "annotated_at": datetime.utcnow().isoformat() + "Z",
    }
    with open(ANNOTATIONS_FILE, "w", encoding="utf-8") as f:
        for ann in annotations.values():
            f.write(json.dumps(ann, ensure_ascii=False) + "\n")


def _highlight_span(text: str, span: str, max_context: int = 1500) -> str:
    """Найти span в тексте, вернуть HTML с подсветкой и контекстом."""
    if not text or not span:
        return "<i>(нет контекста)</i>"
    idx = text.find(span)
    if idx < 0:
        # Попробуем нормализованный поиск (убрать множественные пробелы)
        import re
        norm_text = re.sub(r"\s+", " ", text)
        norm_span = re.sub(r"\s+", " ", span)
        idx_norm = norm_text.find(norm_span)
        if idx_norm < 0:
            return f"<i>(span не найден в исходнике, может быть из xlsx)</i><br/><br/><b>Span:</b> «{span[:300]}»"
        # Перевести offset обратно — упрощение, ищем ближайшее слово
        # Просто покажем нормализованный фрагмент
        s = max(0, idx_norm - max_context // 2)
        e = min(len(norm_text), idx_norm + len(norm_span) + max_context // 2)
        prefix = norm_text[s:idx_norm]
        match = norm_text[idx_norm:idx_norm + len(norm_span)]
        suffix = norm_text[idx_norm + len(norm_span):e]
        return (
            (("…" + prefix) if s > 0 else prefix)
            + f'<mark style="background:#fff176;padding:2px 4px;border-radius:3px;font-weight:600;">{match}</mark>'
            + (suffix + ("…" if e < len(norm_text) else ""))
        )
    s = max(0, idx - max_context // 2)
    e = min(len(text), idx + len(span) + max_context // 2)
    prefix = text[s:idx]
    match = text[idx:idx + len(span)]
    suffix = text[idx + len(span):e]
    return (
        (("…" + prefix) if s > 0 else prefix)
        + f'<mark style="background:#fff176;padding:2px 4px;border-radius:3px;font-weight:600;">{match}</mark>'
        + (suffix + ("…" if e < len(text) else ""))
    ).replace("\n", "<br/>")


# === UI ===
st.title("🏷️ Flag Annotator")
st.caption("Размечаешь предсказания LLM как TRUE / FALSE / PARTIAL для подсчёта precision.")

flags = _load_all_flags()
annotations = _load_annotations()

if "current_idx" not in st.session_state:
    # Стартуем с первого неразмеченного
    next_idx = 0
    for i, f in enumerate(flags):
        if f["flag_id"] not in annotations:
            next_idx = i
            break
    st.session_state.current_idx = next_idx

with st.sidebar:
    st.header("Прогресс")
    annotated = sum(1 for f in flags if f["flag_id"] in annotations)
    st.metric("Размечено", f"{annotated} / {len(flags)}")
    st.progress(annotated / len(flags) if flags else 0)

    if annotated:
        verdicts = {"TRUE": 0, "FALSE": 0, "PARTIAL": 0}
        for ann in annotations.values():
            verdicts[ann["verdict"]] = verdicts.get(ann["verdict"], 0) + 1
        cols = st.columns(3)
        cols[0].markdown(f'<div style="text-align:center;color:{VERDICT_COLORS["TRUE"]};font-weight:600;">TRUE: {verdicts["TRUE"]}</div>', unsafe_allow_html=True)
        cols[1].markdown(f'<div style="text-align:center;color:{VERDICT_COLORS["FALSE"]};font-weight:600;">FALSE: {verdicts["FALSE"]}</div>', unsafe_allow_html=True)
        cols[2].markdown(f'<div style="text-align:center;color:{VERDICT_COLORS["PARTIAL"]};font-weight:600;">PARTIAL: {verdicts["PARTIAL"]}</div>', unsafe_allow_html=True)

    st.divider()

    # Filter
    show_only = st.selectbox(
        "Показать",
        ["Все", "Только не размеченные", "Только TRUE", "Только FALSE", "Только PARTIAL"],
        index=1,
    )
    label_filter = st.multiselect(
        "Фильтр по метке",
        sorted({f["label"] for f in flags}),
    )

    st.divider()
    st.markdown("**Навигация**")
    col_a, col_b = st.columns(2)
    if col_a.button("⬅ Пред", use_container_width=True):
        st.session_state.current_idx = max(0, st.session_state.current_idx - 1)
        st.rerun()
    if col_b.button("След ➡", use_container_width=True):
        st.session_state.current_idx = min(len(flags) - 1, st.session_state.current_idx + 1)
        st.rerun()

    jump = st.number_input("Перейти к #", min_value=1, max_value=len(flags) if flags else 1,
                           value=st.session_state.current_idx + 1)
    if st.button("Перейти", use_container_width=True):
        st.session_state.current_idx = jump - 1
        st.rerun()


# Apply filters to navigation pool
def _matches_filter(f: dict) -> bool:
    if label_filter and f["label"] not in label_filter:
        return False
    if show_only == "Только не размеченные":
        return f["flag_id"] not in annotations
    if show_only == "Только TRUE":
        return annotations.get(f["flag_id"], {}).get("verdict") == "TRUE"
    if show_only == "Только FALSE":
        return annotations.get(f["flag_id"], {}).get("verdict") == "FALSE"
    if show_only == "Только PARTIAL":
        return annotations.get(f["flag_id"], {}).get("verdict") == "PARTIAL"
    return True


filtered_indices = [i for i, f in enumerate(flags) if _matches_filter(f)]
if not filtered_indices:
    st.warning("Нет флагов под текущий фильтр.")
    st.stop()

# Make sure current_idx is in the filtered list, else jump to first match
if st.session_state.current_idx not in filtered_indices:
    st.session_state.current_idx = filtered_indices[0]

current = flags[st.session_state.current_idx]
ann = annotations.get(current["flag_id"])

# Show position within filter
position_in_filter = filtered_indices.index(st.session_state.current_idx) + 1
st.caption(f"Позиция: {position_in_filter} / {len(filtered_indices)} (под фильтром)  |  "
           f"#{st.session_state.current_idx + 1} из {len(flags)} (всего)")

# === Main flag display ===
header_color = LABEL_COLOR.get(current["label"], "#eee")
verdict_badge = ""
if ann:
    v = ann["verdict"]
    verdict_badge = f' <span style="background:{VERDICT_COLORS[v]};color:white;padding:3px 10px;border-radius:6px;font-size:0.8em;">{v}</span>'

st.markdown(
    f'<div style="background:{header_color};padding:12px 16px;border-radius:8px;margin-bottom:14px;">'
    f'<div style="font-size:0.85em;color:#666;">📄 {current["tender_id"]}  •  раздел: <code>{current.get("section","-")}</code>  •  confidence: <b>{current.get("confidence",0):.2f}</b>{verdict_badge}</div>'
    f'<div style="font-size:1.4em;font-weight:600;margin-top:6px;">{current["label"]}</div>'
    f"</div>",
    unsafe_allow_html=True,
)

c1, c2 = st.columns([3, 2])
with c1:
    st.markdown("### Цитата (span)")
    st.markdown(f"> «{current['span_text']}»")

    st.markdown("### Контекст из исходного документа")
    full_text = _load_lot_text(current["tender_id"])
    if full_text:
        st.markdown(
            f'<div style="background:#fafafa;padding:14px;border-radius:6px;max-height:380px;'
            f'overflow-y:auto;font-size:0.9em;line-height:1.45;">'
            f'{_highlight_span(full_text, current["span_text"], max_context=2000)}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"Текст лота {current['tender_id']} не найден в data/raw/")

with c2:
    st.markdown("### Что увидел LLM")
    st.markdown(f"**Обоснование:**\n\n{current.get('rationale','-')}")
    st.markdown(f"**Регуляторная ссылка:**\n\n`{current.get('regulatory_reference','-')}`")

    st.divider()
    st.markdown("### Решение")

    # Краткое описание метки для подсказки
    label_hints = {
        "restrictive_tech_specs": "Технические характеристики избыточно специфичны (под 1 производителя)",
        "brand_or_model_targeting": "Указание марки/модели/страны без 'или эквивалент'",
        "disproportionate_qualification": "Непропорциональные требования (опыт > 3× НМЦК и т.п.)",
        "ambiguous_evaluation_criteria": "Субъективные критерии без измеримых показателей",
        "unusual_short_deadlines": "Нереалистично короткие сроки",
        "unusual_contract_terms": "Нерыночные условия (180 дн. оплата, 30% обеспечение и т.п.)",
        "documentary_burden": "Избыточные/нестандартные документы (нот. копии, спец. заключения)",
        "conflict_of_interest_signals": "ФИО, инвентарные номера, привязка к инсайдеру",
    }
    st.caption(f"💡 По codebook: {label_hints.get(current['label'], '')}")

    comment_default = ann.get("comment", "") if ann else ""

    with st.form(key=f"verdict_form_{current['flag_id']}", clear_on_submit=False):
        comment = st.text_area("Комментарий (опционально)", value=comment_default, height=70,
                               placeholder="Например: 'правильно, но span слишком широкий'")
        col_t, col_p, col_f = st.columns(3)
        true_btn = col_t.form_submit_button(
            "✅ TRUE", use_container_width=True, type="primary",
        )
        partial_btn = col_p.form_submit_button(
            "⚠️ PARTIAL", use_container_width=True,
        )
        false_btn = col_f.form_submit_button(
            "❌ FALSE", use_container_width=True,
        )

    if true_btn or partial_btn or false_btn:
        verdict = "TRUE" if true_btn else "PARTIAL" if partial_btn else "FALSE"
        _save_annotation(current["flag_id"], verdict, comment, current)
        # Auto-advance to next unannotated in filter
        next_unannotated = None
        for idx in filtered_indices:
            if idx > st.session_state.current_idx and flags[idx]["flag_id"] not in _load_annotations():
                next_unannotated = idx
                break
        if next_unannotated is not None:
            st.session_state.current_idx = next_unannotated
        else:
            st.session_state.current_idx = min(len(flags) - 1, st.session_state.current_idx + 1)
        # Bust cache for fresh annotations
        st.cache_data.clear()
        st.rerun()

    if ann:
        st.success(f"Уже размечен как **{ann['verdict']}** ({ann['annotated_at'][:19]}). "
                   f"Можно перезаписать решение через те же кнопки.")
