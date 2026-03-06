USE smart_glass_dev;

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


INSERT INTO lots (
    lot_id,
    lot_name,
    product_type,
    produced_at,
    note
) VALUES
(
    'LOT-240601-A01',
    'MAF Sensor Validation Lot',
    'Air Intake Sensor Module',
    '2026-03-05 08:00:00',
    'Demo scenario 1 / P0101 / airflow sensing quality validation'
),
(
    'LOT-240601-B02',
    'ECU Thermal Stress Lot',
    'Engine ECU Module',
    '2026-03-05 09:00:00',
    'Demo scenario 2 / P0606 / ECU thermal stress verification'
),
(
    'LOT-240601-C03',
    'Ignition Coil Test Lot',
    'Ignition Control Assembly',
    '2026-03-05 10:00:00',
    'Demo scenario 3 / P0302 / misfire-related ignition quality check'
);

SELECT * FROM lots;


INSERT INTO inspections (
    device_id,
    lot_id,
    started_at,
    ended_at,
    operator_name,
    issue_summary
) VALUES
(
    'DEV-MAF-01',
    'LOT-240601-A01',
    '2026-03-06 09:00:00',
    '2026-03-06 09:25:00',
    'kim.ops',
    'Engine output drop detected during intake sensor validation. OBD indicated airflow range/performance issue during powertrain inspection.'
),
(
    'DEV-ECU-02',
    'LOT-240601-B02',
    '2026-03-06 10:00:00',
    '2026-03-06 10:20:00',
    'lee.qa',
    'ECU temperature continuously increased during thermal chamber validation. Processor fault suspected under sustained heat load.'
),
(
    'DEV-IGN-03',
    'LOT-240601-C03',
    '2026-03-06 11:00:00',
    '2026-03-06 11:18:00',
    'park.test',
    'Engine vibration increased during ignition quality check. Cylinder 2 combustion instability suspected from OBD result.'
);

SELECT * FROM inspections;


INSERT INTO manual_docs (
    title,
    category,
    source,
    related_dtc_code,
    content,
    created_at
) VALUES
(
    'MAF Sensor Diagnostic Procedure',
    'diagnostic',
    'OEM Manual',
    'P0101',
    'When DTC P0101 is detected, inspect the mass air flow sensor for dust contamination, oil residue, or signal instability. Check sensor connector pin contact, verify harness locking condition, and inspect the intake duct for unmetered air leakage. If fuel trim is significantly positive and airflow value is unstable, clean the sensor and re-check signal consistency before replacement.',
    '2026-03-05 13:00:00'
),
(
    'Intake Air Leak Inspection Guide',
    'maintenance',
    'Internal QA Guide',
    'P0101',
    'For repeated airflow range/performance faults, inspect the intake hose, clamp looseness, and downstream air leak path. Confirm whether ECU-calculated airflow differs from expected engine load. If connector contact is normal and contamination is low, prioritize intake leak inspection.',
    '2026-03-05 13:10:00'
),
(
    'ECU Processor Fault Initial Check',
    'diagnostic',
    'OEM Manual',
    'P0606',
    'When DTC P0606 occurs, verify ECU power stability, connector seating, and processor fault recurrence. Check whether thermal load, supply voltage instability, or abnormal reset behavior is present. If the fault persists under repeated high temperature operation, consider ECU replacement review.',
    '2026-03-05 13:20:00'
),
(
    'ECU Thermal Management Inspection Procedure',
    'safety',
    'Internal QA Guide',
    'P0606',
    'For rising ECU temperature conditions, inspect cooling airflow around the ECU housing, connector heat damage, and local thermal concentration. If temperature continues to rise beyond the internal acceptance range, suspend continuous validation and escalate for hardware review.',
    '2026-03-05 13:30:00'
),
(
    'Cylinder Misfire Diagnostic Manual',
    'diagnostic',
    'OEM Manual',
    'P0302',
    'When DTC P0302 is detected, inspect cylinder 2 ignition coil, spark plug condition, and injector firing quality. Review RPM fluctuation and abnormal combustion indicators. Perform coil swap test and verify whether the misfire follows the component.',
    '2026-03-05 13:40:00'
),
(
    'Ignition Coil and Spark Plug Inspection Guide',
    'maintenance',
    'Internal QA Guide',
    'P0302',
    'Repeated cylinder 2 misfire may result from ignition coil degradation, spark plug wear, or injector imbalance. Inspect plug electrode wear, secondary ignition leakage, and unstable combustion symptoms before replacing ECU-related control parts.',
    '2026-03-05 13:50:00'
);

SELECT doc_id, title, related_dtc_code FROM manual_docs;


