-- =============================================================================
-- Хранилище данных системы предиктивного обслуживания (лабораторная работа 5)
-- Вариант 10. СУБД PostgreSQL 14+. Схема «звезда» с двумя таблицами фактов
-- и общими (согласованными) измерениями - созвездие фактов.
--
-- Запуск:  psql -d ai_project -f 01_create_schema.sql
-- Скрипт идемпотентен: схема dwh пересоздаётся целиком.
-- =============================================================================

DROP SCHEMA IF EXISTS dwh CASCADE;
CREATE SCHEMA dwh;
SET search_path TO dwh;

-- -----------------------------------------------------------------------------
-- Измерения
-- -----------------------------------------------------------------------------

-- Единица оборудования. Фрейм-экземпляр из лабы 1: паспортные данные и пороги
-- продукционных правил, заданные для типа оборудования.
CREATE TABLE dim_equipment (
    equipment_key        SMALLINT     PRIMARY KEY,
    inventory_no         VARCHAR(20)  NOT NULL UNIQUE,          -- бизнес-ключ
    equipment_name       VARCHAR(100) NOT NULL,
    equipment_type       VARCHAR(50)  NOT NULL,
    nominal_power_w      NUMERIC(7,1) NOT NULL,
    power_min_w          NUMERIC(7,1) NOT NULL,                 -- порог правила PWF
    power_max_w          NUMERIC(7,1) NOT NULL,                 -- порог правила PWF
    hdf_temp_diff_min_k  NUMERIC(4,1) NOT NULL,                 -- порог правила HDF
    hdf_speed_max_rpm    INTEGER      NOT NULL,                 -- порог правила HDF
    twf_wear_min_min     SMALLINT     NOT NULL,                 -- зона правила TWF
    twf_wear_max_min     SMALLINT     NOT NULL,
    data_source          VARCHAR(100) NOT NULL,
    CHECK (power_min_w < power_max_w),
    CHECK (twf_wear_min_min < twf_wear_max_min)
);

-- Класс качества изделия. Фрейм-прототип: значения слотов, наследуемые
-- изделиями класса (порог перегрузки, шаг износа инструмента).
CREATE TABLE dim_quality_class (
    class_key            SMALLINT     PRIMARY KEY,
    class_code           CHAR(1)      NOT NULL UNIQUE CHECK (class_code IN ('L', 'M', 'H')),
    class_name           VARCHAR(30)  NOT NULL,
    class_rank           SMALLINT     NOT NULL UNIQUE,          -- порядок L < M < H
    osf_limit            INTEGER      NOT NULL CHECK (osf_limit > 0),     -- мин·Н·м
    wear_step_min        SMALLINT     NOT NULL CHECK (wear_step_min > 0), -- мин за изделие
    nominal_share_pct    NUMERIC(4,1) NOT NULL                -- доля по документации
);

-- Цикл эксплуатации инструмента: от установки нового инструмента (износ 0)
-- до его замены. Выявлен в лабе 4 по сбросам износа.
CREATE TABLE dim_tool (
    tool_key             SMALLINT     PRIMARY KEY,
    tool_cycle_no        SMALLINT     NOT NULL UNIQUE,          -- бизнес-ключ
    first_udi            INTEGER      NOT NULL,
    last_udi             INTEGER      NOT NULL,
    products_processed   SMALLINT     NOT NULL CHECK (products_processed > 0),
    wear_at_end_min      SMALLINT     NOT NULL CHECK (wear_at_end_min >= 0),
    end_reason           VARCHAR(12)  NOT NULL
                         CHECK (end_reason IN ('PLANNED', 'TWF', 'IN_SERVICE')),
    CHECK (first_udi <= last_udi)
);

-- Тип отказа: справочник распознаваемых системой состояний и правил.
CREATE TABLE dim_failure_type (
    failure_type_key     SMALLINT     PRIMARY KEY,
    failure_code         VARCHAR(8)   NOT NULL UNIQUE,          -- бизнес-ключ
    failure_name         VARCHAR(60)  NOT NULL,
    rule_condition       VARCHAR(120),
    recommended_action   VARCHAR(120),
    severity_rank        SMALLINT     NOT NULL,                 -- 0 - нет отказа
    is_target            BOOLEAN      NOT NULL                  -- входит в целевую переменную
);

-- Партия загрузки: обеспечивает неизменность и прослеживаемость данных
-- (свойства хранилища): каждая строка фактов знает, из какого файла и когда загружена.
CREATE TABLE dim_batch (
    batch_key            INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name          VARCHAR(100) NOT NULL,
    source_file          VARCHAR(200) NOT NULL,
    source_md5           CHAR(32)     NOT NULL,
    etl_script           VARCHAR(100) NOT NULL,
    loaded_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    rows_loaded          INTEGER,
    UNIQUE (source_md5)                                         -- один файл - одна загрузка
);

