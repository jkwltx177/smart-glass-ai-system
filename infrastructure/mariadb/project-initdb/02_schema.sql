-- =========================================================
-- smart_glass_dev 스키마 초기화
-- =========================================================
DROP DATABASE IF EXISTS smart_glass_dev;
CREATE DATABASE smart_glass_dev
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE smart_glass_dev;

-- =========================================================
-- 1. devices
-- =========================================================
CREATE TABLE devices (
    device_id       VARCHAR(30)  NOT NULL,
    device_name     VARCHAR(100) NOT NULL,
    vehicle_type    VARCHAR(50)  NOT NULL,
    line_or_site    VARCHAR(100) NOT NULL,
    location        VARCHAR(100) NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 2. lots
-- =========================================================
CREATE TABLE lots (
    lot_id          VARCHAR(30)  NOT NULL,
    lot_name        VARCHAR(100) NOT NULL,
    product_type    VARCHAR(50)  NOT NULL,
    produced_at     DATETIME     NOT NULL,
    note            TEXT         NULL,
    PRIMARY KEY (lot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 3. inspections
-- =========================================================
CREATE TABLE inspections (
    inspection_id   BIGINT       NOT NULL AUTO_INCREMENT,
    device_id       VARCHAR(30)  NOT NULL,
    lot_id          VARCHAR(30)  NOT NULL,
    started_at      DATETIME     NOT NULL,
    ended_at        DATETIME     NULL,
    operator_name   VARCHAR(50)  NOT NULL,
    issue_summary   TEXT         NULL,
    PRIMARY KEY (inspection_id),
    CONSTRAINT fk_inspections_device
        FOREIGN KEY (device_id) REFERENCES devices(device_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT fk_inspections_lot
        FOREIGN KEY (lot_id) REFERENCES lots(lot_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 4. manual_docs
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
-- 5. case_db
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
-- 6. error_logs
-- =========================================================
CREATE TABLE error_logs (
    log_id               BIGINT        NOT NULL AUTO_INCREMENT,
    inspection_id        BIGINT        NOT NULL,
    device_id            VARCHAR(30)   NOT NULL,
    error_timestamp      DATETIME      NOT NULL,
    dtc_code             VARCHAR(20)   NOT NULL,
    dtc_description      VARCHAR(255)  NOT NULL,
    ecu_module           VARCHAR(100)  NOT NULL,
    error_severity       VARCHAR(20)   NOT NULL,
    raw_message          TEXT          NULL,
    PRIMARY KEY (log_id),
    CONSTRAINT fk_error_logs_inspection
        FOREIGN KEY (inspection_id) REFERENCES inspections(inspection_id)
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
    inspection_id    BIGINT       NOT NULL,
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
    CONSTRAINT fk_sensor_timeseries_inspection
        FOREIGN KEY (inspection_id) REFERENCES inspections(inspection_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    CONSTRAINT fk_sensor_timeseries_device
        FOREIGN KEY (device_id) REFERENCES devices(device_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    INDEX idx_sensor_timeseries_device_time (device_id, timestamp),
    INDEX idx_sensor_timeseries_inspection_id (inspection_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================================================
-- 별도 인덱스
-- =========================================================

-- inspections
CREATE INDEX idx_inspections_device_id
    ON inspections (device_id);

CREATE INDEX idx_inspections_lot_id
    ON inspections (lot_id);

-- error_logs
CREATE INDEX idx_error_logs_device_time
    ON error_logs (device_id, error_timestamp);

CREATE INDEX idx_error_logs_inspection_id
    ON error_logs (inspection_id);

CREATE INDEX idx_error_logs_dtc_code
    ON error_logs (dtc_code);

-- manual_docs
CREATE INDEX idx_manual_docs_related_dtc
    ON manual_docs (related_dtc_code);

-- case_db
CREATE INDEX idx_case_db_dtc_code
    ON case_db (dtc_code);

CREATE INDEX idx_case_db_reference_doc_id
    ON case_db (reference_doc_id);

-- =========================================================
-- 확인용
-- =========================================================


