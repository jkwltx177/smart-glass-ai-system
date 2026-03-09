import os
import unicodedata
from datetime import datetime
from fpdf import FPDF
from sqlalchemy.orm import Session
from app.models.domain import Incident, IncidentAsset, Prediction, SensorTimeseries
from app.core.config import settings
from app.services.prediction import build_timeseries_features_payload, predict_from_timeseries_summary

# 현재 파일이 있는 디렉토리 경로
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(CURRENT_DIR, "NanumGothic.ttf")
FONT_BOLD_PATH = os.path.join(CURRENT_DIR, "NanumGothicBold.ttf")

def normalize_text(text: str) -> str:
    """macOS의 NFD(자소 분리) 한글을 Windows/Linux에서 쓰는 NFC(자소 결합) 형태로 변환"""
    if not text:
        return ""
    return unicodedata.normalize("NFC", str(text))


def strip_markdown_asterisks(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("**", "").replace("__", "").replace("* ", "").replace(" *", " ")


def _normalize_line(text: str) -> str:
    if not text:
        return ""
    s = strip_markdown_asterisks(text).strip()
    for token in ["- ", "• ", "* ", "> "]:
        if s.startswith(token):
            s = s[len(token):].strip()
    return s


def _extract_description_sections(raw_desc: str) -> tuple[list[str], list[str]]:
    placeholder = "상세 조치 내용은 아래 분석 결과를 확인하세요."
    analysis_lines: list[str] = []
    action_lines: list[str] = []
    seen = set()
    mode = "analysis"

    for raw in str(raw_desc or "").splitlines():
        line = _normalize_line(raw)
        if not line:
            continue
        key = line.replace(" ", "").lower()
        if key in {"[분석결과]", "분석결과"}:
            mode = "analysis"
            continue
        if key in {"[조치절차]", "조치절차", "action", "actionplan", "description&actionplan"}:
            mode = "action"
            continue
        if line == placeholder:
            continue
        if line in seen:
            continue
        seen.add(line)
        if mode == "action":
            action_lines.append(line)
        else:
            analysis_lines.append(line)

    if not analysis_lines and action_lines:
        analysis_lines = action_lines[:]
    return analysis_lines, action_lines

class ReportPDF(FPDF):
    def __init__(self):
        super().__init__()
        # 폰트를 인스턴스 생성 시 한 번만 등록
        if os.path.exists(FONT_PATH):
            self.add_font('NanumGothic', '', FONT_PATH)
        if os.path.exists(FONT_BOLD_PATH):
            self.add_font('NanumGothic', 'B', FONT_BOLD_PATH)

    def header(self):
        if os.path.exists(FONT_BOLD_PATH):
            self.set_font('NanumGothic', 'B', 15)
        else:
            self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Smart Factory Quality Remote Assist Report', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        if os.path.exists(FONT_PATH):
            self.set_font('NanumGothic', '', 8)
        else:
            self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_prediction_snapshot(db: Session, incident: Incident) -> dict:
    latest = (
        db.query(Prediction)
        .filter(Prediction.incident_id == incident.incident_id)
        .order_by(Prediction.predicted_at.desc())
        .first()
    )
    if latest:
        return {
            "source": "db.predictions",
            "failure_probability": _safe_float(latest.failure_probability, 0.0),
            "predicted_rul_minutes": _safe_float(latest.predicted_rul_minutes, 0.0),
            "anomaly_score": _safe_float(latest.anomaly_score, 0.0),
            "model": latest.model_name or "unknown",
            "model_version": latest.model_version or "unknown",
        }

    # Fallback: 시계열 기반 즉시 추론
    telemetry = build_timeseries_features_payload(
        db=db,
        device_id=str(incident.device_id),
        limit_rows=720,
        window_size=120,
        stride=30,
    )
    pred = predict_from_timeseries_summary(telemetry)
    return {
        "source": "runtime.inference",
        "failure_probability": _safe_float(pred.failure_probability, 0.0),
        "predicted_rul_minutes": _safe_float(pred.predicted_rul_minutes, 0.0),
        "anomaly_score": _safe_float(pred.anomaly_score, 0.0),
        "model": ",".join(pred.model_versions),
        "model_version": pred.model_source,
    }


def _draw_metric_band(
    pdf: ReportPDF,
    base_font: str,
    label: str,
    value: float,
    max_value: float,
    unit: str,
    color_rgb: tuple[int, int, int],
) -> None:
    band_x = pdf.get_x()
    band_y = pdf.get_y()
    band_w = 122
    band_h = 7
    ratio = 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))
    marker_x = band_x + 74 + (band_w * ratio)

    pdf.set_font(base_font, '', 10)
    shown = round(value, 4) if unit == "" else round(value, 2)
    pdf.cell(72, 6, txt=normalize_text(f"{label}: {shown}{unit}"), ln=0)

    # risk zones: green / amber / red
    pdf.set_fill_color(22, 101, 52)
    pdf.rect(band_x + 74, band_y, band_w * 0.5, band_h, style='F')
    pdf.set_fill_color(161, 98, 7)
    pdf.rect(band_x + 74 + band_w * 0.5, band_y, band_w * 0.25, band_h, style='F')
    pdf.set_fill_color(153, 27, 27)
    pdf.rect(band_x + 74 + band_w * 0.75, band_y, band_w * 0.25, band_h, style='F')

    pdf.set_draw_color(148, 163, 184)
    pdf.rect(band_x + 74, band_y, band_w, band_h)

    # measured value marker
    pdf.set_draw_color(*color_rgb)
    pdf.set_line_width(1.4)
    pdf.line(marker_x, band_y - 1.2, marker_x, band_y + band_h + 1.2)
    pdf.set_line_width(0.2)
    pdf.ln(8)


