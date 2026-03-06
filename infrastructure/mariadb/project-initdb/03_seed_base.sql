USE smart_glass_dev;

-- =========================================================
-- 1. users
-- =========================================================
INSERT INTO users (
    user_id,
    username,
    password_hash,
    role,
    is_active,
    created_at,
    updated_at
) VALUES
(
    1,
    'kim.ops',
    '$2b$12$demo.hash.kim.ops',
    'FIELD_OPERATOR',
    TRUE,
    '2026-03-06 08:00:00',
    '2026-03-06 08:00:00'
),
(
    2,
    'lee.qa',
    '$2b$12$demo.hash.lee.qa',
    'QA_ENGINEER',
    TRUE,
    '2026-03-06 08:05:00',
    '2026-03-06 08:05:00'
),
(
    3,
    'park.test',
    '$2b$12$demo.hash.park.test',
    'FIELD_OPERATOR',
    TRUE,
    '2026-03-06 08:10:00',
    '2026-03-06 08:10:00'
),
(
    4,
    'admin.demo',
    '$2b$12$demo.hash.admin',
    'ADMIN',
    TRUE,
    '2026-03-06 08:15:00',
    '2026-03-06 08:15:00'
);

SELECT user_id, username, role, is_active FROM users;

-- =========================================================
-- 2. devices
-- =========================================================
INSERT INTO devices (
    device_id,
    device_name,
    vehicle_type,
    line_or_site,
    location,
    status,
    created_at
) VALUES
(
    'DEV-MAF-01',
    'Powertrain Inspection Rig A',
    'Sedan ECU Test',
    'Vehicle Inspection Line 1',
    'Hwaseong Plant',
    'ACTIVE',
    '2026-03-06 08:30:00'
),
(
    'DEV-ECU-02',
    'ECU Thermal Validation Bench',
    'SUV ECU Test',
    'Thermal Chamber Line',
    'Hwaseong Plant',
    'ACTIVE',
    '2026-03-06 08:35:00'
),
(
    'DEV-IGN-03',
    'Ignition Quality Bench C',
    'Sedan Ignition Test',
    'Final Inspection Line 2',
    'Ulsan Plant',
    'ACTIVE',
    '2026-03-06 08:40:00'
);

SELECT * FROM devices;

-- =========================================================
-- 3. incidents (demo scenarios)
-- =========================================================
INSERT INTO incidents (
    incident_id,
    user_id,
    device_id,
    site,
    line,
    device_type,
    title,
    description,
    status,
    severity,
    started_at,
    ended_at,
    created_at,
    updated_at
) VALUES
(
    1,
    1,
    'DEV-MAF-01',
    'Hwaseong Plant',
    'Vehicle Inspection Line 1',
    'Air Intake Control ECU',
    'Airflow sensing anomaly during powertrain inspection',
    'Engine output drop detected during intake sensor validation. OBD indicated airflow range/performance issue during powertrain inspection.',
    'IN_PROGRESS',
    'HIGH',
    '2026-03-06 09:00:00',
    NULL,
    '2026-03-06 09:00:00',
    '2026-03-06 09:19:05'
),
(
    2,
    2,
    'DEV-ECU-02',
    'Hwaseong Plant',
    'Thermal Chamber Line',
    'Engine ECU',
    'ECU processor fault under thermal stress',
    'ECU temperature continuously increased during thermal chamber validation. Processor fault suspected under sustained heat load.',
    'OPEN',
    'CRITICAL',
    '2026-03-06 10:00:00',
    NULL,
    '2026-03-06 10:00:00',
    '2026-03-06 10:14:35'
),
(
    3,
    3,
    'DEV-IGN-03',
    'Ulsan Plant',
    'Final Inspection Line 2',
    'Ignition Control Module',
    'Cylinder 2 misfire during ignition quality check',
    'Engine vibration increased during ignition quality check. Cylinder 2 combustion instability suspected from OBD result.',
    'OPEN',
    'HIGH',
    '2026-03-06 11:00:00',
    NULL,
    '2026-03-06 11:00:00',
    '2026-03-06 11:12:00'
);

SELECT incident_id, user_id, device_id, title, status, severity FROM incidents;

