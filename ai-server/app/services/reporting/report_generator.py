import os
import unicodedata
from datetime import datetime
from fpdf import FPDF
from sqlalchemy.orm import Session
from app.models.domain import Incident, IncidentAsset
from app.core.config import settings

# 현재 파일이 있는 디렉토리 경로
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(CURRENT_DIR, "NanumGothic.ttf")
FONT_BOLD_PATH = os.path.join(CURRENT_DIR, "NanumGothicBold.ttf")

def normalize_text(text: str) -> str:
    """macOS의 NFD(자소 분리) 한글을 Windows/Linux에서 쓰는 NFC(자소 결합) 형태로 변환"""
    if not text:
        return ""
    return unicodedata.normalize("NFC", str(text))

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

def generate_pdf_report(incident_id: int, db: Session) -> str:
    """
    Generates a PDF report for a given incident.
    """
    incident = db.query(Incident).filter(Incident.incident_id == incident_id).first()
    if not incident:
        raise ValueError("Incident not found")

    assets = db.query(IncidentAsset).filter(IncidentAsset.incident_id == incident_id).all()

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

    # Save PDF
    os.makedirs(settings.REPORT_OUTPUT_DIR, exist_ok=True)
    file_name = f"incident_report_{incident_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    file_path = os.path.join(settings.REPORT_OUTPUT_DIR, file_name)
    
    pdf.output(file_path)
    
    return file_path