def _draw_timeseries_panel(pdf: ReportPDF, rows: list[SensorTimeseries], base_font: str) -> None:
    if not rows:
        pdf.set_font(base_font, '', 9)
        pdf.cell(0, 6, txt=normalize_text("시계열 샘플이 없어 트렌드 그래프를 생략합니다."), ln=1)
        return

    samples = rows[-90:]
    coolant = [_safe_float(r.coolant_temp, 0.0) for r in samples]
    rpm = [_safe_float(r.engine_rpm, 0.0) for r in samples]
    throttle = [_safe_float(r.throttle_pos, 0.0) for r in samples]
    if not coolant:
        return

    def normalize(vals: list[float]) -> list[float]:
        vmin, vmax = min(vals), max(vals)
        span = max(vmax - vmin, 1e-6)
        return [(v - vmin) / span for v in vals]

    coolant_n = normalize(coolant)
    rpm_n = normalize(rpm) if any(v > 0 for v in rpm) else [0.0 for _ in rpm]
    throttle_n = normalize(throttle) if any(v > 0 for v in throttle) else [0.0 for _ in throttle]

    x0 = pdf.get_x()
    y0 = pdf.get_y()
    w = 180
    h = 42

    # grid
    pdf.set_draw_color(71, 85, 105)
    pdf.rect(x0, y0, w, h)
    for i in range(1, 4):
        gy = y0 + (h * i / 4)
        pdf.line(x0, gy, x0 + w, gy)

    def draw_series(values: list[float], color: tuple[int, int, int]) -> None:
        pdf.set_draw_color(*color)
        n = len(values)
        for i in range(n - 1):
            x1 = x0 + (w * i / max(1, n - 1))
            x2 = x0 + (w * (i + 1) / max(1, n - 1))
            y1 = y0 + h - (h * values[i])
            y2 = y0 + h - (h * values[i + 1])
            pdf.line(x1, y1, x2, y2)

    draw_series(coolant_n, (37, 99, 235))
    draw_series(rpm_n, (16, 185, 129))
    draw_series(throttle_n, (245, 158, 11))

    pdf.ln(h + 2)
    pdf.set_font(base_font, '', 8)
    pdf.cell(
        0,
        5,
        txt=normalize_text(
            f"Legend: Coolant Temp[{min(coolant):.1f}-{max(coolant):.1f}], "
            f"RPM[{min(rpm):.0f}-{max(rpm):.0f}], "
            f"Throttle[{min(throttle):.1f}-{max(throttle):.1f}]"
        ),
        ln=1,
    )