-- =========================================================
-- 4. incident_assets
-- =========================================================
INSERT INTO incident_assets (
    incident_id,
    asset_type,
    file_name,
    file_path,
    mime_type,
    file_size,
    uploaded_by,
    uploaded_at
) VALUES
(
    1,
    'IMAGE',
    'engine_bay_intake_issue.jpg',
    '/demo/assets/incident_1/engine_bay_intake_issue.jpg',
    'image/jpeg',
    428531,
    1,
    '2026-03-06 09:05:00'
),
(
    2,
    'IMAGE',
    'ecu_thermal_validation_bench.jpg',
    '/demo/assets/incident_2/ecu_thermal_validation_bench.jpg',
    'image/jpeg',
    512800,
    2,
    '2026-03-06 10:03:00'
),
(
    3,
    'IMAGE',
    'ignition_coil_cylinder2_check.jpg',
    '/demo/assets/incident_3/ignition_coil_cylinder2_check.jpg',
    'image/jpeg',
    401220,
    3,
    '2026-03-06 11:02:00'
);

SELECT asset_id, incident_id, asset_type, file_name FROM incident_assets;

-- =========================================================
-- 5. incident_telemetry (raw JSON preserved)
-- =========================================================
INSERT INTO incident_telemetry (
    incident_id,
    payload_json,
    recorded_at,
    created_at
) VALUES
(
    1,
    '{"case_id":"GLOBAL_QA_2026_0101","image_path":"engine_bay_intake_issue.jpg","sensor_data":{"engine_rpm_fluctuation":400,"short_term_fuel_trim_percent":18,"intake_air_temp_celsius":32,"throttle_delay_seconds":1.5},"log_code":{"dtc":"P0101","description":"Mass Air Flow Sensor Performance Problem"},"voice_text":"시동은 걸리는데 출력이 약하고 엔진이 떨립니다.","visual_analysis_summary":["흡기 덕트 연결부 느슨해 보임","엔진 상단 임시 냉각 팬 설치됨","배터리 단자 정상","냉각수 수위 정상"],"root_cause_candidates":[{"cause":"Intake air leak","confidence":0.42},{"cause":"MAF sensor contamination","confidence":0.37},{"cause":"Connector pin contact issue","confidence":0.21}]}' ,
    '2026-03-06 09:12:15',
    '2026-03-06 09:12:20'
),
(
    2,
    '{"case_id":"GLOBAL_QA_2026_0606","image_path":"ecu_thermal_validation_bench.jpg","sensor_data":{"ecu_temp_celsius":118.4,"supply_voltage":12.1,"reset_count":3,"fan_status":"ON"},"log_code":{"dtc":"P0606","description":"ECU Processor Fault"},"voice_text":"열 챔버 테스트 중 ECU 오류가 반복됩니다.","visual_analysis_summary":["ECU 하우징 주변 열 집중 흔적 관찰","냉각 덕트 일부 편위","커넥터 체결 상태는 양호해 보임"],"root_cause_candidates":[{"cause":"Thermal concentration near ECU housing","confidence":0.46},{"cause":"Internal processor instability","confidence":0.39},{"cause":"Power supply noise under heat","confidence":0.15}]}' ,
    '2026-03-06 10:10:30',
    '2026-03-06 10:10:35'
),
(
    3,
    '{"case_id":"GLOBAL_QA_2026_0302","image_path":"ignition_coil_cylinder2_check.jpg","sensor_data":{"idle_rpm_variation":230,"misfire_count_cyl2":17,"spark_advance_deg":8.5,"injector_balance_percent":4.2},"log_code":{"dtc":"P0302","description":"Cylinder 2 Misfire Detected"},"voice_text":"공회전이 불안정하고 가속 시 떨림이 심합니다.","visual_analysis_summary":["2번 실린더 점화코일 외관 변색","점화플러그 마모 가능성","배선 체결은 정상 범위"],"root_cause_candidates":[{"cause":"Ignition coil degradation","confidence":0.51},{"cause":"Spark plug wear","confidence":0.34},{"cause":"Injector imbalance","confidence":0.15}]}' ,
    '2026-03-06 11:07:00',
    '2026-03-06 11:07:05'
);

SELECT telemetry_id, incident_id, recorded_at FROM incident_telemetry;

