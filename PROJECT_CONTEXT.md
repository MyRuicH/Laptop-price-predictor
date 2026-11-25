# PROJECT_CONTEXT — Laptop Price Predictor

> Станом на 2026-11-25. Звірено з файлами, локальними артефактами, тестами та реальним Docker-запуском.
> Оригінальний .env не читався, не виводився й не редагувався. Моделі не перенавчалися; усі п’ять файлів ml/models залишилися незмінними.

## 0. Правила та достовірність

Спілкування — українською, коміти — англійською. Логи переважно англійською, коментарі й docstring переважно українською. Користувач — студент; пояснювати причини рішень.

- [F] — встановлено з актуальних файлів або Git.
- [V] — додатково перевірено виконанням 2026-11-25.
- [H] — історичні відомості попереднього контексту, не відтворені цим аудитом.
- [P] — рекомендація або майбутня робота.

Непозначені описи коду — факти з поточних файлів. Не відкривати оригінальний .env і не виводити секрети через Compose config/inspect/logs. Для тестів використовувались явно вказаний .env.example і випадковий пароль у пам’яті процесу. Інструкції запуску нижче призначені користувачу; під час цього завдання власний пароль користувача не використовувався.

## 1. Мета та стан

Курсова: наскрізна система PostgreSQL → Polars ETL → регресійна ML-модель → FastAPI → вебсторінки. Завдання — відтворюваний навчальний проєкт, а не оцінювання актуальної ринкової ціни.

- Seed, ETL, навчання, CV/тюнінг, оцінювання та експорт реалізовані; готові дані, модель, JSON, CSV й PNG є.
- Backend незалежний від ETL/Polars, успішно працював у Docker з реальним записом прогнозів у JSONB [V].
- Ручний openapi.yaml — джерело контракту для Swagger UI на /docs/, ReDoc і /openapi.json. Описані 12 шляхів / 13 операцій.
- postman-collection.json: 25 запитів, 26 змінних колекції та JavaScript-перевірки. Пароля БД у колекції немає.
- 13 локальних unittest-тестів, 25 HTTP-запитів колекції з перевіркою OpenAPI-схем, контейнерний HTTP/SQL smoke та pip check — успішні [V].
- Frontend: index.html, analytics.html, script.js, style.css мають 0 байтів; шість PNG готові. README тепер містить запуск і перевірки. ER-діаграми та записки немає.
- Тестові контейнери db_postgres/server_backend успішно мали running/healthy, потім **зупинені й видалені**, щоб звільнити порти й імена. Тестовий volume збережений, основні volume не змінені [V]. Push не виконувався.

## 2. Середовище та залежності

Windows, PowerShell; venv у корені, Python **3.12.6**. Docker — **python:3.12.6-slim**, PostgreSQL — postgres:16.

backend/requirements.txt містить коректні == та uvicorn[standard]: FastAPI 0.142.4, Uvicorn 0.54.0, scikit-learn 1.9.1, pandas 3.0.6, NumPy 2.5.3, SciPy 1.18.1, PyArrow 26.0.0, psycopg2-binary 2.9.13, python-dotenv 1.2.4, Pydantic 2.13.5, joblib 1.6.0, threadpoolctl 3.7.0, PyYAML 6.0.4. Збірка і pip check успішні [V]. NumPy/SciPy потребують Python >=3.12.

Локальний driver — psycopg2 2.9.13; Docker використовує binary-дистрибутив. Polars 2.0.0 потрібен ETL/локальним регресіям, але відсутній у backend-образі. requirements-dev.txt включає runtime dependencies, Polars 2.0.0 та openapi-spec-validator 0.8.5. EDA/evaluate також потребують matplotlib/seaborn/Jupyter; окремого повного lock-файлу для них немає.

common/logger.py: INFO у консоль, DEBUG у LOG_DIR/<name>.log, ротація 2 000 000 байтів, три резервні копії. LOG_DIR із середовища, типово logs/. .gitignore ігнорує *.log.

## 3. Файли й архітектура