INSERT INTO case_db (
    dtc_code,
    symptom,
    root_cause,
    action_steps,
    result_summary,
    reference_doc_id,
    created_at
) VALUES
(
    'P0101',
    'Engine response became weak during validation and airflow reading fluctuated abnormally.',
    'MAF sensor contamination caused unstable airflow signal input to ECU.',
    '1) Disconnect connector and inspect terminals. 2) Clean MAF sensing element. 3) Recheck airflow signal and fuel trim.',
    'After sensor cleaning, airflow stabilized and fuel trim moved toward normal range.',
    1,
    '2026-03-05 14:00:00'
),
(
    'P0101',
    'Repeated airflow performance fault occurred after maintenance work.',
    'Intake hose leak introduced unmetered air, causing ECU airflow estimation mismatch.',
    '1) Inspect intake duct and clamp. 2) Remove leak source. 3) Re-run OBD check and confirm DTC clear.',
    'Air leak was removed and repeated P0101 event did not recur.',
    2,
    '2026-03-05 14:05:00'
),
(
    'P0606',
    'ECU fault triggered repeatedly during thermal validation cycle.',
    'Cooling airflow around ECU housing was insufficient, leading to thermal stress on processor area.',
    '1) Check ECU mounting and airflow path. 2) Inspect connector heat marks. 3) Pause test and cool down ECU.',
    'Temperature rise slowed after airflow correction and no immediate recurrence was observed.',
    4,
    '2026-03-05 14:10:00'
),
(
    'P0606',
    'Processor fault persisted under high temperature despite normal external connector fit.',
    'Internal ECU processor instability under sustained thermal load.',
    '1) Verify supply voltage. 2) Reproduce under controlled heat condition. 3) Review ECU replacement.',
    'Fault was isolated to ECU internal condition and replacement recommendation was issued.',
    3,
    '2026-03-05 14:15:00'
),
(
    'P0302',
    'Engine vibration increased and combustion became unstable during line inspection.',
    'Cylinder 2 ignition coil degradation caused intermittent misfire.',
    '1) Swap ignition coil. 2) Recheck cylinder-specific misfire. 3) Replace faulty coil.',
    'Misfire moved with the coil during swap test, confirming component issue.',
    5,
    '2026-03-05 14:20:00'
),
(
    'P0302',
    'OBD detected cylinder 2 misfire with unstable idle and rough acceleration.',
    'Spark plug wear and partial combustion instability were identified.',
    '1) Inspect spark plug electrode. 2) Replace worn plug. 3) Confirm injector balance if symptom remains.',
    'Replacing the spark plug reduced misfire count and stabilized idle RPM.',
    6,
    '2026-03-05 14:25:00'
);

SELECT case_id, dtc_code, reference_doc_id FROM case_db;


INSERT INTO error_logs (
    inspection_id,
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
    'Warning',
    'Repeated airflow range deviation detected during intake sensor validation.'
),
(
    1,
    'DEV-MAF-01',
    '2026-03-06 09:15:40',
    'P0101',
    'Mass Air Flow Sensor Range/Performance',
    'Air Intake Control ECU',
    'Warning',
    'Fuel trim remained positive while airflow signal fluctuated beyond expected range.'
),
(
    1,
    'DEV-MAF-01',
    '2026-03-06 09:19:05',
    'P0101',
    'Mass Air Flow Sensor Range/Performance',
    'Air Intake Control ECU',
    'Critical',
    'Connector contamination or intake leak suspected due to repeated airflow instability within 10 minutes.'
),

(
    2,
    'DEV-ECU-02',
    '2026-03-06 10:08:20',
    'P0606',
    'ECU Processor Fault',
    'Engine ECU',
    'Warning',
    'Processor fault event recorded during thermal validation cycle.'
),
(
    2,
    'DEV-ECU-02',
    '2026-03-06 10:11:00',
    'P0606',
    'ECU Processor Fault',
    'Engine ECU',
    'Warning',
    'Abnormal ECU behavior persisted as temperature continued to rise.'
),
(
    2,
    'DEV-ECU-02',
    '2026-03-06 10:14:35',
    'P0606',
    'ECU Processor Fault',
    'Engine ECU',
    'Critical',
    'ECU processor checksum mismatch detected under elevated thermal load.'
),

(
    3,
    'DEV-IGN-03',
    '2026-03-06 11:06:10',
    'P0302',
    'Cylinder 2 Misfire Detected',
    'Ignition Control Module',
    'Warning',
    'Cylinder 2 combustion instability detected during ignition quality inspection.'
),
(
    3,
    'DEV-IGN-03',
    '2026-03-06 11:09:25',
    'P0302',
    'Cylinder 2 Misfire Detected',
    'Ignition Control Module',
    'Warning',
    'RPM fluctuation and rough combustion pattern repeated within short interval.'
),
(
    3,
    'DEV-IGN-03',
    '2026-03-06 11:12:00',
    'P0302',
    'Cylinder 2 Misfire Detected',
    'Ignition Control Module',
    'Critical',
    'Ignition coil or spark plug degradation suspected from repeated cylinder 2 misfire event.'
);

SELECT log_id, inspection_id, dtc_code, error_timestamp
FROM error_logs
ORDER BY inspection_id, error_timestamp;
