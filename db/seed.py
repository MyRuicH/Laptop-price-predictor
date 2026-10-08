import os

import polars as pl
import psycopg2 as psg

from dotenv import load_dotenv

from common.logger import get_logger


load_dotenv()

logger = get_logger("db.seed")

CSV_PATH = "data/raw/RawLaptopData.csv"

conn = psg.connect(
    host="localhost",
    port=5433,
    dbname="laptops",
    user="myruich",
    password=os.getenv("DB_PASSWORD")
)

cur = conn.cursor()

df = pl.read_csv(CSV_PATH, null_values=["?"])

try:
    for row in df.iter_rows(named=True):
        
            cur.execute(
            """
            INSERT INTO raw_laptops(company, type_name, inches, screen_resolution, cpu, ram, memory, gpu, opsys, weight, price)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """ ,
            (  
                row["Company"], row["TypeName"], row["Inches"], row["ScreenResolution"],
                row["Cpu"], row["Ram"], row["Memory"], row["Gpu"],
                row["OpSys"], row["Weight"], row["Price"],  
            ),
            )

except Exception as e:
    logger.error(f"Invalid attempting to insert data to the table `{CSV_PATH}`: {e}")
    raise
finally:
    conn.commit()
    cur.close()
    conn.close()

logger.info(f"Data from {CSV_PATH} has been successfully seeded into the raw_laptops table.")