~~~text
openapi.yaml                         # ручний контракт, копіюється в образ
postman-collection.json               # Postman v2.1, змінні, приклади, тести
requirements-dev.txt
.env.example / docker-compose.yml
README.md / PROJECT_CONTEXT.md
backend/
  main.py                            # HTTP, документація, статика
  api_docs.py                        # читання YAML один раз, safe_load
  schemas.py / model_loader.py
  db_con.py                          # власна get_connection, без ETL
  Dockerfile / requirements.txt
common/logger.py
 db/init.sql / db/seed.py
etl/clean.py / features.py / db_utils.py / etl_main.py
data/raw/RawLaptopData.csv
data/processed/feature_set.parquet
ml/train.py / evaluate.py / export_options.py
ml/notebooks/eda.ipynb
ml/models/{best_model.joblib,metrics.json,options.json,
           test_predictions.parquet,evaluation_summary.json}
frontend/{index.html,analytics.html,script.js,style.css,img/}
docs/analytics_graphs/                # 5 PNG
 docs/evaluation/                     # 6 PNG + 3 CSV
 tests/test_backend_regressions.py
 tests/test_openapi_contract.py
 tests/check_collection_http.py
 tests/smoke_containers.py
~~~

CSV → db.seed → raw_laptops → etl.clean/features/etl_main → parquet + laptops_clean → ml.train/export_options. Оцінювання створює PNG/CSV та summary. Backend читає готові артефакти, перевіряє запит, робить прогноз і зберігає історію у фоні. etl/load_to_db.py та backend/db.py відсутні; фактичні модулі — etl.etl_main/etl.db_utils та backend.db_con.

## 4. Дані та SQL

[V] CSV — **1303 записи**; checkpoint — **1216 × 21**; тест — **244 × 19**, тобто 17 ознак та actual/predicted_price. За поділу цих 1216 рядків train мав би 972 рядки; актуальний склад старої основної БД не перевірявся.

У checkpoint перейменовано лише колонку ОС на opsys, значення рядків не перекодовані. Вхідний CSV збережений як оригінальне джерело з початковими назвами заголовків; seed мапить їх на SQL-поля. Аномалії лишилися: inches до 35.6, weight 0.0002–11.1, storage_gb 8–2000. У evaluate.py ціна підписана як «грн», але підтвердження валюти чи конвертації немає. Kaggle Laptop Price Dataset та приблизний вік 2017–2018 років — історичні відомості/припущення [H].

| Таблиця | Поточний init.sql |
|---|---|
| raw_laptops | PK raw_laps_id SERIAL, текстові сирі поля, opsys VARCHAR(30), price NUMERIC |
| laptops_clean | PK clean_laps_id, FK raw_id → raw_laptops; inches/cpu_ghz REAL; storage_gb/weight DOUBLE PRECISION; RAM/роздільність INTEGER; прапорці BOOLEAN; price NUMERIC; opsys VARCHAR(30), cpu_gpu_pair TEXT |
| model_predictions | PK predict_id SERIAL, input_json JSONB, **pridicted_price JSONB**, created_at TIMESTAMP DEFAULT NOW() |

Назву pridicted_price та тип JSONB явно підтвердив користувач. Backend обгортає ціну в Json(predicted_price), тобто зберігає JSON-число. HTTP-відповідь має назву predicted_price. Колонка ОС у виконуваному коді/SQL/checkpoint — opsys.

Новий init.sql перевірений на чистому тестовому volume: таблиці, FK, cpu_gpu_pair, числові поля та JSONB INSERT працюють [V]. Старі основні volume не мігрувалися. init.sql запускається лише при першій ініціалізації порожнього volume; змінні POSTGRES_PASSWORD не змінюють пароль уже створеної ролі.

## 5. ETL