def generate_pdf_report(incident_id: int, db: Session) -> str:
    """
    Generates a PDF report for a given incident.
    """
    incident = db.query(Incident).filter(Incident.incident_id == incident_id).first()
    if not incident:
        raise ValueError("Incident not found")

    assets = db.query(IncidentAsset).filter(IncidentAsset.incident_id == incident_id).all()
    prediction = _get_prediction_snapshot(db, incident)
    ts_rows = (
        db.query(SensorTimeseries)
        .filter(SensorTimeseries.device_id == incident.device_id)
        .order_by(SensorTimeseries.timestamp.desc())
        .limit(240)
        .all()
    )
    ts_rows.reverse()

    pdf = ReportPDF()
    pdf.add_page()
    
    base_font = 'NanumGothic' if os.path.exists(FONT_PATH) else 'Arial'

    pdf.set_font(base_font, size=12)

    # Basic Info
    pdf.set_font(base_font, 'B', 12)
    pdf.cell(200, 10, txt="1. 사건 기본 정보 (Incident Information)", ln=1)
    pdf.set_font(base_font, '', 10)
    pdf.cell(200, 8, txt=normalize_text(f"사건 번호 (ID): {incident.incident_id}"), ln=1)
    pdf.cell(200, 8, txt=normalize_text(f"장비 식별자 (Device ID): {incident.device_id}"), ln=1)
    pdf.cell(200, 8, txt=normalize_text(f"발생 위치: {incident.site} | 라인: {incident.line}"), ln=1)
    pdf.cell(200, 8, txt=normalize_text(f"생성 일시: {incident.created_at}"), ln=1)
    pdf.cell(200, 8, txt=normalize_text(f"상태: {incident.status} | 심각도: {incident.severity}"), ln=1)
    pdf.ln(5)

    # Details
    pdf.set_font(base_font, 'B', 12)
    pdf.cell(200, 10, txt="2. 상세 설명 및 조치 내용 (Description & Action Plan)", ln=1)
    pdf.set_font(base_font, '', 10)
    
    desc = str(incident.description) if incident.description else ""
    analysis_lines, action_lines = _extract_description_sections(desc)
    if analysis_lines:
        pdf.multi_cell(0, 8, txt=normalize_text("\n".join(analysis_lines)))
    else:
        pdf.multi_cell(0, 8, txt=normalize_text("상세 설명이 없습니다."))
    if action_lines:
        pdf.ln(2)
        pdf.set_font(base_font, 'B', 11)
        pdf.cell(200, 8, txt=normalize_text("조치 절차"), ln=1)
        pdf.set_font(base_font, '', 10)
        for idx, step in enumerate(action_lines, start=1):
            pdf.cell(0, 7, txt=normalize_text(f"{idx}. {step}"), ln=1)
    pdf.ln(5)

    # Assets Summary
    pdf.set_font(base_font, 'B', 12)
    pdf.cell(200, 10, txt="3. 첨부 파일 및 증적 자료 (Attached Assets)", ln=1)
    pdf.set_font(base_font, '', 10)
    if assets:
        for asset in assets:
            pdf.cell(200, 8, txt=normalize_text(f"- [{asset.asset_type}] {asset.file_name} ({asset.file_size} bytes)"), ln=1)
    else:
        pdf.cell(200, 8, txt=normalize_text("첨부된 파일이 없습니다."), ln=1)

    # Predictive AI summary + graph
    pdf.ln(4)
    pdf.set_font(base_font, 'B', 12)
    pdf.cell(200, 10, txt="4. 예측형 AI 결과 (Predictive AI Summary)", ln=1)
    pdf.set_font(base_font, '', 10)
    pdf.cell(
        200,
        6,
        txt=normalize_text(
            f"Source: {prediction['source']} | Model: {prediction['model']} ({prediction['model_version']})"
        ),
        ln=1,
    )

    _draw_metric_band(
        pdf,
        base_font=base_font,
        label="Failure Probability",
        value=_safe_float(prediction["failure_probability"], 0.0),
        max_value=1.0,
        unit="",
        color_rgb=(239, 68, 68),
    )
    _draw_metric_band(
        pdf,
        base_font=base_font,
        label="Anomaly Score",
        value=_safe_float(prediction["anomaly_score"], 0.0),
        max_value=1.0,
        unit="",
        color_rgb=(245, 158, 11),
    )
    _draw_metric_band(
        pdf,
        base_font=base_font,
        label="Predicted RUL",
        value=_safe_float(prediction["predicted_rul_minutes"], 0.0),
        max_value=1440.0,
        unit=" min",
        color_rgb=(16, 185, 129),
    )

    pdf.set_font(base_font, '', 9)
    pdf.cell(200, 6, txt=normalize_text("5. 최근 시계열 트렌드 (Multi-Sensor Trend)"), ln=1)
    _draw_timeseries_panel(pdf, ts_rows, base_font)

    # Save PDF
    os.makedirs(settings.REPORT_OUTPUT_DIR, exist_ok=True)
    file_name = f"incident_report_{incident_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    file_path = os.path.join(settings.REPORT_OUTPUT_DIR, file_name)
    
    pdf.output(file_path)
    
    return file_path
