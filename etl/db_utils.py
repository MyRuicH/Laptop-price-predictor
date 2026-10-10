import os
import polars as pl
import psycopg2 as psg

from dotenv import load_dotenv
from common.logger import get_logger


load_dotenv()

logger = get_logger("etl.db_utils")


def get_connection():
    return psg.connect(
        host="localhost",
        port=5433,
        dbname="laptops",
        user="myruich",
        password=os.getenv("DB_PASSWORD"),
    )


def load_table_data(table_name: str="raw_laptops") -> pl.DataFrame:
    """Завантаження даних з таблиці та пертворення і запис у DataFrame"""
    logger.info(f"Loading data from table: {table_name}")
    conn = get_connection()
    try:
        df = pl.read_database(f"SELECT * FROM {table_name}", connection=conn)
    except Exception as e:
        logger.error(f"Invalod attempting to load data from the table `{table_name}`: {e}")
        raise
    finally:
        conn.close()
    
    logger.info(f"Data loaded from table: {table_name} successfully.")
    return df


def save_to_table(df: pl.DataFrame, table_name: str="laptops_clean") -> None:
    """Збереження даних у таблицю із вхідного DataFrame"""
    logger.info(f"Saving data to table: {table_name}")
    conn = get_connection()
    cur = conn.cursor()
    try:
        for row in df.iter_rows(named=True):
            cur.execute("""
            INSERT INTO laptops_clean(raw_id, company, type_name, inches, screen_width, screen_height, is_ips, is_touchscreen, cpu_brand, cpu_model, 
            cpu_ghz, ram_gb, storage_type, storage_gb, gpu_brand, gpu_model, opSys, weight, price)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["raw_id"], row["company"], row["type_name"], row["inches"], row["screen_width"], row["screen_height"],
                row["is_ips"], row["is_touchscreen"], row["cpu_brand"], row["cpu_model"], row["cpu_ghz"],
                row["ram_gb"], row["storage_type"], row["storage_gb"], row["gpu_brand"], row["gpu_model"],
                row["opSys"], row["weight"], row["price"]
            ))
    except Exception as e:
        logger.error(f"Invalid attempting to save data to the table `{table_name}`: {e}")
        raise
    finally:
        conn.commit()
        cur.close()
        conn.close()

    logger.info(f"Data saved to table: {table_name} successfully.")