- db.seed читає CSV відносно кореня, бере DB_* із середовища. Підключення та INSERT виконуються на рівні модуля; не імпортувати для аудиту. Повторний запуск додає рядки без UPSERT.
- etl.db_utils має власну get_connection(connect_timeout=5), окремі DB_* без DATABASE_URL; SELECT * без ORDER BY. save_to_table робить INSERT по рядках у жорстко визначену laptops_clean; повторний ETL її не очищає, commit стоїть у finally.
- Очищення: дедуплікація без raw_laps_id, видалення критичних пропусків, opsys → No OS, мода роздільності за inches і ваги за type_name, одиниці RAM/ваги, цінові викиди 1.5 IQR. Фізичних фільтрів inches/weight немає.
- Парсинг екрана, CPU/GPU, першого накопичувача; **1 TB = 1000 GB**. Другий накопичувач не агрегується. CPU/GPU-моделі вже strip_chars().
- No OS — канонічна категорія; різний регістр і пробіли нормалізуються. Unknown лишається окремою категорією; macOS/Mac OS X окремі.
- cpu_gpu_pair = '<cpu_model> | <gpu_model>'; raw_laps_id → raw_id. opsys не перейменовується. etl_main.run_etl_pipline спершу пише parquet, потім БД; parquet сам по собі не доводить успішного INSERT.

## 6. Модель та оцінювання

ml.train: target price; виключаються конкретні id/raw_id/clean_laps_id та screen_height. Split 0.2, random_state=67. Числові — SimpleImputer(median) + StandardScaler; категоріальні — мода + OneHotEncoder(infrequent_if_exist, min_frequency=10, sparse_output=False). TransformedTargetRegressor(log1p/expm1), Dummy без логарифма. KFold 5/shuffle/seed67; тюнінг RF/HGB 30 ітерацій за neg_root_mean_squared_error. SMOKE=1 **не реалізований**.

Залишений баг: best_name/best_search обираються за CV, але best_model жорстко присвоюється hgb_search.best_estimator_. Зараз HGB справді кращий, артефакт і назва узгоджені; при перемозі RF код був би некоректний. SQL/unique не гарантують порядок; split-індекси не зберігаються, тому seed сам по собі не гарантує відтворення історичних train/test.

| Модель | CV RMSE до тюнінгу, mean ± sample std |
|---|---|
| Dummy | 31880.39 ± 2336.74 |
| LinearRegression | 17280.35 ± 2294.39 |
| RandomForest | 13692.40 ± 816.16 |
| HistGradientBoosting | 12735.62 ± 952.91 |

Тюнінг: HGB 12559.52; RF 13130.07. HGB: lr=0.05, max_iter=1000, max_leaf_nodes=8, min_samples_leaf=8, l2=5.0. RF: 600 дерев, depth20, leaf1, max_features0.5.

[V] Тест: **RMSE 11485.9658, MAE 7778.7253, R² 0.868239, MAPE 12.7985%**; частка помилки ≤10% — 45.082%, ≤20% — 78.6885%. Середня ціна 59575.89, медіана 53226.72. Середня actual-predicted = +1414.56. mape у metrics.json — частка 0.12798496. Перерахунок збігається з JSON; модель відтворює всі 244 прогнози з max diff=0.0.

17 ознак: company, type_name, inches, screen_width, is_ips, is_touchscreen, cpu_brand, cpu_model, cpu_ghz, ram_gb, storage_type, storage_gb, gpu_brand, gpu_model, opsys, weight, cpu_gpu_pair. Ключ categorial_columns у metrics.json має історичну друкарську помилку; не змінювати ізольовано.

evaluate.py: шість PNG і три CSV в docs/evaluation та frontend/img, summary в ml/models. Копії PNG побайтово однакові [V]. CLI --models-dir/--out-dir/--skip-importance. bootstrap_ci існує, але main її не викликає; у summary bootstrap CI немає. У help залишилася стара згадка backend/static/img.

EDA: 25 клітинок, після очищення чотирьох outputs зі старими назвами ОС — 6 code-клітинок зі збереженими результатами. Код використовує opsys; ноутбук не перезапускався. Залишилися текстові плейсхолдери та старі згадки has_dual_storage/weight_kg/handle_unknown='ignore'.

## 7. Довідники та ОС

options.json: dropdowns, 90 CPU, 97 GPU, 249 пар CPU/GPU, numeric_ranges. error_ratio_quantiles вже є: q10=0.7840776376455708, q90=1.276815323496533. Активний interval_source — quantiles, приблизно −21.6%/+27.7%; це емпіричний діапазон, не гарантія.

