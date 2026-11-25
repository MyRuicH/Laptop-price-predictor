CREATE TABLE IF NOT EXISTS raw_laptops (
    raw_laps_id      SERIAL     PRIMARY KEY,
    company          VARCHAR(50),
    type_name        VARCHAR(50),
    inches           VARCHAR(10),        
    screen_resolution TEXT,
    cpu              TEXT,
    ram              VARCHAR(20),
    memory           TEXT,
    gpu              TEXT,
    opsys            VARCHAR(30),
    weight           VARCHAR(20),
    price            NUMERIC
);

CREATE TABLE IF NOT EXISTS laptops_clean (
    clean_laps_id   SERIAL      PRIMARY KEY,
    raw_id          INTEGER     REFERENCES raw_laptops(raw_laps_id),
    company         VARCHAR(50),
    type_name       VARCHAR(50),
    inches          REAL,
    screen_width    INTEGER,
    screen_height   INTEGER,
    is_ips          BOOLEAN,
    is_touchscreen  BOOLEAN,
    cpu_brand       VARCHAR(20),
    cpu_model       VARCHAR(100),
    cpu_ghz         REAL,
    ram_gb          INTEGER,
    storage_type    VARCHAR(20),
    storage_gb      DOUBLE PRECISION,
    gpu_brand       VARCHAR(20),
    gpu_model       VARCHAR(100),
    opsys           VARCHAR(30),
    weight          DOUBLE PRECISION,
    price           NUMERIC,
    cpu_gpu_pair    TEXT
);

CREATE TABLE IF NOT EXISTS model_predictions (
    predict_id      SERIAL      PRIMARY KEY,
    input_json      JSONB,
    pridicted_price JSONB,
    created_at      TIMESTAMP   DEFAULT NOW()
);