-- =========================================================
-- 6. manual_docs
-- =========================================================
INSERT INTO manual_docs (
    doc_id,
    title,
    category,
    source,
    related_dtc_code,
    content,
    created_at
) VALUES
(
    1,
    'MAF Sensor Diagnostic Procedure',
    'diagnostic',
    'OEM Manual',
    'P0101',
    'When DTC P0101 is detected, inspect the mass air flow sensor for dust contamination, oil residue, or signal instability. Check sensor connector pin contact, verify harness locking condition, and inspect the intake duct for unmetered air leakage. If fuel trim is significantly positive and airflow value is unstable, clean the sensor and re-check signal consistency before replacement.',
    '2026-03-05 13:00:00'
),
(
    2,
    'Intake Air Leak Inspection Guide',
    'maintenance',
    'Internal QA Guide',
    'P0101',
    'For repeated airflow range/performance faults, inspect the intake hose, clamp looseness, and downstream air leak path. Confirm whether ECU-calculated airflow differs from expected engine load. If connector contact is normal and contamination is low, prioritize intake leak inspection.',
    '2026-03-05 13:10:00'
),
(
    3,
    'ECU Processor Fault Initial Check',
    'diagnostic',
    'OEM Manual',
    'P0606',
    'When DTC P0606 occurs, verify ECU power stability, connector seating, and processor fault recurrence. Check whether thermal load, supply voltage instability, or abnormal reset behavior is present. If the fault persists under repeated high temperature operation, consider ECU replacement review.',
    '2026-03-05 13:20:00'
),
(
    4,
    'ECU Thermal Management Inspection Procedure',
    'safety',
    'Internal QA Guide',
    'P0606',
    'For rising ECU temperature conditions, inspect cooling airflow around the ECU housing, connector heat damage, and local thermal concentration. If temperature continues to rise beyond the internal acceptance range, suspend continuous validation and escalate for hardware review.',
    '2026-03-05 13:30:00'
),
(
    5,
    'Cylinder Misfire Diagnostic Manual',
    'diagnostic',
    'OEM Manual',
    'P0302',
    'When DTC P0302 is detected, inspect cylinder 2 ignition coil, spark plug condition, and injector firing quality. Review RPM fluctuation and abnormal combustion indicators. Perform coil swap test and verify whether the misfire follows the component.',
    '2026-03-05 13:40:00'
),
(
    6,
    'Ignition Coil and Spark Plug Inspection Guide',
    'maintenance',
    'Internal QA Guide',
    'P0302',
    'Repeated cylinder 2 misfire may result from ignition coil degradation, spark plug wear, or injector imbalance. Inspect plug electrode wear, secondary ignition leakage, and unstable combustion symptoms before replacing ECU-related control parts.',
    '2026-03-05 13:50:00'
);

SELECT doc_id, title, related_dtc_code FROM manual_docs;

-- =========================================================
-- 7. case_db
-- =========================================================
INSERT INTO case_db (
    case_id,
    dtc_code,
    symptom,
    root_cause,
    action_steps,
    result_summary,
    reference_doc_id,
    created_at
) VALUES
(
    1,
    'P0101',
    'Engine response became weak during validation and airflow reading fluctuated abnormally.',
    'MAF sensor contamination caused unstable airflow signal input to ECU.',
    '1) Disconnect connector and inspect terminals. 2) Clean MAF sensing element. 3) Recheck airflow signal and fuel trim.',
    'After sensor cleaning, airflow stabilized and fuel trim moved toward normal range.',
    1,
    '2026-03-05 14:00:00'
),
(
    2,
    'P0101',
    'Repeated airflow performance fault occurred after maintenance work.',
    'Intake hose leak introduced unmetered air, causing ECU airflow estimation mismatch.',
    '1) Inspect intake duct and clamp. 2) Remove leak source. 3) Re-run OBD check and confirm DTC clear.',
    'Air leak was removed and repeated P0101 event did not recur.',
    2,
    '2026-03-05 14:05:00'
),
(
    3,
    'P0606',
    'ECU fault triggered repeatedly during thermal validation cycle.',
    'Cooling airflow around ECU housing was insufficient, leading to thermal stress on processor area.',
    '1) Check ECU mounting and airflow path. 2) Inspect connector heat marks. 3) Pause test and cool down ECU.',
    'Temperature rise slowed after airflow correction and no immediate recurrence was observed.',
    4,
    '2026-03-05 14:10:00'
),
(
    4,
    'P0606',
    'Processor fault persisted under high temperature despite normal external connector fit.',
    'Internal ECU processor instability under sustained thermal load.',
    '1) Verify supply voltage. 2) Reproduce under controlled heat condition. 3) Review ECU replacement.',
    'Fault was isolated to ECU internal condition and replacement recommendation was issued.',
    3,
    '2026-03-05 14:15:00'
),
(
    5,
    'P0302',
    'Engine vibration increased and combustion became unstable during line inspection.',
    'Cylinder 2 ignition coil degradation caused intermittent misfire.',
    '1) Swap ignition coil. 2) Recheck cylinder-specific misfire. 3) Replace faulty coil.',
    'Misfire moved with the coil during swap test, confirming component issue.',
    5,
    '2026-03-05 14:20:00'
),
(
    6,
    'P0302',
    'OBD detected cylinder 2 misfire with unstable idle and rough acceleration.',
    'Spark plug wear and partial combustion instability were identified.',
    '1) Inspect spark plug electrode. 2) Replace worn plug. 3) Confirm injector balance if symptom remains.',
    'Replacing the spark plug reduced misfire count and stabilized idle RPM.',
    6,
    '2026-03-05 14:25:00'
);

