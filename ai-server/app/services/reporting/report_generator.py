from __future__ import annotations

import html
import json
import math
import os
import unicodedata
from datetime import datetime, timedelta
from statistics import mean, pstdev
from typing import Any, Optional

from fpdf import FPDF
from sqlalchemy.orm import Session
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except Exception:
    HTML = None
    WEASYPRINT_AVAILABLE = False

from app.core.config import settings
from app.models.domain import Device, ErrorLog, Incident, IncidentAsset, Prediction, SensorTimeseries
from app.schemas.reporting import (
    AECQReference,
    EvidenceSummary,
    ImmediateContainmentAction,
    IncidentSummary,
    PDCAMapping,
    PredictiveAISummary,
    QualityIncidentReport,
    ReferenceDocument,
    ReportFooter,
    ReportHeader,
    RootCauseCorrectiveAction,
    RuleBasedFlags,
    SQCSummary,
    StatisticalSummary,
)
from app.services.prediction import build_timeseries_features_payload, predict_from_timeseries_summary

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(CURRENT_DIR, "NanumGothic.ttf")
FONT_BOLD_PATH = os.path.join(CURRENT_DIR, "NanumGothicBold.ttf")

REPORT_VERSION = "quality-report-v1.0"


def normalize_text(text: Any) -> str:
    if text is None:
        return ""
    return unicodedata.normalize("NFC", str(text))


