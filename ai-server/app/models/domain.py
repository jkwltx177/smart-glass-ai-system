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

class SensorTimeseries(Base):
    __tablename__ = "sensor_timeseries"

    ts_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    incident_id = Column(BigInteger, nullable=False)
    device_id = Column(String(30), index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    engine_rpm = Column(Integer)
    coolant_temp = Column(Numeric(5, 2))
    intake_air_temp = Column(Numeric(5, 2))
    throttle_pos = Column(Numeric(5, 2))
    fuel_trim = Column(Numeric(5, 2))
    maf = Column(Numeric(6, 2))
    failure = Column(Boolean, default=False, nullable=False)


class AIOpsEvent(Base):
    __tablename__ = "aiops_events"

    event_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    event_type = Column(String(50), index=True, nullable=False)
    severity = Column(String(20), index=True, nullable=False, default="INFO")
    service = Column(String(50), index=True, nullable=False)
    stage = Column(String(50), index=True, nullable=True)
    incident_id = Column(BigInteger, index=True, nullable=True)
    device_id = Column(String(30), index=True, nullable=True)
    model_name = Column(String(100), nullable=True)
    status = Column(String(30), index=True, nullable=True)
    message = Column(String(255), nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)


class RetrainJob(Base):
    __tablename__ = "retrain_jobs"

    job_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    model_target = Column(String(100), nullable=False, default="prediction")
    period_months = Column(Integer, nullable=False, default=3)
    trigger_reason = Column(String(255), nullable=False, default="manual")
    requested_by = Column(String(100), nullable=True)
    status = Column(String(30), index=True, nullable=False, default="queued")
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class IncidentReport(Base):
    __tablename__ = "incident_reports"

    report_pk = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    incident_id = Column(BigInteger, index=True, nullable=False)
    report_type = Column(String(30), nullable=False, default="quality")
    report_url = Column(String(500), nullable=True)
    html_report_url = Column(String(500), nullable=True)
    summary = Column(String(255), nullable=True)
    generated_at = Column(DateTime, default=func.now(), index=True)