SELECT case_id, dtc_code, reference_doc_id FROM case_db;

-- =========================================================
-- 8. error_logs
-- =========================================================
INSERT INTO error_logs (
    incident_id,
    device_id,
    error_timestamp,
    dtc_code,
    dtc_description,
    ecu_module,
    error_severity,
    raw_message
) VALUES
(
    1,
    'DEV-MAF-01',
    '2026-03-06 09:12:10',
    'P0101',
    'Mass Air Flow Sensor Range/Performance',
    'Air Intake Control ECU',
    'WARNING',
    'Repeated airflow range deviation detected during intake sensor validation.'
),
(
    1,
    'DEV-MAF-01',
    '2026-03-06 09:15:40',
    'P0101',
    'Mass Air Flow Sensor Range/Performance',
    'Air Intake Control ECU',
    'WARNING',
    'Fuel trim remained positive while airflow signal fluctuated beyond expected range.'
),
(
    1,
    'DEV-MAF-01',
    '2026-03-06 09:19:05',
    'P0101',
    'Mass Air Flow Sensor Range/Performance',
    'Air Intake Control ECU',
    'CRITICAL',
    'Connector contamination or intake leak suspected due to repeated airflow instability within 10 minutes.'
),
(
    2,
    'DEV-ECU-02',
    '2026-03-06 10:08:20',
    'P0606',
    'ECU Processor Fault',
    'Engine ECU',
    'WARNING',
    'Processor fault event recorded during thermal validation cycle.'
),
(
    2,
    'DEV-ECU-02',
    '2026-03-06 10:11:00',
    'P0606',
    'ECU Processor Fault',
    'Engine ECU',
    'WARNING',
    'Abnormal ECU behavior persisted as temperature continued to rise.'
),
(
    2,
    'DEV-ECU-02',
    '2026-03-06 10:14:35',
    'P0606',
    'ECU Processor Fault',
    'Engine ECU',
    'CRITICAL',
    'ECU processor checksum mismatch detected under elevated thermal load.'
),
(
    3,
    'DEV-IGN-03',
    '2026-03-06 11:06:10',
    'P0302',
    'Cylinder 2 Misfire Detected',
    'Ignition Control Module',
    'WARNING',
    'Cylinder 2 combustion instability detected during ignition quality inspection.'
),
(
    3,
    'DEV-IGN-03',
    '2026-03-06 11:09:25',
    'P0302',
    'Cylinder 2 Misfire Detected',
    'Ignition Control Module',
    'WARNING',
    'RPM fluctuation and rough combustion pattern repeated within short interval.'
),
(
    3,
    'DEV-IGN-03',
    '2026-03-06 11:12:00',
    'P0302',
    'Cylinder 2 Misfire Detected',
    'Ignition Control Module',
    'CRITICAL',
    'Ignition coil or spark plug degradation suspected from repeated cylinder 2 misfire event.'
);

SELECT log_id, incident_id, dtc_code, error_timestamp
FROM error_logs
ORDER BY incident_id, error_timestamp;

