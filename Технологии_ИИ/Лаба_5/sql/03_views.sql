-- =============================================================================
-- Аналитические представления (витрины) поверх схемы «звезда».
-- Используются панелью мониторинга, базой знаний и модулем оптимизации.
-- =============================================================================
SET search_path TO dwh;

-- Денормализованное наблюдение: факт + все измерения (источник для выгрузок)
CREATE OR REPLACE VIEW v_observation AS
SELECT f.udi, f.product_id, q.class_code, e.inventory_no, t.tool_cycle_no, f.cycle_pos,
       f.air_temp_k, f.process_temp_k, f.rot_speed_rpm, f.torque_nm, f.tool_wear_min,
       f.temp_diff_k, f.power_w, f.power_margin_w, f.wear_torque, f.osf_margin,
       f.machine_failure, ft.failure_code AS failure_mode,
       f.is_outlier_speed, f.is_outlier_torque, b.loaded_at
FROM fact_observation f
JOIN dim_quality_class q USING (class_key)
JOIN dim_equipment     e USING (equipment_key)
JOIN dim_tool          t USING (tool_key)
JOIN dim_failure_type ft USING (failure_type_key)
JOIN dim_batch         b USING (batch_key);

-- Доля отказов по классу качества (лаба 2, табл. 6)
CREATE OR REPLACE VIEW v_failure_rate_by_class AS
SELECT q.class_code, count(*) AS observations,
       sum(f.machine_failure) AS failures,
       round(100.0 * avg(f.machine_failure), 2) AS failure_rate_pct,
       sum(f.twf) AS twf, sum(f.hdf) AS hdf, sum(f.pwf) AS pwf, sum(f.osf) AS osf
FROM fact_observation f
JOIN dim_quality_class q USING (class_key)
GROUP BY q.class_code, q.class_rank
ORDER BY q.class_rank;

-- Сводка по циклам инструмента (для планирования замен генетическим алгоритмом)
CREATE OR REPLACE VIEW v_tool_cycle_summary AS
SELECT t.tool_cycle_no, t.products_processed, t.wear_at_end_min, t.end_reason,
       sum(f.machine_failure) AS failures_in_cycle,
       max(f.wear_torque)     AS max_wear_torque,
       min(f.osf_margin)      AS min_osf_margin
FROM fact_observation f
JOIN dim_tool t USING (tool_key)
GROUP BY t.tool_cycle_no, t.products_processed, t.wear_at_end_min, t.end_reason;

-- Проверка продукционных правил: условия вычисляются по порогам, хранящимся
-- в измерениях (а не в коде), и сравниваются с фактическими метками.
CREATE OR REPLACE VIEW v_rule_check AS
SELECT f.udi,
       (f.temp_diff_k < e.hdf_temp_diff_min_k AND f.rot_speed_rpm < e.hdf_speed_max_rpm)::int AS rule_hdf,
       (f.power_w < e.power_min_w OR f.power_w > e.power_max_w)::int                        AS rule_pwf,
       (f.wear_torque > q.osf_limit)::int                                                    AS rule_osf,
       (f.tool_wear_min BETWEEN e.twf_wear_min_min AND e.twf_wear_max_min)::int              AS rule_twf,
       f.hdf, f.pwf, f.osf, f.twf
FROM fact_observation f
JOIN dim_equipment     e USING (equipment_key)
JOIN dim_quality_class q USING (class_key);