def strip_markdown(text: str) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("**", "")
        .replace("__", "")
        .replace("* ", "")
        .replace(" *", " ")
    )


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        f = float(value)
        if not math.isfinite(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_str(value: Any, default: str = "N/A") -> str:
    s = normalize_text(value).strip()
    return s if s else default


def _normalize_line(line: str) -> str:
    s = strip_markdown(line).strip()
    for token in ["- ", "• ", "* ", "> "]:
        if s.startswith(token):
            s = s[len(token):].strip()
    return s


def _split_incident_description(desc: str) -> tuple[list[str], list[str]]:
    analysis: list[str] = []
    actions: list[str] = []
    seen = set()
    mode = "analysis"
    placeholder = "상세 조치 내용은 아래 분석 결과를 확인하세요."

    for raw in str(desc or "").splitlines():
        line = _normalize_line(raw)
        if not line:
            continue
        key = line.replace(" ", "").lower()
        if key in {"[분석결과]", "분석결과"}:
            mode = "analysis"
            continue
        if key in {"[조치절차]", "조치절차", "action", "actionplan"}:
            mode = "action"
            continue
        if line == placeholder:
            continue
        if line in seen:
            continue
        seen.add(line)
        if mode == "action":
            actions.append(line)
        else:
            analysis.append(line)

    return analysis, actions


def _linear_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    return 0.0 if den == 0 else num / den


def _trend_label(values: list[float]) -> str:
    if len(values) < 2:
        return "N/A"
    slope = _linear_slope(values)
    if slope > 0.02:
        return "rising"
    if slope < -0.02:
        return "falling"
    return "stable"


def _collect_rows(db: Session, incident: Incident) -> tuple[list[SensorTimeseries], list[ErrorLog], list[IncidentAsset], Optional[Device]]:
    ts_rows = (
        db.query(SensorTimeseries)
        .filter(SensorTimeseries.device_id == incident.device_id)
        .order_by(SensorTimeseries.timestamp.desc())
        .limit(240)
        .all()
    )
    ts_rows.reverse()

    error_logs = (
        db.query(ErrorLog)
        .filter(ErrorLog.device_id == incident.device_id)
        .order_by(ErrorLog.error_timestamp.desc())
        .limit(60)
        .all()
    )

    assets = db.query(IncidentAsset).filter(IncidentAsset.incident_id == incident.incident_id).all()
    device = db.query(Device).filter(Device.device_id == incident.device_id).first()
    return ts_rows, error_logs, assets, device


def _get_prediction_snapshot(db: Session, incident: Incident) -> tuple[dict[str, Any], str]:
    latest = (
        db.query(Prediction)
        .filter(Prediction.incident_id == incident.incident_id)
        .order_by(Prediction.predicted_at.desc())
        .first()
    )
    if latest:
        return (
            {
                "failure_probability": _safe_float(latest.failure_probability, 0.0) or 0.0,
                "predicted_rul_minutes": _safe_float(latest.predicted_rul_minutes, 0.0) or 0.0,
                "anomaly_score": _safe_float(latest.anomaly_score, 0.0) or 0.0,
            },
            f"db.predictions/{latest.model_name or 'unknown'}:{latest.model_version or 'unknown'}",
        )

    telemetry = build_timeseries_features_payload(
        db=db,
        device_id=str(incident.device_id),
        limit_rows=720,
        window_size=120,
        stride=30,
    )
    pred = predict_from_timeseries_summary(telemetry)
    return (
        {
            "failure_probability": _safe_float(pred.failure_probability, 0.0) or 0.0,
            "predicted_rul_minutes": _safe_float(pred.predicted_rul_minutes, 0.0) or 0.0,
            "anomaly_score": _safe_float(pred.anomaly_score, 0.0) or 0.0,
        },
        f"runtime.inference/{pred.model_source}",
    )


def _error_log_pattern(error_logs: list[ErrorLog]) -> tuple[str, bool]:
    if not error_logs:
        return "N/A", False

    by_dtc: dict[str, list[datetime]] = {}
    for row in error_logs:
        code = _safe_str(row.dtc_code, "UNKNOWN")
        if not row.error_timestamp:
            continue
        by_dtc.setdefault(code, []).append(row.error_timestamp)

    repeated_burst = False
    parts: list[str] = []
    for code, times in by_dtc.items():
        times = sorted(times)
        if len(times) >= 3:
            for i in range(len(times) - 2):
                if (times[i + 2] - times[i]) <= timedelta(minutes=10):
                    repeated_burst = True
                    break
        parts.append(f"{code} x{len(times)}")

    parts.sort()
    return ", ".join(parts[:5]), repeated_burst


def _spc_summary(ts_rows: list[SensorTimeseries], repeated_error_burst: bool) -> tuple[SQCSummary, dict[str, Optional[str]], list[float]]:
    coolant = [(_safe_float(r.coolant_temp) or 0.0) for r in ts_rows if _safe_float(r.coolant_temp) is not None]
    rpm = [(_safe_float(r.engine_rpm) or 0.0) for r in ts_rows if _safe_float(r.engine_rpm) is not None]
    throttle = [(_safe_float(r.throttle_pos) or 0.0) for r in ts_rows if _safe_float(r.throttle_pos) is not None]
    fuel_trim = [(_safe_float(r.fuel_trim) or 0.0) for r in ts_rows if _safe_float(r.fuel_trim) is not None]
    maf = [(_safe_float(r.maf) or 0.0) for r in ts_rows if _safe_float(r.maf) is not None]

    primary = coolant or rpm or throttle
    m = mean(primary) if primary else None
    sd = pstdev(primary) if len(primary) >= 2 else None
    mn = min(primary) if primary else None
    mx = max(primary) if primary else None
    trend = _trend_label(primary) if primary else "N/A"

    slope = _linear_slope(primary) if primary else 0.0
    abnormal_drift = abs(slope) > 0.08
    out_of_control = bool(sd is not None and m is not None and m != 0 and (sd / abs(m)) > 0.25)

    interpretation: list[str] = []
    if out_of_control:
        interpretation.append("통계적으로 변동 확대")
    if repeated_error_burst:
        interpretation.append("반복 오류 패턴 관찰")
    if abnormal_drift:
        interpretation.append("이상 드리프트 감지")
    if not interpretation:
        interpretation.append("즉시 이상 징후는 제한적이나 추적 관찰 권고")
    if out_of_control or repeated_error_burst or abnormal_drift:
        interpretation.append("즉시 공정 점검 권고")

    sqc = SQCSummary(
        monitored_features=[
            "coolant_temp",
            "engine_rpm",
            "throttle_pos",
            "fuel_trim",
            "maf",
            "error_log_frequency",
        ],
        statistical_summary=StatisticalSummary(
            mean=round(m, 4) if m is not None else None,
            std=round(sd, 4) if sd is not None else None,
            min=round(mn, 4) if mn is not None else None,
            max=round(mx, 4) if mx is not None else None,
            trend=trend,
        ),
        rule_based_flags=RuleBasedFlags(
            out_of_control=out_of_control,
            repeated_error_burst=repeated_error_burst,
            abnormal_drift=abnormal_drift,
        ),
        interpretation=interpretation,
    )

    timeseries_summary = {
        "temp_trend": _trend_label(coolant) if coolant else "N/A",
        "rpm_trend": _trend_label(rpm) if rpm else "N/A",
        "throttle_trend": _trend_label(throttle) if throttle else "N/A",
        "fuel_trim_trend": _trend_label(fuel_trim) if fuel_trim else "N/A",
        "maf_trend": _trend_label(maf) if maf else "N/A",
    }
    return sqc, timeseries_summary, coolant


def _severity_and_priority(pred: dict[str, Any], flags: RuleBasedFlags) -> tuple[str, str]:
    fp = float(pred.get("failure_probability", 0.0) or 0.0)
    anomaly = float(pred.get("anomaly_score", 0.0) or 0.0)
    rul = float(pred.get("predicted_rul_minutes", 0.0) or 0.0)

    high = fp >= 0.8 or anomaly >= 0.8 or (rul > 0 and rul <= 60) or flags.repeated_error_burst
    med = fp >= 0.5 or anomaly >= 0.6 or (rul > 0 and rul <= 180) or flags.out_of_control or flags.abnormal_drift

    if high:
        return "HIGH", "P1"
    if med:
        return "MEDIUM", "P2"
    return "LOW", "P3"


def _containment_recommendation(severity: str, pred: dict[str, Any]) -> tuple[str, str]:
    rul = float(pred.get("predicted_rul_minutes", 0.0) or 0.0)
    if severity == "HIGH":
        return (
            "STOP_AND_ESCALATE",
            "격리 구역으로 이동 후 원인부품 분리 검사 권고",
        )
    if severity == "MEDIUM":
        return (
            "CONTINUE_WITH_CAUTION",
            "해당 라인 배치 분리 보관 및 100% 재검사 권고",
        )
    if rul > 0 and rul < 240:
        return (
            "CONTINUE_WITH_MONITORING",
            "단기 모니터링 강화 및 동일 증상 재발 여부 확인 권고",
        )
    return (
        "CONTINUE",
        "정상 생산 유지 가능하나 표본 재검사 권고",
    )


def _reference_docs(error_logs: list[ErrorLog]) -> list[ReferenceDocument]:
    docs: list[ReferenceDocument] = []
    for i, row in enumerate(error_logs[:3], start=1):
        docs.append(
            ReferenceDocument(
                doc_id=f"ERRLOG-{i}",
                title=f"Error Log Reference {i}",
                section=_safe_str(row.ecu_module, "ECU Module"),
                snippet=_safe_str(row.raw_message or row.dtc_description, "N/A"),
            )
        )
    return docs


def build_quality_report(incident_id: int, db: Session) -> tuple[QualityIncidentReport, dict[str, Any]]:
    incident = db.query(Incident).filter(Incident.incident_id == incident_id).first()
    if not incident:
        raise ValueError("Incident not found")

    ts_rows, error_logs, assets, device = _collect_rows(db, incident)
    pred_raw, model_info = _get_prediction_snapshot(db, incident)
    error_pattern, repeated_error_burst = _error_log_pattern(error_logs)
    sqc_summary, timeseries_summary, coolant_values = _spc_summary(ts_rows, repeated_error_burst)

    analysis_lines, action_lines = _split_incident_description(incident.description or "")
    symptom_summary = analysis_lines[0] if analysis_lines else _safe_str(incident.description, "N/A")

    severity, priority = _severity_and_priority(pred_raw, sqc_summary.rule_based_flags)
    stop_or_continue, isolation_action = _containment_recommendation(severity, pred_raw)

    aec_stress: list[str] = []
    if coolant_values and max(coolant_values) >= 95:
        aec_stress.append("temperature")
    if sqc_summary.rule_based_flags.abnormal_drift:
        aec_stress.append("operating life")
    if sqc_summary.rule_based_flags.out_of_control:
        aec_stress.append("humidity")
    if not aec_stress:
        aec_stress = ["temperature", "ESD", "operating life"]

    header = ReportHeader(
        report_id=f"QIR-{incident.incident_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        incident_id=str(incident.incident_id),
        generated_at=datetime.utcnow(),
        device_id=_safe_str(incident.device_id),
        lot_id="N/A",
        process_step=_safe_str(getattr(incident, "line", None), "N/A"),
        station_id=_safe_str(getattr(incident, "site", None), "N/A"),
        product_type=_safe_str(getattr(device, "vehicle_type", None), "N/A"),
        severity=severity,
        status=_safe_str(incident.status, "N/A"),
    )

    incident_summary = IncidentSummary(
        issue_title=_safe_str(incident.title, "Quality incident"),
        user_intent=_safe_str(analysis_lines[0] if analysis_lines else "검토 필요", "검토 필요"),
        symptom_summary=_safe_str(symptom_summary, "N/A"),
        business_impact=(
            "라인 중단/재작업 위험 증가" if severity == "HIGH" else "품질 편차 확대 가능성" if severity == "MEDIUM" else "즉시 영향 제한적"
        ),
        recommended_priority=priority,
    )

    evidence_summary = EvidenceSummary(
        voice_transcript="N/A",
        objects_detected=[],
        observations=analysis_lines[:5] if analysis_lines else ["검토 필요"],
        error_log_pattern=_safe_str(error_pattern, "N/A"),
        timeseries_summary={k: (v if v else "N/A") for k, v in timeseries_summary.items()},
        predictive_ai=PredictiveAISummary(
            predicted_rul_minutes=round(float(pred_raw.get("predicted_rul_minutes", 0.0)), 2),
            failure_probability=round(float(pred_raw.get("failure_probability", 0.0)), 4),
            anomaly_score=round(float(pred_raw.get("anomaly_score", 0.0)), 4),
        ),
    )

    immediate = ImmediateContainmentAction(
        stop_or_continue_recommendation=stop_or_continue,
        isolation_action=isolation_action,
        reinspection_action="동일 장비/동일 로트 대상 기능 재검사 및 센서 교차검증 권고",
        escalation_condition="고장확률>=0.8 또는 RUL<=60분 또는 동일 DTC 10분 내 3회 이상 발생 시 즉시 에스컬레이션",
    )

    root_cause = RootCauseCorrectiveAction(
        problem_description=_safe_str(symptom_summary, "N/A"),
        suspected_root_cause=_safe_str(action_lines[0] if action_lines else "검토 필요", "검토 필요"),
        interim_containment_action=_safe_str(action_lines[1] if len(action_lines) > 1 else isolation_action, "검토 필요"),
        corrective_action=_safe_str(action_lines[2] if len(action_lines) > 2 else "부품/공정 조건 점검 및 이상 항목 교정 권고", "검토 필요"),
        preventive_action="SPC 모니터링 임계치 재정의, 작업표준서 점검, 재발방지 교육 권고",
        owner="Engineer review required",
        due_date="N/A",
        verification_method="재측정, 재검사, SPC 추세 추적 및 DTC 재발 여부 확인",
    )

    pdca = PDCAMapping(
        plan="이상 센서/오류 로그를 핵심 개선 대상으로 정의",
        do="격리, 재검사, 원인 의심 항목 우선 점검 권고",
        check="재측정 결과와 SPC 변동성, 오류 재발 빈도로 효과 확인",
        act="표준작업서/점검표 개정 및 교육 반영 여부 엔지니어 검토",
    )

    aec = AECQReference(
        applicable_component_type="module" if device and device.vehicle_type else "unknown",
        possible_related_stress_categories=aec_stress,
        aec_reference_note=(
            "현재 장애 패턴과 연관 가능성이 있는 AEC-Q 스트레스 카테고리를 참고용으로 제시합니다. "
            "본 보고서는 compliance/pass/fail 판정을 제공하지 않습니다."
        ),
        review_required=True,
    )

    references = _reference_docs(error_logs)

    footer = ReportFooter(
        disclaimer="This report is an AI-assisted draft for quality support. Final disposition requires engineer review.",
        version=REPORT_VERSION,
        model_info=model_info,
        data_sources=[
            "incidents",
            "incident_assets",
            "sensor_timeseries",
            "error_logs",
            "predictions/runtime_inference",
        ],
    )

    report = QualityIncidentReport(
        header=header,
        incident_summary=incident_summary,
        evidence_summary=evidence_summary,
        immediate_containment_action=immediate,
        root_cause_corrective_action=root_cause,
        iso9001_pdca_mapping=pdca,
        sqc_spc_summary=sqc_summary,
        aec_q_reference=aec,
        reference_documents=references,
        footer=footer,
    )

    context = {
        "incident": incident,
        "assets": assets,
        "ts_rows": ts_rows,
        "pred": pred_raw,
    }
    return report, context


class ReportPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_margins(8, 8, 8)
        self.set_auto_page_break(auto=True, margin=8)
        if os.path.exists(FONT_PATH):
            self.add_font("NanumGothic", "", FONT_PATH)
        if os.path.exists(FONT_BOLD_PATH):
            self.add_font("NanumGothic", "B", FONT_BOLD_PATH)

    def header(self):
        font = "NanumGothic" if os.path.exists(FONT_BOLD_PATH) else "Arial"
        self.set_font(font, "B", 14)
        self.cell(0, 9, normalize_text("Quality Incident & Corrective Action Report"), 0, 1, "C")
        self.ln(3)

    def footer(self):
        font = "NanumGothic" if os.path.exists(FONT_PATH) else "Arial"
        self.set_y(-14)
        self.set_font(font, "", 8)
        self.cell(0, 8, f"Page {self.page_no()}", 0, 0, "C")


def _pdf_metric(pdf: ReportPDF, label: str, value: float, max_value: float, color: tuple[int, int, int], unit: str = "") -> None:
    x = pdf.get_x()
    y = pdf.get_y()
    w = 100
    h = 5
    ratio = 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))

    pdf.set_font(pdf.font_family, "", 10)
    shown = f"{value:.4f}" if unit == "" else f"{value:.2f}{unit}"
    pdf.cell(75, 6, normalize_text(f"{label}: {shown}"), ln=0)

    pdf.set_fill_color(22, 101, 52)
    pdf.rect(x + 77, y, w * 0.5, h, style="F")
    pdf.set_fill_color(161, 98, 7)
    pdf.rect(x + 77 + w * 0.5, y, w * 0.25, h, style="F")
    pdf.set_fill_color(153, 27, 27)
    pdf.rect(x + 77 + w * 0.75, y, w * 0.25, h, style="F")
    pdf.set_draw_color(120, 130, 150)
    pdf.rect(x + 77, y, w, h)

    marker = x + 77 + w * ratio
    pdf.set_draw_color(*color)
    pdf.set_line_width(1.3)
    pdf.line(marker, y - 1.0, marker, y + h + 1.0)
    pdf.set_line_width(0.2)
    pdf.ln(8)