export_options.compute_error_ratio_quantiles завантажує модель, читає БД, повторює split і виконує cross_val_predict на train. Він **навчає клони на CV-фолдах**, хоча не перезаписує best_model.joblib; тому експорт також не запускався за заборони перенавчання.

opsys необов’язкова: відсутність/null/порожній/пробільний рядок → None → NaN → навчальна мода. No OS означає відсутню ОС; для чинного незміненого артефакту API переводить її на історичний Unknown. No OS додається в API-довідник без мутації options.json. Попередження про пропущену ОС формується **один раз**, поза циклами [V].

## 8. Backend та документація

LaptopInput: extra=forbid, strip пробілів. Межі: inches10–20, screen_width1366–3840, cpu_ghz0.8–4.0, ram_gb1–64, storage_gb8–2000, weight0.5–6.0. Прапорці типово False; screen_height optional768–2160 і не більший за ширину; модель його не використовує. Бренди CPU/GPU та пару обчислює сервер.

ModelService.load читає model/metrics/options один раз; MODEL_DIR або repo/ml/models. Довідникові помилки → 422; numeric_ranges/нетиповий RAM/невідома пара дають warnings. Прогноз і межі округлюються до сотень.

| Шлях | Реалізація |
|---|---|
| POST /api/predict | валідація, прогноз, BackgroundTasks для історії |
| GET /api/options | довідники форми |
| GET /api/model-info | test/CV/tuning/interval_source/n_features |
| GET /health | ok/degraded, model_loaded/db_ok; HTTP200 навіть без БД |
| GET /, /analytics | FileResponse на порожні HTML; 404 лише якщо файлу немає |
| GET/HEAD /static/{asset_path} | ресурси frontend, PNG готові |
| GET /docs | 307 на /docs/ |
| GET /docs/ | Swagger UI, джерело /openapi.yaml |
| GET /redoc | ReDoc, те саме джерело |
| GET /openapi.yaml | ручний файл із кореня |
| GET /openapi.json | той самий YAML, перетворений на JSON |

backend.api_docs використовує PyYAML safe_load та кеш на один документ. lifespan перевіряє наявність YAML перед моделлю; app.openapi перевизначено, автогенерація FastAPI не є джерелом UI. Після зміни YAML потрібен restart, а в Docker — rebuild. UI-бібліотеки Swagger/ReDoc завантажуються браузером із CDN. У браузері UI в цьому кроці не перевірявся; перевірені його HTML та URL YAML.

InvalidInputError → 422 detail:[{loc,msg,type}], інші Exception → 500 із загальним текстом. Обробники основних маршрутів sync, lifespan/middleware async. Exception-handler не пише traceback, хоча docstring обіцяє його — залишена некритична неточність.

backend.db_con.get_connection напряму викликає psycopg2.connect з DB_* і типовим таймаутом3с, без ETL/Polars/DATABASE_URL. Нове з’єднання на виклик. /health виконує SELECT1; INSERT перевіряється smoke-тестом. Основні помилки збереження перехоплюються; close у finally окремим try не захищений.

## 9. Docker, конфігурація та запуск

Образ копіює common/backend/frontend/openapi.yaml, артефакти монтуються read-only. .dockerignore виключає .env, ETL/ML/data/db/tests і кеші. Команда Uvicorn отримує UVICORN_HOST/PORT із Compose.

.env.example містить DB_HOST/PORT для локальних скриптів (localhost/5433), DB_NAME/USER, порожній DB_PASSWORD; DOCKER_DB_HOST/PORT (postgres/5432); BACKEND_HOST_PORT/HOST/PORT; шляхи MODEL_DIR/FRONTEND_DIR/LOG_DIR/DB_INIT_SQL_PATH/BACKEND_BUILD_CONTEXT/BACKEND_DOCKERFILE та відповідні DOCKER_* шляхи. Оригінальний .env користувач заповнює сам.

