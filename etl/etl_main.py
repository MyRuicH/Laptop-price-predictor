from common.logger import get_logger
from etl.clean import run_cleaning_pipeline
from etl.features import build_feature_set
from etl.db_utils import save_to_table


def run_etl_pipline() -> None:
    """Оркестрація процесів отримання, очищення, парсингу та збереження данних для подальшого 
        розбиття на вибірки та подання моделям"""
    
    logger = get_logger("etl.etl_main")
    logger.info("Starting ETL pipeline...")

    # Крок 1: Виклик функції очищення сириз даних
    logger.info("Running cleaning pipeline...")
    cleaned_data = run_cleaning_pipeline()
    logger.info("Cleaning pipeline completed.")

    # Крок 2: Виклик функції формування парсингу данних та їх нормалізації 
    logger.info("Building feature set...")
    feature_set = build_feature_set(cleaned_data)
    logger.info("Feature set built successfully.")

    # Кро 2_5: Збереження оброблених данни у data/processed/ як .parquet - щоб швидко перезавантажувати під час розробки моделі, 
        # не ганяючи щоразу весь пайплайн
    feature_set.write_parquet("data/processed/feature_set.parquet", compression="snappy")
    logger.info("Feature set written as parquet seccessfully.")

    # Крок 3: Збереження оброблених данх у таблицю laptops_clean 
    logger.info("Saving feature set to the database...")
    save_to_table(feature_set, table_name="laptops_clean")
    
    logger.info("ETL pipeline completed successfully.")


if __name__ == "__main__":
    run_etl_pipline()