def _pdf_section_title(pdf: ReportPDF, text: str) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font(pdf.font_family, "B", 11)
    pdf.cell(pdf.w - pdf.l_margin - pdf.r_margin, 8, normalize_text(text), ln=1)


def _pdf_split_to_fit(pdf: ReportPDF, text: str, max_width: float) -> list[str]:
    raw = normalize_text(text).replace("\r", "")
    if not raw:
        return [""]

    lines: list[str] = []
    for paragraph in raw.split("\n"):
        if not paragraph:
            lines.append("")
            continue

        current = ""
        for ch in paragraph:
            trial = current + ch
            # guard against width-calc anomalies
            try:
                trial_w = pdf.get_string_width(trial)
            except Exception:
                trial_w = max_width + 1
            if trial_w <= max_width:
                current = trial
                continue
            if current:
                lines.append(current)
                current = ch
            else:
                # single-character overflow should be impossible with sane font sizes,
                # but keep progress by emitting one character per line.
                lines.append(ch)
                current = ""
        if current:
            lines.append(current)
    return lines or [""]


def _pdf_safe_write(pdf: ReportPDF, text: str, line_h: float = 6.0) -> None:
    writable_w = pdf.w - pdf.l_margin - pdf.r_margin
    # keep small right padding to avoid edge-overflow in fpdf width engine
    max_width = max(10.0, writable_w - 1.0)
    for line in _pdf_split_to_fit(pdf, text, max_width):
        pdf.set_x(pdf.l_margin)
        pdf.cell(writable_w, line_h, line, ln=1)


