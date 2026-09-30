import os

import polars as pl
import psycopg2 as psg

from dotenv import load_dotenv


load_dotenv()

CSV_PATH = "data/raw/laptopData.csv"

conn = psg.connect(
    host="localhost",
    port=5433,
    dbname="laptops",
    user="myruich",
    password=os.getenv("DB_PASSWORD")
)

cur = conn.cursor()

df = pl.read_csv(CSV_PATH, null_values=["?"])

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

conn.commit()
cur.close()
conn.close()

print(f"  {len(df)} rows have been successfully loaded into `raw_laptops` ")
