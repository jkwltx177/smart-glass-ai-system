from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Text, Boolean, Numeric
from sqlalchemy.sql import func
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True)
    password_hash = Column(String(255))
    role = Column(String(30))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class Device(Base):
    __tablename__ = "devices"
    
    device_id = Column(String(30), primary_key=True, index=True)
    device_name = Column(String(100))
    vehicle_type = Column(String(50))
    line_or_site = Column(String(100))
    location = Column(String(100))
    status = Column(String(20))
    created_at = Column(DateTime, default=func.now())

class Incident(Base):
    __tablename__ = "incidents"
    
    incident_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    user_id = Column(BigInteger) # FK to users.user_id
    device_id = Column(String(30)) # FK to devices.device_id
    site = Column(String(100))
    line = Column(String(100))
    device_type = Column(String(50))
    title = Column(String(200))
    description = Column(Text)
    status = Column(String(20))
    severity = Column(String(20))
    started_at = Column(DateTime)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class IncidentAsset(Base):
    __tablename__ = "incident_assets"
    
    asset_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    incident_id = Column(BigInteger) # FK to incidents.incident_id
    asset_type = Column(String(20))
    file_name = Column(String(255))
    file_path = Column(String(500))
    mime_type = Column(String(100))
    file_size = Column(BigInteger)
    uploaded_by = Column(BigInteger) # FK to users.user_id
    uploaded_at = Column(DateTime, default=func.now())

class Prediction(Base):
    __tablename__ = "predictions"
    
    prediction_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    incident_id = Column(BigInteger) # FK to incidents.incident_id
    model_name = Column(String(100))
    model_version = Column(String(50))
    failure_probability = Column(Numeric(6, 4))
    predicted_rul_minutes = Column(Integer)
    anomaly_score = Column(Numeric(6, 4))
    prediction_summary = Column(Text)
    predicted_at = Column(DateTime, default=func.now())

class ErrorLog(Base):
    __tablename__ = "error_logs"
    
    log_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    incident_id = Column(BigInteger)
    device_id = Column(String(30))
    error_timestamp = Column(DateTime, default=func.now())
    dtc_code = Column(String(20))
    dtc_description = Column(String(255))
    ecu_module = Column(String(100))
    error_severity = Column(String(20))
    raw_message = Column(Text)