def _render_pdf(report: QualityIncidentReport, context: dict[str, Any], out_path: str) -> None:
    pdf = ReportPDF()
    pdf.add_page()
    base_font = "NanumGothic" if os.path.exists(FONT_PATH) else "Arial"
    pdf.set_font(base_font, "", 10)

    _pdf_section_title(pdf, "A. Report Header")
    for k, v in report.header.model_dump().items():
        _pdf_safe_write(pdf, f"{k}: {v}")
    pdf.ln(2)

    _pdf_section_title(pdf, "B. Incident Summary")
    for k, v in report.incident_summary.model_dump().items():
        _pdf_safe_write(pdf, f"{k}: {v}")
    pdf.ln(2)

    _pdf_section_title(pdf, "C. Evidence Summary")
    ev = report.evidence_summary
    _pdf_safe_write(pdf, f"voice_transcript: {ev.voice_transcript}")
    _pdf_safe_write(pdf, f"observations: {', '.join(ev.observations) if ev.observations else 'N/A'}")
    _pdf_safe_write(pdf, f"error_log_pattern: {ev.error_log_pattern}")
    _pdf_safe_write(pdf, f"timeseries_summary: {json.dumps(ev.timeseries_summary, ensure_ascii=False)}")

    pred = ev.predictive_ai
    _pdf_metric(pdf, "failure_probability", float(pred.failure_probability or 0.0), 1.0, (239, 68, 68))
    _pdf_metric(pdf, "anomaly_score", float(pred.anomaly_score or 0.0), 1.0, (245, 158, 11))
    _pdf_metric(pdf, "predicted_rul_minutes", float(pred.predicted_rul_minutes or 0.0), 1440.0, (16, 185, 129), " min")

    _pdf_section_title(pdf, "D. Immediate Containment Action")
    for k, v in report.immediate_containment_action.model_dump().items():
        _pdf_safe_write(pdf, f"{k}: {v}")
    pdf.ln(1)

    _pdf_section_title(pdf, "E. Root Cause / Corrective Action (8D/CAPA summary)")
    for k, v in report.root_cause_corrective_action.model_dump().items():
        _pdf_safe_write(pdf, f"{k}: {v}")
    pdf.ln(1)

    _pdf_section_title(pdf, "F. ISO 9001 PDCA Mapping")
    for k, v in report.iso9001_pdca_mapping.model_dump().items():
        _pdf_safe_write(pdf, f"{k}: {v}")
    pdf.ln(1)

    _pdf_section_title(pdf, "G. SQC / SPC Summary")
    _pdf_safe_write(pdf, f"monitored_features: {', '.join(report.sqc_spc_summary.monitored_features)}")
    _pdf_safe_write(pdf, f"statistical_summary: {report.sqc_spc_summary.statistical_summary.model_dump()}")
    _pdf_safe_write(pdf, f"rule_based_flags: {report.sqc_spc_summary.rule_based_flags.model_dump()}")
    _pdf_safe_write(pdf, f"interpretation: {'; '.join(report.sqc_spc_summary.interpretation)}")

    _pdf_section_title(pdf, "H. AEC-Q Reference Section")
    for k, v in report.aec_q_reference.model_dump().items():
        _pdf_safe_write(pdf, f"{k}: {v}")

    _pdf_section_title(pdf, "I. Reference Documents")
    if report.reference_documents:
        for doc in report.reference_documents:
            _pdf_safe_write(pdf, f"{doc.doc_id} | {doc.title} | {doc.section} | {doc.snippet}")
    else:
        _pdf_safe_write(pdf, "N/A")

    _pdf_section_title(pdf, "J. Footer / Disclaimer")
    for k, v in report.footer.model_dump().items():
        _pdf_safe_write(pdf, f"{k}: {v}")

    pdf.output(out_path)


