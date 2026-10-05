-- =============================================================================
-- Проверка целостности и полноты загруженных данных (лаба 6, шаг 4).
-- Запуск: psql -d ai_project -f sql/05_checks.sql
-- =============================================================================
SET search_path TO dwh;

\echo '--- 1. Количество записей по таблицам'
SELECT 'dim_equipment' AS table_name, count(*) AS count FROM dim_equipment
UNION ALL SELECT 'dim_quality_class',  count(*) FROM dim_quality_class
UNION ALL SELECT 'dim_tool',           count(*) FROM dim_tool
UNION ALL SELECT 'dim_failure_type',   count(*) FROM dim_failure_type
UNION ALL SELECT 'dim_batch',          count(*) FROM dim_batch
UNION ALL SELECT 'fact_observation',   count(*) FROM fact_observation
UNION ALL SELECT 'fact_failure_event', count(*) FROM fact_failure_event;

\echo '--- 2. Строки фактов без соответствующей строки измерения (orphaned rows)'
SELECT 'equipment' AS dim, count(*) AS orphans FROM fact_observation f
       LEFT JOIN dim_equipment d USING (equipment_key) WHERE d.equipment_key IS NULL
UNION ALL SELECT 'quality_class', count(*) FROM fact_observation f
       LEFT JOIN dim_quality_class d USING (class_key) WHERE d.class_key IS NULL
UNION ALL SELECT 'tool', count(*) FROM fact_observation f
       LEFT JOIN dim_tool d USING (tool_key) WHERE d.tool_key IS NULL
UNION ALL SELECT 'failure_type', count(*) FROM fact_observation f
       LEFT JOIN dim_failure_type d USING (failure_type_key) WHERE d.failure_type_key IS NULL
UNION ALL SELECT 'batch', count(*) FROM fact_observation f
       LEFT JOIN dim_batch d USING (batch_key) WHERE d.batch_key IS NULL
UNION ALL SELECT 'event -> observation', count(*) FROM fact_failure_event e
       LEFT JOIN fact_observation o USING (udi) WHERE o.udi IS NULL;

\echo '--- 3. NULL в ключевых полях'
SELECT count(*) FILTER (WHERE udi IS NULL)              AS udi_null,
       count(*) FILTER (WHERE class_key IS NULL)        AS class_null,
       count(*) FILTER (WHERE tool_key IS NULL)         AS tool_null,
       count(*) FILTER (WHERE failure_type_key IS NULL) AS failure_type_null
FROM fact_observation;

\echo '--- 4. Базовая статистика показаний датчиков'
SELECT round(avg(air_temp_k), 2)     AS avg_air,    round(stddev(air_temp_k), 2)    AS sd_air,
       round(avg(rot_speed_rpm), 2)  AS avg_speed,  round(stddev(rot_speed_rpm), 2) AS sd_speed,
       round(avg(torque_nm), 2)      AS avg_torque, min(torque_nm) AS min_torque, max(torque_nm) AS max_torque,
       round(avg(tool_wear_min), 2)  AS avg_wear,   max(tool_wear_min) AS max_wear
FROM fact_observation;

\echo '--- 5. Доля отказов по классам качества (сравнить с лабой 2, табл. 6)'
SELECT * FROM v_failure_rate_by_class;

\echo '--- 6. Согласованность двух таблиц фактов'
SELECT (SELECT sum(twf + hdf + pwf + osf + rnf_ref + failure_type_unknown) FROM fact_observation) AS flags_in_observation,
       (SELECT count(*) FROM fact_failure_event)                                                   AS events,
       (SELECT sum(machine_failure) FROM fact_observation)                                         AS failures,
       (SELECT count(*) FROM fact_failure_event WHERE is_primary = 1)                              AS primary_events;

\echo '--- 7. Проверка продукционных правил по порогам из измерений (лаба 2, табл. 7)'
SELECT 'HDF' AS rule, sum(rule_hdf) AS fired, sum(hdf) AS labels, sum(rule_hdf * hdf) AS matched FROM v_rule_check
UNION ALL SELECT 'PWF', sum(rule_pwf), sum(pwf), sum(rule_pwf * pwf) FROM v_rule_check
UNION ALL SELECT 'OSF', sum(rule_osf), sum(osf), sum(rule_osf * osf) FROM v_rule_check
UNION ALL SELECT 'TWF', sum(rule_twf), sum(twf), sum(rule_twf * twf) FROM v_rule_check;