-- -----------------------------------------------------------------------------
-- Таблица фактов 1: наблюдение за станком при обработке одного изделия.
-- Зерно: одно изделие (одна строка исходного набора).
-- -----------------------------------------------------------------------------
CREATE TABLE fact_observation (
    observation_key      INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- вырожденные измерения (идентификаторы без собственной таблицы)
    udi                  INTEGER      NOT NULL UNIQUE,
    product_id           VARCHAR(10)  NOT NULL UNIQUE,
    product_serial       INTEGER      NOT NULL,
    -- внешние ключи измерений
    equipment_key        SMALLINT     NOT NULL REFERENCES dim_equipment,
    class_key            SMALLINT     NOT NULL REFERENCES dim_quality_class,
    tool_key             SMALLINT     NOT NULL REFERENCES dim_tool,
    failure_type_key     SMALLINT     NOT NULL REFERENCES dim_failure_type,  -- failure_mode
    batch_key            INTEGER      NOT NULL REFERENCES dim_batch,
    -- меры: показания датчиков
    air_temp_k           NUMERIC(5,1) NOT NULL CHECK (air_temp_k BETWEEN 273 AND 343),
    process_temp_k       NUMERIC(5,1) NOT NULL CHECK (process_temp_k BETWEEN 273 AND 373),
    rot_speed_rpm        INTEGER      NOT NULL CHECK (rot_speed_rpm BETWEEN 1 AND 5000),
    torque_nm            NUMERIC(5,1) NOT NULL CHECK (torque_nm BETWEEN 0 AND 150),
    tool_wear_min        SMALLINT     NOT NULL CHECK (tool_wear_min BETWEEN 0 AND 400),
    -- меры: производные признаки (лаба 4)
    temp_diff_k          NUMERIC(4,1) NOT NULL,
    power_w              NUMERIC(8,1) NOT NULL,
    power_margin_w       NUMERIC(8,1) NOT NULL,
    wear_torque          NUMERIC(8,1) NOT NULL,
    osf_margin           NUMERIC(8,1) NOT NULL,
    cycle_pos            SMALLINT     NOT NULL CHECK (cycle_pos > 0),
    -- меры: метки и флаги (0/1, аддитивны - сумма даёт число случаев)
    machine_failure      SMALLINT     NOT NULL CHECK (machine_failure IN (0, 1)),
    twf                  SMALLINT     NOT NULL CHECK (twf IN (0, 1)),
    hdf                  SMALLINT     NOT NULL CHECK (hdf IN (0, 1)),
    pwf                  SMALLINT     NOT NULL CHECK (pwf IN (0, 1)),
    osf                  SMALLINT     NOT NULL CHECK (osf IN (0, 1)),
    rnf_ref              SMALLINT     NOT NULL CHECK (rnf_ref IN (0, 1)),
    n_failure_modes      SMALLINT     NOT NULL CHECK (n_failure_modes BETWEEN 0 AND 4),
    failure_type_unknown SMALLINT     NOT NULL CHECK (failure_type_unknown IN (0, 1)),
    is_outlier_speed     SMALLINT     NOT NULL CHECK (is_outlier_speed IN (0, 1)),
    is_outlier_torque    SMALLINT     NOT NULL CHECK (is_outlier_torque IN (0, 1)),
    -- согласованность разметки, установленная в лабе 4
    CHECK (machine_failure = GREATEST(twf, hdf, pwf, osf, failure_type_unknown)),
    CHECK (process_temp_k >= air_temp_k)
);

-- -----------------------------------------------------------------------------
-- Таблица фактов 2: событие отказа (один подтип отказа в одном наблюдении).
-- Зерно: пара «наблюдение - тип отказа». Нужна потому, что в одном наблюдении
-- может быть несколько подтипов (23 записи); без неё многометочную разметку
-- пришлось бы хранить только плоскими флагами.
-- -----------------------------------------------------------------------------
CREATE TABLE fact_failure_event (
    failure_event_key    INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    udi                  INTEGER      NOT NULL REFERENCES fact_observation (udi),
    equipment_key        SMALLINT     NOT NULL REFERENCES dim_equipment,
    class_key            SMALLINT     NOT NULL REFERENCES dim_quality_class,
    tool_key             SMALLINT     NOT NULL REFERENCES dim_tool,
    failure_type_key     SMALLINT     NOT NULL REFERENCES dim_failure_type,
    batch_key            INTEGER      NOT NULL REFERENCES dim_batch,
    is_primary           SMALLINT     NOT NULL CHECK (is_primary IN (0, 1)),  -- совпадает с failure_mode
    event_count          SMALLINT     NOT NULL DEFAULT 1 CHECK (event_count = 1),
    UNIQUE (udi, failure_type_key)
);

-- -----------------------------------------------------------------------------
-- Описания объектов (видны в pgAdmin и \d+)
-- -----------------------------------------------------------------------------
COMMENT ON SCHEMA dwh IS 'Хранилище данных системы предиктивного обслуживания (вариант 10)';
COMMENT ON TABLE dim_equipment IS 'Измерение: единица оборудования (фрейм-экземпляр, пороги правил)';
COMMENT ON TABLE dim_quality_class IS 'Измерение: класс качества изделия (фрейм-прототип)';
COMMENT ON TABLE dim_tool IS 'Измерение: цикл эксплуатации режущего инструмента';
COMMENT ON TABLE dim_failure_type IS 'Измерение: тип отказа и соответствующее продукционное правило';
COMMENT ON TABLE dim_batch IS 'Измерение: партия загрузки (прослеживаемость)';
COMMENT ON TABLE fact_observation IS 'Факт: наблюдение за станком при обработке одного изделия';
COMMENT ON TABLE fact_failure_event IS 'Факт: событие отказа (подтип отказа в наблюдении)';
COMMENT ON COLUMN fact_observation.failure_type_key IS 'failure_mode: подтип с наивысшим приоритетом PWF > OSF > HDF > TWF';
COMMENT ON COLUMN fact_observation.power_margin_w IS 'Запас до границы 3500-9000 Вт; < 0 - условие PWF выполнено';
COMMENT ON COLUMN fact_observation.osf_margin IS 'osf_limit - wear_torque; < 0 - условие OSF выполнено';
