-- =============================================================================
-- Индексы хранилища (лаба 6, шаг 5). Создаются после загрузки данных.
-- Уникальные индексы на udi, product_id, бизнес-ключи измерений и
-- (udi, failure_type_key) уже созданы ограничениями UNIQUE в лабе 5.
-- =============================================================================
SET search_path TO dwh;

-- Внешние ключи таблиц фактов: соединения с измерениями и фильтры по ним.
-- PostgreSQL, в отличие от ряда СУБД, не индексирует внешние ключи автоматически.
CREATE INDEX IF NOT EXISTS idx_obs_tool         ON fact_observation (tool_key);          -- история цикла инструмента (СИ-2)
CREATE INDEX IF NOT EXISTS idx_obs_failure_type ON fact_observation (failure_type_key);  -- выборка по типу отказа
CREATE INDEX IF NOT EXISTS idx_event_type       ON fact_failure_event (failure_type_key);
CREATE INDEX IF NOT EXISTS idx_event_tool       ON fact_failure_event (tool_key);

-- Составной индекс для частого фильтра «класс качества + отказ» (панель мониторинга)
CREATE INDEX IF NOT EXISTS idx_obs_class_failure ON fact_observation (class_key, machine_failure);

-- Частичный индекс: только записи с отказом (3,4 % таблицы) - журнал отказов
CREATE INDEX IF NOT EXISTS idx_obs_failures ON fact_observation (udi) WHERE machine_failure = 1;

-- Диапазонный поиск по износу: кандидаты на замену инструмента (зона правила TWF)
CREATE INDEX IF NOT EXISTS idx_obs_wear ON fact_observation (tool_wear_min);

ANALYZE fact_observation;
ANALYZE fact_failure_event;
