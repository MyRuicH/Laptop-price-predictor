import polars as pl

from etl.db_utils import load_table_data
from common.logger import get_logger


RAW_TABLE = "raw_laptops"
THRESHOLD = 3.0

logger = get_logger("etl.clean")


def load_raw_data() -> pl.DataFrame:
   logger.info("Loading row data from `raw_laptops` ")
   df = load_table_data(RAW_TABLE)
   logger.info(f"{df.height} rows were successfully loaded")
   return df


def drop_duplicates(df: pl.DataFrame) -> pl.DataFrame:
   """Видаляє повні дублікати рядків"""

   logger.info("Drop duplicates function call")
   before = df.height
   df = df.unique(keep="any")
   after = df.height

   logger.warning(f"{before - after} duplicates were deleted")
   return df


def handle_missing_values(df: pl.DataFrame) -> pl.DataFrame:
    """Обробка пропусків: дропнути рядки без ціни (цільова змінна),
    заповнити чи дропнути пропуски в інших колонках"""

    logger.info("handle_missing_values function call")
    before = df.height
    df = df.filter(
       pl.all_horizontal(pl.col(["company", "type_name", "cpu", "gpu", "price"]).is_not_null()) # тілки для чисто текстових, поєднаних через bool
        )
    
    after = df.height
    logger.warning(f"{before - after} rows were deleted due to missing critical fields")

    df = df.with_columns([
        pl.col("opsys").fill_null("Without OS"),
        pl.col("screen_resolution").fill_null(
            pl.col("screen_resolution").mode().first().over("inches")
        )
    ])
    
    return df


def strip_units(df: pl.DataFrame) -> pl.DataFrame:
    """Прибирає одиниці виміру з текстових полів:
    '8GB' -> 8, '1.37kg' -> 1.37 (поки як проміжний крок, 
    без повного парсингу — тільки очистка рядків)"""

    logger.info("Strip units function call")

    df = df.with_columns([
        pl.col("ram").str.replace_all("GB", "").cast(pl.Int32).alias("ram_gb"), # replace_all - змінює всі входження
        pl.col("weight").str.replace_all("kg", "").cast(pl.Float64)
    ])

    logger.info("The measurment units for text rows (ram, memory, weight) were successfully changed")
    return df


def remove_outliers(df: pl.DataFrame, column: str, method: str = "iqr") -> pl.DataFrame:
    """Видалення викидів за ціною (IQR або z-score)"""

    logger.info("Remove outliers function call")
    before = df.height

    if method.lower().strip() == "iqr":
        q1 = pl.col(column).quantile(0.25)
        q3 = pl.col(column).quantile(0.75)
        iqr = q3 - q1

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        df = df.filter(pl.col(column).is_between(lower_bound=lower_bound, upper_bound=upper_bound))
      
    else:                    # z-score
        df = df.filter(
        ((pl.col(column) - pl.col(column).mean()) / pl.col(column).std()).abs() <= THRESHOLD)

    after = df.height

    logger.warning(f"{before - after} outliers were deleted by {method.upper().strip()}")
    return df


def run_cleaning_pipeline() -> pl.DataFrame:
    """Головна функція: викликає всі кроки по черзі, повертає очищений df"""

    logger.info("run_cleaning_pipeline function call")
    df = load_raw_data()
    df = drop_duplicates(df)
    df = handle_missing_values(df)
    df = strip_units(df)
    cleaned_df = remove_outliers(df, "price")

    logger.info(f"Cleanup complete. {cleaned_df.height} rows remained")

    return cleaned_df

df = run_cleaning_pipeline()
print(df)

