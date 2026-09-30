import os
import polars as pl
import psycopg2 as psg

from dotenv import load_dotenv


load_dotenv()

def get_connection():
    return psg.connect(
        host="localhost",
        port=5433,
        dbname="laptops",
        user="myruich",
        password=os.getenv("DB_PASSWORD"),
    )

def load_table_data(table_name: str) -> pl.DataFrame:
    conn = get_connection()
    df = pl.read_database(f"SELECT * FROM {table_name}", connection=conn)
    conn.close()
    return df
