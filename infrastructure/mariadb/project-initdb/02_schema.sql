-- =========================================================
-- smart_glass_dev (minimal api schema)
-- =========================================================
DROP DATABASE IF EXISTS smart_glass_dev;
CREATE DATABASE smart_glass_dev
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE smart_glass_dev;

-- =========================================================
-- 1. users
-- =========================================================
CREATE TABLE users (
    user_id          BIGINT       NOT NULL AUTO_INCREMENT,
    username         VARCHAR(50)  NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,
    role             VARCHAR(30)  NOT NULL DEFAULT 'FIELD_OPERATOR',
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 2. devices
-- =========================================================
CREATE TABLE devices (
    device_id        VARCHAR(30)  NOT NULL,
    device_name      VARCHAR(100) NOT NULL,
    vehicle_type     VARCHAR(50)  NOT NULL,
    line_or_site     VARCHAR(100) NOT NULL,
    location         VARCHAR(100) NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 3. incidents
-- =========================================================
CREATE TABLE incidents (
    incident_id      BIGINT       NOT NULL AUTO_INCREMENT,
    user_id          BIGINT       NULL,
    device_id        VARCHAR(30)  NOT NULL,
    site             VARCHAR(100) NOT NULL,
    line             VARCHAR(100) NOT NULL,
    device_type      VARCHAR(50)  NOT NULL,
    title            VARCHAR(200) NULL,
    description      TEXT         NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'OPEN',
    severity         VARCHAR(20)  NOT NULL DEFAULT 'MEDIUM',
    started_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at         DATETIME     NULL,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (incident_id),
    CONSTRAINT fk_incidents_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    CONSTRAINT fk_incidents_device
        FOREIGN KEY (device_id) REFERENCES devices(device_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 4. incident_assets
-- =========================================================
CREATE TABLE incident_assets (
    asset_id         BIGINT       NOT NULL AUTO_INCREMENT,
    incident_id      BIGINT       NOT NULL,
    asset_type       VARCHAR(20)  NOT NULL,
    file_name        VARCHAR(255) NOT NULL,
    file_path        VARCHAR(500) NOT NULL,
    mime_type        VARCHAR(100) NULL,
    file_size        BIGINT       NULL,
    uploaded_by      BIGINT       NULL,
    uploaded_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asset_id),
    CONSTRAINT fk_incident_assets_incident
        FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    CONSTRAINT fk_incident_assets_user
        FOREIGN KEY (uploaded_by) REFERENCES users(user_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 5. incident_telemetry
-- =========================================================
CREATE TABLE incident_telemetry (
    telemetry_id     BIGINT       NOT NULL AUTO_INCREMENT,
    incident_id      BIGINT       NOT NULL,
    payload_json     LONGTEXT     NOT NULL,
    recorded_at      DATETIME     NULL,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (telemetry_id),
    CONSTRAINT fk_incident_telemetry_incident
        FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 6. error_logs
-- =========================================================
CREATE TABLE error_logs (
    log_id               BIGINT        NOT NULL AUTO_INCREMENT,
    incident_id          BIGINT        NOT NULL,
    device_id            VARCHAR(30)   NOT NULL,
    error_timestamp      DATETIME      NOT NULL,
    dtc_code             VARCHAR(20)   NOT NULL,
    dtc_description      VARCHAR(255)  NOT NULL,
    ecu_module           VARCHAR(100)  NOT NULL,
    error_severity       VARCHAR(20)   NOT NULL,
    raw_message          TEXT          NULL,
    PRIMARY KEY (log_id),
    CONSTRAINT fk_error_logs_incident
        FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    CONSTRAINT fk_error_logs_device
        FOREIGN KEY (device_id) REFERENCES devices(device_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 7. sensor_timeseries
-- =========================================================
CREATE TABLE sensor_timeseries (
    ts_id            BIGINT       NOT NULL AUTO_INCREMENT,
    incident_id      BIGINT       NOT NULL,
    device_id        VARCHAR(30)  NOT NULL,
    timestamp        DATETIME     NOT NULL,
    engine_rpm       INT          NULL,
    coolant_temp     DECIMAL(5,2) NULL,
    intake_air_temp  DECIMAL(5,2) NULL,
    throttle_pos     DECIMAL(5,2) NULL,
    fuel_trim        DECIMAL(5,2) NULL,
    maf              DECIMAL(6,2) NULL,
    failure          BOOLEAN      NOT NULL DEFAULT FALSE,
    PRIMARY KEY (ts_id),
    CONSTRAINT fk_sensor_timeseries_incident
        FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    CONSTRAINT fk_sensor_timeseries_device
        FOREIGN KEY (device_id) REFERENCES devices(device_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 8. manual_docs
-- =========================================================
CREATE TABLE manual_docs (
    doc_id              BIGINT        NOT NULL AUTO_INCREMENT,
    title               VARCHAR(200)  NOT NULL,
    category            VARCHAR(50)   NOT NULL,
    source              VARCHAR(100)  NOT NULL,
    related_dtc_code    VARCHAR(20)   NULL,
    content             TEXT          NOT NULL,
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (doc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 9. case_db
-- =========================================================
CREATE TABLE case_db (
    case_id              BIGINT       NOT NULL AUTO_INCREMENT,
    dtc_code             VARCHAR(20)  NOT NULL,
    symptom              TEXT         NOT NULL,
    root_cause           TEXT         NOT NULL,
    action_steps         TEXT         NOT NULL,
    result_summary       TEXT         NULL,
    reference_doc_id     BIGINT       NULL,
    created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_id),
    CONSTRAINT fk_case_db_reference_doc
        FOREIGN KEY (reference_doc_id) REFERENCES manual_docs(doc_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 10. predictions
-- =========================================================
CREATE TABLE predictions (
    prediction_id            BIGINT        NOT NULL AUTO_INCREMENT,
    incident_id              BIGINT        NOT NULL,
    model_name               VARCHAR(100)  NOT NULL,
    model_version            VARCHAR(50)   NOT NULL,
    failure_probability      DECIMAL(6,4)  NULL,
    predicted_rul_minutes    INT           NULL,
    anomaly_score            DECIMAL(6,4)  NULL,
    prediction_summary       TEXT          NULL,
    predicted_at             DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (prediction_id),
    CONSTRAINT fk_predictions_incident
        FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 11. aiops_events
-- =========================================================
CREATE TABLE aiops_events (
    event_id           BIGINT        NOT NULL AUTO_INCREMENT,
    event_type         VARCHAR(50)   NOT NULL,
    severity           VARCHAR(20)   NOT NULL DEFAULT 'INFO',
    service            VARCHAR(50)   NOT NULL,
    stage              VARCHAR(50)   NULL,
    incident_id        BIGINT        NULL,
    device_id          VARCHAR(30)   NULL,
    model_name         VARCHAR(100)  NULL,
    status             VARCHAR(30)   NULL,
    message            VARCHAR(255)  NULL,
    payload_json       TEXT          NULL,
    created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id),
    KEY idx_aiops_events_type (event_type),
    KEY idx_aiops_events_severity (severity),
    KEY idx_aiops_events_service (service),
    KEY idx_aiops_events_stage (stage),
    KEY idx_aiops_events_incident (incident_id),
    KEY idx_aiops_events_device (device_id),
    KEY idx_aiops_events_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 12. retrain_jobs
-- =========================================================
CREATE TABLE retrain_jobs (
    job_id              BIGINT        NOT NULL AUTO_INCREMENT,
    model_target        VARCHAR(100)  NOT NULL DEFAULT 'prediction',
    period_months       INT           NOT NULL DEFAULT 3,
    trigger_reason      VARCHAR(255)  NOT NULL DEFAULT 'manual',
    requested_by        VARCHAR(100)  NULL,
    status              VARCHAR(30)   NOT NULL DEFAULT 'queued',
    payload_json        TEXT          NULL,
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at          DATETIME      NULL,
    completed_at        DATETIME      NULL,
    PRIMARY KEY (job_id),
    KEY idx_retrain_jobs_status (status),
    KEY idx_retrain_jobs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 13. reports
-- =========================================================
CREATE TABLE reports (
    report_id          BIGINT       NOT NULL AUTO_INCREMENT,
    incident_id        BIGINT       NULL,
    report_type        VARCHAR(50)  NOT NULL,
    report_title       VARCHAR(200) NOT NULL,
    report_url         VARCHAR(500) NOT NULL,
    file_format        VARCHAR(20)  NOT NULL DEFAULT 'pdf',
    generated_by       BIGINT       NULL,
    status             VARCHAR(20)  NOT NULL DEFAULT 'GENERATED',
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (report_id),
    CONSTRAINT fk_reports_incident
        FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    CONSTRAINT fk_reports_user
        FOREIGN KEY (generated_by) REFERENCES users(user_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 12. auth_users (Java Auth Server)
-- =========================================================
CREATE TABLE auth_users (
    id                      BIGINT        NOT NULL AUTO_INCREMENT,
    username                VARCHAR(50)   NOT NULL,
    password_hash           VARCHAR(255)  NOT NULL,
    company_name            VARCHAR(120)  NOT NULL,
    company_auth_code_hash  VARCHAR(255)  NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_auth_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- INDEX
-- =========================================================
CREATE INDEX idx_incidents_user_id
    ON incidents (user_id);

CREATE INDEX idx_incidents_device_id
    ON incidents (device_id);

CREATE INDEX idx_incidents_status
    ON incidents (status);

CREATE INDEX idx_incidents_created_at
    ON incidents (created_at);

CREATE INDEX idx_incident_assets_incident_id
    ON incident_assets (incident_id);

CREATE INDEX idx_incident_assets_type
    ON incident_assets (asset_type);

CREATE INDEX idx_incident_telemetry_incident_id
    ON incident_telemetry (incident_id);

CREATE INDEX idx_incident_telemetry_recorded_at
    ON incident_telemetry (recorded_at);

CREATE INDEX idx_error_logs_incident_id
    ON error_logs (incident_id);

CREATE INDEX idx_error_logs_device_time
    ON error_logs (device_id, error_timestamp);

CREATE INDEX idx_error_logs_dtc_code
    ON error_logs (dtc_code);

CREATE INDEX idx_sensor_timeseries_incident_id
    ON sensor_timeseries (incident_id);

CREATE INDEX idx_sensor_timeseries_device_time
    ON sensor_timeseries (device_id, timestamp);

CREATE INDEX idx_manual_docs_related_dtc
    ON manual_docs (related_dtc_code);

CREATE INDEX idx_case_db_dtc_code
    ON case_db (dtc_code);

CREATE INDEX idx_case_db_reference_doc_id
    ON case_db (reference_doc_id);

CREATE INDEX idx_predictions_incident_id
    ON predictions (incident_id);

CREATE INDEX idx_predictions_predicted_at
    ON predictions (predicted_at);

CREATE INDEX idx_reports_incident_id
    ON reports (incident_id);

CREATE INDEX idx_reports_type
    ON reports (report_type);

-- =========================================================
-- CHECK
-- =========================================================
SHOW TABLES;