-- =========================================================
-- 9. sensor_timeseries
-- =========================================================
INSERT INTO sensor_timeseries (
    incident_id,
    device_id,
    timestamp,
    engine_rpm,
    coolant_temp,
    intake_air_temp,
    throttle_pos,
    fuel_trim,
    maf,
    failure
) VALUES
(1, 'DEV-MAF-01', '2026-03-06 09:10:00', 820, 91.20, 31.50, 12.40,  8.50, 10.80, FALSE),
(1, 'DEV-MAF-01', '2026-03-06 09:12:00', 860, 91.80, 32.00, 14.10, 12.70,  9.40, FALSE),
(1, 'DEV-MAF-01', '2026-03-06 09:15:00', 910, 92.40, 32.30, 16.80, 17.90,  8.10, TRUE),
(1, 'DEV-MAF-01', '2026-03-06 09:18:00', 980, 92.90, 32.80, 18.50, 19.20,  7.60, TRUE),
(2, 'DEV-ECU-02', '2026-03-06 10:06:00', 1100, 95.00, 34.00, 19.50,  2.20, 15.20, FALSE),
(2, 'DEV-ECU-02', '2026-03-06 10:09:00', 1120, 98.50, 35.20, 20.00,  2.60, 15.10, FALSE),
(2, 'DEV-ECU-02', '2026-03-06 10:12:00', 1140, 102.30, 36.10, 20.40,  3.10, 14.90, TRUE),
(2, 'DEV-ECU-02', '2026-03-06 10:14:00', 1150, 106.80, 36.80, 20.60,  3.40, 14.70, TRUE),
(3, 'DEV-IGN-03', '2026-03-06 11:04:00', 790, 88.40, 29.80, 10.30,  1.40, 11.10, FALSE),
(3, 'DEV-IGN-03', '2026-03-06 11:07:00', 760, 89.10, 30.10, 11.20,  1.80, 10.90, TRUE),
(3, 'DEV-IGN-03', '2026-03-06 11:09:00', 720, 89.40, 30.30, 12.10,  2.10, 10.70, TRUE),
(3, 'DEV-IGN-03', '2026-03-06 11:12:00', 700, 89.80, 30.40, 13.50,  2.60, 10.50, TRUE);

SELECT ts_id, incident_id, device_id, timestamp, failure
FROM sensor_timeseries
ORDER BY incident_id, timestamp;

-- =========================================================
-- 10. predictions
-- =========================================================
INSERT INTO predictions (
    incident_id,
    model_name,
    model_version,
    failure_probability,
    predicted_rul_minutes,
    anomaly_score,
    prediction_summary,
    predicted_at
) VALUES
(
    1,
    'vehicle-quality-anomaly-detector',
    'v1.2.0',
    0.8420,
    55,
    0.7810,
    'P0101 scenario shows high likelihood of intake air leak or MAF contamination. Immediate connector and duct inspection recommended.',
    '2026-03-06 09:19:20'
),
(
    2,
    'vehicle-quality-anomaly-detector',
    'v1.2.0',
    0.9310,
    18,
    0.9020,
    'P0606 scenario indicates severe thermal-risk condition. Suspend test and review ECU thermal path and processor integrity.',
    '2026-03-06 10:14:50'
),
(
    3,
    'vehicle-quality-anomaly-detector',
    'v1.2.0',
    0.8840,
    42,
    0.8160,
    'P0302 scenario suggests cylinder-2 ignition component degradation. Coil swap and spark plug inspection should be prioritized.',
    '2026-03-06 11:12:15'
);

SELECT prediction_id, incident_id, failure_probability, predicted_rul_minutes
FROM predictions;

-- =========================================================
-- 11. reports
-- =========================================================
INSERT INTO reports (
    incident_id,
    report_type,
    report_title,
    report_url,
    file_format,
    generated_by,
    status,
    created_at
) VALUES
(
    1,
    'INCIDENT_SUMMARY',
    'P0101 Incident Summary Report',
    '/demo/reports/incident_1_summary.pdf',
    'pdf',
    4,
    'GENERATED',
    '2026-03-06 09:21:00'
),
(
    2,
    'INCIDENT_SUMMARY',
    'P0606 Incident Summary Report',
    '/demo/reports/incident_2_summary.pdf',
    'pdf',
    4,
    'GENERATED',
    '2026-03-06 10:16:00'
),
(
    3,
    'INCIDENT_SUMMARY',
    'P0302 Incident Summary Report',
    '/demo/reports/incident_3_summary.pdf',
    'pdf',
    4,
    'GENERATED',
    '2026-03-06 11:14:00'
);

SELECT report_id, incident_id, report_type, report_title
FROM reports;