def _render_html(report: QualityIncidentReport, out_path: str) -> None:
    def esc(v: Any) -> str:
        return html.escape(normalize_text(v))

    def kv_rows(data: dict[str, Any]) -> str:
        rows = []
        for k, v in data.items():
            if isinstance(v, dict):
                v = json.dumps(v, ensure_ascii=False)
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v) if v else "N/A"
            rows.append(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>")
        return "".join(rows)

    html_doc = f"""
<!doctype html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>Quality Incident & Corrective Action Report</title>
  <style>
    @page {{ size: A4; margin: 10mm 8mm; }}
    body {{ font-family: Arial, sans-serif; background:#ffffff; color:#111827; margin:0; padding:0; }}
    .wrap {{ width:100%; margin:0; background:#fff; border:1px solid #d1d5db; padding:8px; box-sizing:border-box; }}
    h1 {{ margin:0 0 6px 0; font-size:20px; }}
    h2 {{ margin:12px 0 6px 0; font-size:15px; border-bottom:1px solid #e5e7eb; padding-bottom:3px; }}
    table {{ width:100%; border-collapse: collapse; font-size:13px; }}
    th, td {{ border:1px solid #e5e7eb; padding:6px; vertical-align:top; }}
    th {{ width:220px; background:#f9fafb; text-align:left; }}
    .muted {{ color:#6b7280; font-size:12px; }}
    .chips span {{ display:inline-block; padding:3px 8px; border:1px solid #cbd5e1; border-radius:999px; margin-right:6px; margin-bottom:6px; font-size:12px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-top:6px; }}
    .card {{ border:1px solid #d1d5db; padding:8px; }}
    .bar {{ background:#e5e7eb; height:8px; border-radius:999px; overflow:hidden; margin-top:6px; }}
    .fill {{ height:8px; }}
    .footer {{ margin-top:10px; font-size:11px; color:#374151; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>{esc(report.report_title)}</h1>
    <div class=\"muted\">AI-assisted quality support draft. Engineer review required.</div>

    <h2>A. Report Header</h2>
    <table>{kv_rows(report.header.model_dump())}</table>

    <h2>B. Incident Summary</h2>
    <table>{kv_rows(report.incident_summary.model_dump())}</table>

    <h2>C. Evidence Summary</h2>
    <table>{kv_rows(report.evidence_summary.model_dump())}</table>
    <div class=\"grid\">
      <div class=\"card\"><strong>Failure Probability</strong><br/>{esc(report.evidence_summary.predictive_ai.failure_probability)}<div class=\"bar\"><div class=\"fill\" style=\"width:{max(0,min(100,(report.evidence_summary.predictive_ai.failure_probability or 0)*100)):.1f}%;background:#ef4444\"></div></div></div>
      <div class=\"card\"><strong>Anomaly Score</strong><br/>{esc(report.evidence_summary.predictive_ai.anomaly_score)}<div class=\"bar\"><div class=\"fill\" style=\"width:{max(0,min(100,(report.evidence_summary.predictive_ai.anomaly_score or 0)*100)):.1f}%;background:#f59e0b\"></div></div></div>
      <div class=\"card\"><strong>Predicted RUL (min)</strong><br/>{esc(report.evidence_summary.predictive_ai.predicted_rul_minutes)}<div class=\"bar\"><div class=\"fill\" style=\"width:{max(0,min(100,((report.evidence_summary.predictive_ai.predicted_rul_minutes or 0)/1440.0)*100)):.1f}%;background:#10b981\"></div></div></div>
    </div>

    <h2>D. Immediate Containment Action</h2>
    <table>{kv_rows(report.immediate_containment_action.model_dump())}</table>

    <h2>E. Root Cause / Corrective Action (8D/CAPA style summary)</h2>
    <table>{kv_rows(report.root_cause_corrective_action.model_dump())}</table>

    <h2>F. ISO 9001 PDCA Mapping</h2>
    <table>{kv_rows(report.iso9001_pdca_mapping.model_dump())}</table>

    <h2>G. SQC / SPC Summary</h2>
    <table>{kv_rows(report.sqc_spc_summary.model_dump())}</table>

    <h2>H. AEC-Q Reference Section</h2>
    <table>{kv_rows(report.aec_q_reference.model_dump())}</table>

    <h2>I. Reference Documents</h2>
    <table>
      <tr><th>doc_id</th><th>title</th><th>section</th><th>snippet</th></tr>
      {''.join(f'<tr><td>{esc(d.doc_id)}</td><td>{esc(d.title)}</td><td>{esc(d.section)}</td><td>{esc(d.snippet)}</td></tr>' for d in report.reference_documents) or '<tr><td colspan="4">N/A</td></tr>'}
    </table>

    <h2>J. Footer / Disclaimer</h2>
    <table>{kv_rows(report.footer.model_dump())}</table>
    <div class=\"footer\">This report is generated for quality support demo workflow and requires engineer final disposition.</div>
  </div>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)


def _render_pdf_from_html(html_path: str, pdf_path: str) -> None:
    if not WEASYPRINT_AVAILABLE or HTML is None:
        raise RuntimeError(
            "WeasyPrint is not available. Install dependency 'weasyprint' in ai-server environment."
        )
    HTML(filename=html_path, base_url=os.path.dirname(html_path)).write_pdf(pdf_path)


def _render_pdf_fallback(report: QualityIncidentReport, out_path: str) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 8, "Quality Incident & Corrective Action Report (Fallback)", ln=1)
    pdf.set_font("Arial", "", 10)
    lines = [
        f"report_id: {report.header.report_id}",
        f"incident_id: {report.header.incident_id}",
        f"generated_at: {report.header.generated_at.isoformat()}",
        f"device_id: {report.header.device_id}",
        f"severity: {report.header.severity}",
        f"status: {report.header.status}",
        f"issue_title: {report.incident_summary.issue_title}",
        f"recommended_priority: {report.incident_summary.recommended_priority}",
        "This fallback PDF was generated due to rich rendering failure.",
    ]
    for line in lines:
        ascii_line = normalize_text(line).encode("ascii", "ignore").decode("ascii")
        if not ascii_line.strip():
            continue
        # Hard wrap to avoid rare width-calculation failures on long tokens.
        for i in range(0, len(ascii_line), 110):
            segment = ascii_line[i : i + 110]
            if not segment:
                continue
            pdf.cell(190, 6, segment, ln=1)
    pdf.output(out_path)


def _render_html_fallback(report: QualityIncidentReport, out_path: str, error_message: str) -> None:
    safe_error = html.escape(normalize_text(error_message))
    safe_json = html.escape(report.model_dump_json(indent=2))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(
            "<!doctype html><html><head><meta charset='utf-8'><title>Quality Report Fallback</title></head>"
            "<body style='font-family:Arial;padding:20px'>"
            "<h1>Quality Incident & Corrective Action Report (Fallback)</h1>"
            f"<p>Rich report rendering failed: {safe_error}</p>"
            "<pre style='white-space:pre-wrap;border:1px solid #ccc;padding:12px;background:#f8fafc'>"
            f"{safe_json}</pre></body></html>"
        )


def generate_quality_report_bundle(incident_id: int, db: Session) -> tuple[QualityIncidentReport, str, str]:
    report, _context = build_quality_report(incident_id, db)
    os.makedirs(settings.REPORT_OUTPUT_DIR, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    pdf_name = f"quality_incident_report_{incident_id}_{ts}.pdf"
    html_name = f"quality_incident_report_{incident_id}_{ts}.html"

    pdf_path = os.path.join(settings.REPORT_OUTPUT_DIR, pdf_name)
    html_path = os.path.join(settings.REPORT_OUTPUT_DIR, html_name)

    try:
        _render_html(report, html_path)
    except Exception as e:
        raise RuntimeError(f"HTML report rendering failed: {str(e)}")

    try:
        _render_pdf_from_html(html_path, pdf_path)
    except Exception as e:
        # On environments without native WeasyPrint libs, keep deterministic PDF output.
        try:
            _render_pdf(report, _context, pdf_path)
        except Exception as inner:
            raise RuntimeError(f"PDF conversion failed (HTML->PDF): {str(e)} / ReportLab fallback failed: {str(inner)}")

    return report, pdf_path, html_path


def generate_fallback_report_bundle(incident_id: int, reason: str = "unknown") -> tuple[QualityIncidentReport, str, str]:
    report = sample_quality_report()
    now = datetime.utcnow()
    report = report.model_copy(
        update={
            "header": report.header.model_copy(
                update={
                    "report_id": f"QIR-FALLBACK-{incident_id}-{now.strftime('%Y%m%d%H%M%S')}",
                    "incident_id": str(incident_id),
                    "generated_at": now,
                    "status": "FALLBACK",
                }
            ),
            "incident_summary": report.incident_summary.model_copy(
                update={
                    "issue_title": f"Fallback report generated (incident_id={incident_id})",
                    "symptom_summary": f"원본 보고서 생성 실패로 fallback 보고서를 반환합니다. reason={reason}",
                }
            ),
        }
    )

    os.makedirs(settings.REPORT_OUTPUT_DIR, exist_ok=True)
    ts = now.strftime("%Y%m%d%H%M%S")
    pdf_name = f"quality_incident_report_fallback_{incident_id}_{ts}.pdf"
    html_name = f"quality_incident_report_fallback_{incident_id}_{ts}.html"
    pdf_path = os.path.join(settings.REPORT_OUTPUT_DIR, pdf_name)
    html_path = os.path.join(settings.REPORT_OUTPUT_DIR, html_name)
    try:
        _render_pdf_fallback(report, pdf_path)
    except Exception:
        # HTML fallback is the primary guaranteed artifact.
        pass
    _render_html_fallback(report, html_path, reason)
    return report, pdf_path, html_path


def generate_pdf_report(incident_id: int, db: Session) -> str:
    _, pdf_path, _ = generate_quality_report_bundle(incident_id, db)
    return pdf_path


def sample_quality_report() -> QualityIncidentReport:
    now = datetime.utcnow()
    return QualityIncidentReport(
        header=ReportHeader(
            report_id="QIR-SAMPLE-20260309-0001",
            incident_id="12345",
            generated_at=now,
            device_id="DEV-MAF-01",
            lot_id="N/A",
            process_step="Engine Inspection",
            station_id="Line-A/Station-03",
            product_type="module",
            severity="MEDIUM",
            status="COMPLETED",
        ),
        incident_summary=IncidentSummary(
            issue_title="엔진 진동 증가 및 출력 저하 경고",
            user_intent="원인 후보와 즉시 조치 확인",
            symptom_summary="냉각수 온도 상승과 반복 DTC 패턴 동반",
            business_impact="품질 편차 확대 가능성",
            recommended_priority="P2",
        ),
        evidence_summary=EvidenceSummary(
            voice_transcript="N/A",
            objects_detected=[],
            observations=["작업 중 경고등 점등", "반복 오류 코드 관찰"],
            error_log_pattern="P0302 x3, P0117 x2",
            timeseries_summary={"temp_trend": "rising", "rpm_trend": "unstable", "throttle_trend": "stable"},
            predictive_ai=PredictiveAISummary(
                predicted_rul_minutes=118.5,
                failure_probability=0.63,
                anomaly_score=0.78,
            ),
        ),
        immediate_containment_action=ImmediateContainmentAction(
            stop_or_continue_recommendation="CONTINUE_WITH_CAUTION",
            isolation_action="해당 배치 분리 후 재검사 권고",
            reinspection_action="동일 로트 대상 센서 및 ECU 로그 재검사",
            escalation_condition="고장확률>=0.8 또는 RUL<=60분이면 즉시 에스컬레이션",
        ),
        root_cause_corrective_action=RootCauseCorrectiveAction(
            problem_description="센서 변동성과 오류코드가 동반된 이상 상태",
            suspected_root_cause="냉각계통 성능 저하 또는 연결부 접촉 불량 의심",
            interim_containment_action="격리 및 기능 재검사",
            corrective_action="냉각계통 점검 및 커넥터 체결상태 교정",
            preventive_action="SPC 임계치 재설정 및 표준점검 주기 보강",
            owner="Engineer review required",
            due_date="N/A",
            verification_method="재측정 및 오류 재발여부 확인",
        ),
        iso9001_pdca_mapping=PDCAMapping(
            plan="핵심 이상 항목 정의",
            do="격리/재검사/점검 수행 권고",
            check="SPC 및 재검사 결과로 효과 확인",
            act="표준화/교육/문서개정 검토",
        ),
        sqc_spc_summary=SQCSummary(
            monitored_features=["coolant_temp", "engine_rpm", "error_log_frequency"],
            statistical_summary=StatisticalSummary(mean=86.2, std=4.1, min=79.5, max=94.6, trend="rising"),
            rule_based_flags=RuleBasedFlags(out_of_control=False, repeated_error_burst=True, abnormal_drift=True),
            interpretation=["반복 오류 패턴 관찰", "이상 드리프트 감지", "즉시 공정 점검 권고"],
        ),
        aec_q_reference=AECQReference(
            applicable_component_type="module",
            possible_related_stress_categories=["temperature", "operating life", "ESD"],
            aec_reference_note="장애 패턴과 연관 가능성이 있는 AEC-Q 시험 카테고리를 참고용으로 제시하며 pass/fail 판정은 제공하지 않습니다.",
            review_required=True,
        ),
        reference_documents=[
            ReferenceDocument(doc_id="ERRLOG-1", title="Error Log Reference 1", section="ECU", snippet="P0302 반복 발생"),
        ],
        footer=ReportFooter(
            disclaimer="This report is an AI-assisted draft for quality support. Final disposition requires engineer review.",
            version=REPORT_VERSION,
            model_info="runtime.inference/demo",
            data_sources=["incidents", "sensor_timeseries", "error_logs"],
        ),
    )
