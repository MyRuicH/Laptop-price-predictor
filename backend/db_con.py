"""
backend/db_con.py — шар збереження даних (PostgreSQL).

Навмисно маленький і окремий від main.py: HTTP-шар не повинен знати, як
влаштоване з'єднання з БД (принцип розділення відповідальності). Якщо завтра
замінити psycopg2 на пул з'єднань чи ORM, змінюється лише цей файл.

Головне правило модуля: збій БД НІКОЛИ не ламає основну функцію сервісу.
Прогноз ціни не залежить від бази, тому логування прогнозів (побічна дія)
у разі помилки лише пише повідомлення в лог і не кидає виняток.
"""

import os

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json

from etl.db_utils import get_connection
from common.logger import get_logger


# Локально змінні беруться з .env, у Docker їх передає docker-compose
# (load_dotenv не перезаписує вже задані змінні середовища).
load_dotenv()

logger = get_logger("backend.db")


def save_prediction(input_data: dict, predicted_price: float) -> None:
    """Записує один прогноз у таблицю model_predictions.

    Викликається у фоні вже ПІСЛЯ відправки відповіді користувачу
    (див. BackgroundTasks у main.py), тому вона не затримує відповідь, а
    помилки не поширюються нагору.
    """
    conn = None
    try:
        conn = get_connection(connect_timeout=3)  # швидко відпрацьовує, якщо БД недоступна
        # `with conn` відкриває транзакцію: commit при успіху, rollback при помилці.
        # (Сам по собі `with conn` з'єднання НЕ закриває, тому close() у finally.)
        with conn, conn.cursor() as cur:
            # Запит параметризований (%s): значення передаються окремо від тексту SQL,
            # тож SQL-ін'єкція неможлива, навіть якщо в input_data прийде шкідливий рядок.
            cur.execute(
                "INSERT INTO model_predictions (input_json, predicted_price) VALUES (%s, %s)",
                (Json(input_data), predicted_price),   # Json() -> колонка типу JSONB
            )
        logger.info(f"Prediction saved to model_predictions (price={predicted_price:.0f}).")
    except Exception as exc:
        # Навмисно ловимо все: це побічна дія, її збій не повинен ламати сервіс.
        logger.error(f"Failed to save prediction: {exc}")
    finally:
        if conn is not None:
            conn.close()


def check_db() -> bool:
    """Чи відповідає БД. Використовується в /health; повертає bool, а не кидає виняток."""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception as exc:
        logger.warning(f"Database health check failed: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()
            