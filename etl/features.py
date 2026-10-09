import polars as pl

from etl.clean import run_cleaning_pipeline
from common.logger import get_logger


logger = get_logger("etl.features")


def get_cleaned_data() -> pl.DataFrame:
    """Безпечне отримання очищених даних із clean.py."""
    try:
        return run_cleaning_pipeline()
    except Exception as e:
        logger.error(f"Error while running cleaning pipeline: {e}")
        raise


def parse_screen_resolution(df: pl.DataFrame) -> pl.DataFrame:
    """ Парсинг стовпця Роздільна Здатність Екрану.
        Приклад: 'IPS Panel Full HD 1920x1080' ->
                screen_width: 1920, screen_height: 1080,
                is_ips: True, is_touchscreen: False"""

    logger.info("Parsing screen resolution and features...")

    groups = pl.col("screen_resolution").str.extract_groups(r"(?P<screen_width>\d+)x(?P<screen_height>\d+)")

    df = df.with_columns([
        groups.struct.field("screen_width").cast(pl.Int32).alias("screen_width"),
        groups.struct.field("screen_height").cast(pl.Int32).alias("screen_height"),

        pl.col("screen_resolution").str.contains(r"(?i)IPS").alias("is_ips"),
        pl.col("screen_resolution").str.contains(r"(?i)Touchscreen").alias("is_touchscreen")
        
    ])
    df = df.drop("screen_resolution")

    logger.debug(f"Parsed screen resolution and features: {df.head()}")
    return df
    

def parse_cpu(df: pl.DataFrame) -> pl.DataFrame:
    """ Парсинг стовпця Процесор
        Приклад: 'Intel Core i5 2.3GHz' ->
                cpu_brand: 'Intel', cpu_model: 'Core i5', cpu_ghz: 2.3"""

    logger.info("Parsing CPU information...")

    groups = pl.col("cpu").str.extract_groups(r"(?P<cpu_brand>\w+)\s+(?P<cpu_model>[\w\s]+)\s+(?P<cpu_ghz>[\d\.]+)GHz")

    df = df.with_columns([
        groups.struct.field("cpu_brand").alias("cpu_brand"),
        groups.struct.field("cpu_model").alias("cpu_model"),
        groups.struct.field("cpu_ghz").cast(pl.Float32).alias("cpu_ghz")
        
    ])
    df = df.drop("cpu")

    logger.debug(f"Parsed CPU information: {df.head()}")
    return df


def parse_memory(df: pl.DataFrame) -> pl.DataFrame:
    """ Парсинг стовпця Постійна пам'ять
        Приклад: '256GB SSD' або '1TB HDD + 256GB SSD' ->
                storage_type: 'SSD'/'HDD'/'Hybrid', storage_gb: 256"""

    logger.info("Parsing memory information...")

    groups = pl.col("memory").str.extract_groups(r"(?P<storage_gb>\d+)(?P<storage_type>GB|TB|SSD|HDD|Hybrid)")

    df = df.with_columns([
        groups.struct.field("storage_gb").cast(pl.Int32).alias("storage_gb"),
        groups.struct.field("storage_type").alias("storage_type")
    ])
    df = df.drop("memory")

    logger.debug(f"Parsed memory information: {df.head()}")
    return df


def parse_gpu(df: pl.DataFrame) -> pl.DataFrame:
    """ Парсинг стовпця Відеокарти 
        Приклад: 'Nvidia GTX 1050' -> gpu_brand: 'Nvidia', gpu_model: 'GTX 1050'"""

    logger.info("Parsing GPU information...")

    groups = pl.col("gpu").str.extract_groups(r"(?P<gpu_brand>\w+)\s+(?P<gpu_model>[\w\s]+)")

    df = df.with_columns([
        groups.struct.field("gpu_brand").alias("gpu_brand"),
        groups.struct.field("gpu_model").alias("gpu_model")
    ])
    df = df.drop("gpu")

    logger.debug(f"Parsed GPU information: {df.head()}")
    return df


def cast_numeric_types(df: pl.DataFrame) -> pl.DataFrame:
    """Приведення простих числових полів до правильного типу"""

    logger.info("Casting numeric columns...")
    df = df.with_columns([
        pl.col("inches").cast(pl.Float32),
    ])
    return df


def normalize_categoricals(df: pl.DataFrame) -> pl.DataFrame:
    """Нормалізація значень для стовпців company, type_name, opsys, cpu_brand, gpu_brand"""

    logger.info("Encoding categorical features...")
    
    known_type_names = ["Notebook", "Ultrabook", "Gaming", "2 in 1 Convertible", "Workstation", "Netbook", "Unknown"]
    known_opsys = ["Windows 10", "Windows 10 S", "Windows 7", "Linux", "macOS", "Mac OS X", "Chrome OS", "No Os", "Unknown"]
    known_cpu_brands = ["Intel", "AMD", "Unknown"]
    known_gpu_brands = ["Nvidia", "AMD", "Intel", "Unknown"]

    tn_cat = pl.Enum(known_type_names)
    os_cat = pl.Enum(known_opsys)
    cpb_cat = pl.Enum(known_cpu_brands)
    gpb_cat = pl.Enum(known_gpu_brands)

    df = df.with_columns([
        pl.col("company").cast(pl.Categorical, strict=False).fill_null("Unknown"),
        pl.col("type_name").cast(tn_cat, strict=False).fill_null("Unknown"),
        pl.col("opsys").cast(os_cat, strict=False).fill_null("Unknown"),
        pl.col("cpu_brand").cast(cpb_cat, strict=False).fill_null("Unknown"),
        pl.col("gpu_brand").cast(gpb_cat, strict=False).fill_null("Unknown"),
    ])

    logger.debug(f"Encoded categorical features: {df.head()}")
    return df


def build_feature_set(cleaned_df: pl.DataFrame) -> pl.DataFrame:
    """Головна функція: викликає всі parse_* та encode_categoricals по черзі"""

    logger.info("Building feature set...")
    df = parse_screen_resolution(cleaned_df)
    df = parse_cpu(df)
    df = parse_memory(df)
    df = parse_gpu(df)
    df = cast_numeric_types(df)
    parsed_df = normalize_categoricals(df)
    
    df = df.rename({"raw_laps_id": "raw_id", "opsys": "opSys"})

    logger.info("Feature set built successfully.")
    return parsed_df