Compose: postgres/backend, db_postgres/server_backend, course_net, postgres_data; depends_on service_healthy. Healthcheck PostgreSQL — pg_isready, backend — urllib на /health. Модель/frontend read-only, logs writable, init.sql read-only. Backend healthcheck перевіряє HTTP, не JSON degraded; його Docker timeout8с, таймаут підключення БД3с.

Тестовий проєкт laptop-price-predictor-smoke перевірений і завершений без -v. Volume laptop-price-predictor-smoke_postgres_data збережений; основні laptop-price-predictor_postgres_data/course_db_postgres_data не змінювалися.

Для запуску користувачем із власним .env та новою БД з актуальним init.sql:

~~~powershell
docker compose --env-file .env --project-name laptop-price-predictor-local up -d --build --wait
~~~

Новий project name ізолює volume від старої схеми й тестового пароля. Повторний запуск того самого project name повторно використовує його volume. Не видаляти дані старої БД без прямої вказівки користувача.

## 10. Перевірки та Postman

- 8 регресій backend/ETL + 5 тестів контракту = **13 unittest**, успішні [V]. Включають паритет240 прийнятих рядків; 4 історичні рядки відхиляються через вагу/діагональ.
- OpenAPI3.1 перевірений openapi-spec-validator; поля/межі запиту звірені з Pydantic, всі поточні маршрути описані.
- **25 HTTP-запитів** з postman-collection.json виконані tests/check_collection_http.py: статуси, типи вмісту, JSON Schema, byte-wise YAML, тотожність JSON/YAML, redirect, No OS і warnings [V].
- Newman не встановлювався: дозвіл на завантаження відхилено. JavaScript Postman-тестів не виконувався в Newman; їх виконує Postman/Collection Runner. HTTP-helper цього не підміняє.
- Контейнерний smoke перевірив JSONB number/4 записи, raw/clean FK та типи в rollback-транзакції, відсутність ETL/Polars, Python3.12.6, health/API/PNG/422; pip check успішний [V].
- SHA-256 усіх п’яти ml/models збігаються з початком робіт. Seed/повний ETL/train/export/evaluate та міграція основних volume не виконувалися.

~~~powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python tests/check_collection_http.py
Get-Content -Raw tests/smoke_containers.py | docker exec -i server_backend python -X utf8 -
~~~

У Postman імпортувати колекцію, змінити Collection Variables за потреби, запускати в порядку папок. baseUrl типовий http://localhost:8000; числа/булеві шаблонізовані без лапок; expectedHealthStatus типово ok; lastPrediction/legacyNoOsPrediction заповнюються JS-тестами. Успішні запити створюють історію прогнозів. 500 не провокується колекцією; для нього потрібна керована ін’єкція збою.

## 11. Git і межі змін

До цих робіт HEAD був 92ef8d9 feat(backend); ML — 52c323c feat(ml). На початку вже були зміни model_loader/schemas/compose, видалення трьох docs/json_schema_examples/*.ndjson та untracked PROJECT_CONTEXT.md. Вони не відновлювалися поверх користувача. Локальний коміт цього кроку об’єднує виправлення Docker/БД/ОС, ручну специфікацію, Postman, тести й документацію; push не виконується. .env до коміту не додається.

## 12. Залишені завдання та історія

[P] Frontend; ER/записка; підтвердження валюти; виправлення вибору estimator у train; фізичні аномалії даних; стабільність порядку й split; повторні seed/ETL без дублювання; решта тексту EDA/help/docstrings. Користувач визначив їх некритичними для поточного обсягу. Зміни даних/перенавчання — тільки за окремою вказівкою.

[H] До виправлень ETL був тест RMSE13380/MAE9327/R²0.826/MAPE16.5%, але склад тесту відрізнявся; напряму не порівнювати. Старий bootstrap RMSE CI[9935;13046] не є полем поточного summary. Історичні експерименти пропусків давали RMSE без ОС11946, без ваги14747, без обох15302, без RAM14143, без cpu_ghz13955 при базовому11486; цього разу не відтворювалися. learning_curve й ансамбль HGB+RF не реалізовані.
