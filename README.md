# Laptop-price-predictor

Навчальна система прогнозування ціни ноутбука: PostgreSQL → Polars ETL →
scikit-learn → FastAPI. Backend використовує готові артефакти з ml/models;
для запуску API перенавчання не потрібне. HTML/CSS/JS frontend поки порожні.

## Запуск із власним паролем

Потрібен Docker Desktop із Docker Compose. Налаштування наведені в .env.example:
скопіюйте їх у власний .env та заповніть DB_PASSWORD. Готовий .env не перезаписуйте.

З кореня репозиторію, для нового локального Compose-проєкту:

~~~powershell
docker compose --env-file .env --project-name laptop-price-predictor-local up -d --build --wait
~~~

Контейнери називаються db_postgres і server_backend, порти за замовчуванням —
5433 та 8000. Перед запуском вони не повинні бути зайняті іншим Compose-проєктом.
Назва проєкту вище створює окрему БД з актуальним init.sql та вашим паролем;
попередні volume залишаються збереженими. Якщо цей проєкт уже існує, його volume
використовується повторно.

init.sql виконується лише на порожньому volume. Зміни POSTGRES_PASSWORD у Compose
не змінюють пароль ролі в уже створеній БД; для старої БД потрібне окреме узгодження
схеми та облікових даних. Команди видалення volume для звичайного запуску не потрібні.

## Специфікація та API

- Swagger UI: [localhost:8000/docs/](http://localhost:8000/docs/).
- Ручна специфікація: [openapi.yaml](openapi.yaml), доступна через /openapi.yaml.
- /openapi.json повертає той самий контракт у JSON; /redoc використовує той самий YAML.
- Описані всі 12 шляхів / 13 операцій: API, health, HTML, статика та документація.
- Після редагування YAML перезапустіть backend; у Docker файл копіюється в образ,
  тому потрібен повторний запуск із --build.

POST /api/predict повертає predicted_price, price_low, price_high, model_name, warnings.
Значення категорій беріть із GET /api/options. GET /api/model-info містить метрики,
GET /health — стан моделі й БД; degraded також має HTTP 200.

ОС необов'язкова: null, порожній рядок або відсутність поля означають імпутацію.
No OS — ноутбук без ОС; для чинної моделі сервер використовує історичну категорію
Unknown без зміни артефактів. Ціна в історії прогнозів зберігається в
pridicted_price JSONB як JSON-число; це окремо від назви поля HTTP-відповіді.
MAPE у test_metrics — частка: для відсотків помножте на 100.
Dummy навчається без логарифмування цілі. Валюта датасету, прогнозу та його меж —
українська гривня (UAH), підтверджена користувачем; конвертація не виконується.

## Postman і перевірки

Імпортуйте [postman-collection.json](postman-collection.json) у Postman.
У Collection → Variables змініть baseUrl та характеристики ноутбука за потреби.
Є 25 запитів із JavaScript-перевірками: успішні прогнози, необов'язкова ОС,
помилки 422, документація, статика та 404. Числові й булеві змінні в JSON
використовуються без лапок. Колекція не потребує пароля БД чи API-автентифікації.
Успішні прогнози додають записи в БД; запускайте колекцію в заданому порядку,
щоб порівняти No OS з історичною категорією. lastPrediction і
legacyNoOsPrediction оновлюються тестами. Для навмисної перевірки відмови БД
встановіть expectedHealthStatus=degraded; сама колекція БД не зупиняє.

Для локальних перевірок потрібен Python 3.12.6 і активований venv:

~~~powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python tests/check_collection_http.py
Get-Content -Raw tests/smoke_containers.py | docker exec -i server_backend python -X utf8 -
~~~

check_collection_http.py виконує HTTP-запити з колекції та перевіряє відповіді
за OpenAPI-схемами, але не виконує Postman JavaScript. JS-перевірки виконує Postman
або Newman. Контейнерний smoke-тест додатково перевіряє реальний JSONB INSERT і DDL;
він теж додає чотири прогнози в історію. Локальні unittest-тести не читають .env.
