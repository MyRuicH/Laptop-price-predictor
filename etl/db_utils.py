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
    """Завантаження данних з таблиці та пертворення і запис у DataFrame"""
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
