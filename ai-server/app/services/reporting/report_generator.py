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
    return str(text).replace("**", "").replace("__", "")

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


def _draw_bar_metric(
    pdf: ReportPDF,
    base_font: str,
    label: str,
    value: float,
    max_value: float,
    unit: str,
    color_rgb: tuple[int, int, int],
) -> None:
    bar_x = pdf.get_x()
    bar_y = pdf.get_y()
    bar_w = 120
    bar_h = 6

    pdf.set_font(base_font, '', 10)
    shown = round(value, 4) if unit == "" else round(value, 2)
    pdf.cell(70, 6, txt=normalize_text(f"{label}: {shown}{unit}"), ln=0)

    pdf.set_fill_color(40, 48, 64)
    pdf.rect(bar_x + 72, bar_y, bar_w, bar_h, style='F')

    ratio = 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))
    fill_w = bar_w * ratio
    pdf.set_fill_color(*color_rgb)
    pdf.rect(bar_x + 72, bar_y, fill_w, bar_h, style='F')
    pdf.ln(8)


def _draw_timeseries_sparkline(pdf: ReportPDF, rows: list[SensorTimeseries]) -> None:
    if not rows:
        pdf.set_font('Arial', '', 9)
        pdf.cell(0, 6, txt=normalize_text("시계열 샘플이 없어 트렌드 그래프를 생략합니다."), ln=1)
        return

    # 최근 60개 샘플만 사용
    samples = rows[-60:]
    values = [_safe_float(r.coolant_temp, 0.0) for r in samples]
    if not values:
        return

    min_v = min(values)
    max_v = max(values)
    span = max(max_v - min_v, 1e-6)

    x0 = pdf.get_x()
    y0 = pdf.get_y()
    w = 180
    h = 28

    pdf.set_draw_color(80, 92, 120)
    pdf.rect(x0, y0, w, h)

    pdf.set_draw_color(37, 99, 235)
    n = len(values)
    for i in range(n - 1):
        x1 = x0 + (w * i / max(1, n - 1))
        x2 = x0 + (w * (i + 1) / max(1, n - 1))
        y1 = y0 + h - (h * (values[i] - min_v) / span)
        y2 = y0 + h - (h * (values[i + 1] - min_v) / span)
        pdf.line(x1, y1, x2, y2)

    pdf.ln(h + 2)
    pdf.set_font('Arial', '', 8)
    pdf.cell(0, 5, txt=normalize_text(f"Coolant Temp Trend (min={min_v:.2f}, max={max_v:.2f})"), ln=1)

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
        .order_by(SensorTimeseries.timestamp.asc())
        .limit(120)
        .all()
    )

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
    
    desc = str(incident.description) if incident.description else "상세 설명이 없습니다."
    desc = strip_markdown_asterisks(desc)
    
    # UTF-8 출력 지원
    pdf.multi_cell(0, 8, txt=normalize_text(desc))
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

    _draw_bar_metric(
        pdf,
        base_font=base_font,
        label="Failure Probability",
        value=_safe_float(prediction["failure_probability"], 0.0),
        max_value=1.0,
        unit="",
        color_rgb=(239, 68, 68),
    )
    _draw_bar_metric(
        pdf,
        base_font=base_font,
        label="Anomaly Score",
        value=_safe_float(prediction["anomaly_score"], 0.0),
        max_value=1.0,
        unit="",
        color_rgb=(245, 158, 11),
    )
    _draw_bar_metric(
        pdf,
        base_font=base_font,
        label="Predicted RUL",
        value=_safe_float(prediction["predicted_rul_minutes"], 0.0),
        max_value=1440.0,
        unit=" min",
        color_rgb=(16, 185, 129),
    )

    pdf.set_font(base_font, '', 9)
    pdf.cell(200, 6, txt=normalize_text("5. 최근 시계열 트렌드 (Coolant Temperature)"), ln=1)
    _draw_timeseries_sparkline(pdf, ts_rows)

    # Save PDF
    os.makedirs(settings.REPORT_OUTPUT_DIR, exist_ok=True)
    file_name = f"incident_report_{incident_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    file_path = os.path.join(settings.REPORT_OUTPUT_DIR, file_name)
    
    pdf.output(file_path)
    
    return file_path
