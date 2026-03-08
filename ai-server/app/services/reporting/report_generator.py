import os
from datetime import datetime
from fpdf import FPDF
from sqlalchemy.orm import Session
from app.models.domain import Incident, IncidentAsset
from app.core.config import settings

class ReportPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Smart Factory Quality Remote Assist Report', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
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
    pdf.set_font("Arial", size=12)

    # Basic Info
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="1. Incident Information", ln=1)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 8, txt=f"Incident ID: {incident.incident_id}", ln=1)
    pdf.cell(200, 8, txt=f"Device ID: {incident.device_id}", ln=1)
    pdf.cell(200, 8, txt=f"Site: {incident.site} | Line: {incident.line}", ln=1)
    pdf.cell(200, 8, txt=f"Created At: {incident.created_at}", ln=1)
    pdf.cell(200, 8, txt=f"Status: {incident.status} | Severity: {incident.severity}", ln=1)
    pdf.ln(5)

    # Details
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="2. Description", ln=1)
    pdf.set_font("Arial", size=10)
    # Handle potentially long descriptions
    desc = str(incident.description) if incident.description else "No description provided."
    # A simple way to handle encoding issues if any non-latin chars exist
    desc = desc.encode('latin-1', 'replace').decode('latin-1') 
    pdf.multi_cell(0, 8, txt=desc)
    pdf.ln(5)

    # Assets Summary
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="3. Attached Assets", ln=1)
    pdf.set_font("Arial", size=10)
    if assets:
        for asset in assets:
            pdf.cell(200, 8, txt=f"- [{asset.asset_type}] {asset.file_name} ({asset.file_size} bytes)", ln=1)
    else:
        pdf.cell(200, 8, txt="No assets attached.", ln=1)

    # Save PDF
    os.makedirs(settings.REPORT_OUTPUT_DIR, exist_ok=True)
    file_name = f"incident_report_{incident_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    file_path = os.path.join(settings.REPORT_OUTPUT_DIR, file_name)
    
    pdf.output(file_path)
    
    return file_path
