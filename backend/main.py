"""
backend/main.py — HTTP-шар застосунку (точка входу FastAPI).

Архітектура: три шари з односпрямованими залежностями.

    main.py (HTTP: маршрути, коди відповідей)
        |--> model_loader.py (бізнес-логіка: перевірка, підготовка ознак, прогноз)
        |--> db.py           (збереження: PostgreSQL)
    schemas.py — «контракт»: які дані ходять між клієнтом і сервером

Запуск (з кореня проєкту):
    uvicorn backend.main:app --reload
Документація API (Swagger): http://localhost:8000/docs
"""

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.db_con import check_db, save_prediction
from backend.model_loader import InvalidInputError, ModelService
from backend.schemas import HealthOut, LaptopInput, OptionsOut, PredictionOut
from common.logger import get_logger

logger = get_logger("backend.main")

API_VERSION = "1.0.0"


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", REPO_ROOT / "frontend"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Виконується один раз: код до yield — при старті, після yield — при зупинці.

    Модель завантажується тут, а не на кожен запит і не на рівні модуля:
      * швидкість: joblib.load відбувається один раз, запити лише викликають predict;
      * fail fast: якщо файлу моделі немає або він пошкоджений, застосунок
        НЕ стартує (процес завершується з помилкою), і Docker/оркестратор бачить
        збій одразу, а не після першого запиту користувача;
      * тестованість: імпорт модуля main.py не вимагає наявності моделі на диску.
    """
    logger.info(f"Starting API v{API_VERSION}.")
    app.state.service = ModelService.load()
    yield
    logger.info("Shutting down API.")


app = FastAPI(
    title="Laptop Price Predictor API",
    description="Прогноз ціни ноутбука за його характеристиками (HistGradientBoosting).",
    version=API_VERSION,
    lifespan=lifespan,
)


def get_service(request: Request) -> ModelService:
    """Віддає сервіс моделі для обробника запиту.

    Обробники не лізуть у глобальні змінні, а ОТРИМУЮТЬ залежність через
    Depends(). Практична користь: у тестах її можна підмінити заглушкою
    (app.dependency_overrides[get_service] = ...) без патчингу коду.
    """
    return request.app.state.service


# Annotated-псевдонім, щоб не повторювати Depends(...) у кожному обробнику.
ServiceDep = Annotated[ModelService, Depends(get_service)]


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Пише в лог метод, шлях, код відповіді й тривалість кожного запиту.

    /health пропускається, бо Docker опитує його кожні кілька секунд і засмітив би лог.
    """
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path != "/health":
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({elapsed_ms:.0f} ms)")
    return response


def _to_detail(error: str) -> dict:
    """«company: невідоме значення 'X'» -> {'loc': ['body', 'company'], 'msg': ..., 'type': ...}."""
    field, _, message = error.partition(":")
    return {
        "loc": ["body", field.strip()],
        "msg": message.strip() or error,
        "type": "invalid_option",
    }


@app.exception_handler(InvalidInputError)
async def invalid_input_handler(request: Request, exc: InvalidInputError) -> JSONResponse:
    """Невідома категорія -> HTTP 422 у тому Ж форматі, що й помилки Pydantic.

    Єдиний формат помилок (`detail` — список об'єктів loc/msg/type) спрощує
    фронтенд: один код показує помилки під відповідними полями форми, незалежно
    від того, який шар їх виявив.
    """
    return JSONResponse(status_code=422, content={"detail": [_to_detail(e) for e in exc.errors]})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Остання сітка безпеки для непередбачених помилок -> HTTP 500.

    Повний трейсбек іде тільки в лог; клієнт отримує загальне повідомлення.
    Внутрішні деталі (шляхи, назви колонок, тексти винятків) допомагають
    зловмиснику, тому назовні їх не віддаємо.
    """
    logger.error(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Внутрішня помилка сервера"})


# APIRouter групує пов'язані маршрути з спільним префіксом і тегом (для /docs).
router = APIRouter(prefix="/api", tags=["api"])


@router.post("/predict", response_model=PredictionOut)
def predict(payload: LaptopInput, background: BackgroundTasks, service: ServiceDep) -> PredictionOut:
    """Головний маршрут: характеристики ноутбука -> прогноз ціни з діапазоном.

    Обробник «тонкий» і лише оркеструє:
      1 payload уже перевірений Pydantic до входу в функцію (типи, межі);
      2 service.predict_laptop — уся логіка моделі (перевірка за довідниками,
         підготовка ознак, прогноз, діапазон);
      3 збереження в БД — у фоні.

    """
    result = service.predict_laptop(payload)
    background.add_task(save_prediction, payload.model_dump(), result.predicted_price)
    return result


@router.get("/options", response_model=OptionsOut)
def get_options(service: ServiceDep) -> OptionsOut:
    """Довідники для побудови форми (списки брендів, діапазони чисел).

    Форма будується з цієї відповіді, а не зашита в HTML. Тому після перенавчання
    з новими категоріями фронтенд правити не треба: джерело правди одне (options.json).
    """
    return OptionsOut(**service.options_payload())


@router.get("/model-info")
def get_model_info(service: ServiceDep) -> dict:
    """Метрики моделі для сторінки «Аналітика» (дані з metrics.json)."""
    return service.model_info()


app.include_router(router)


@app.get("/health", response_model=HealthOut, tags=["service"])
def health(request: Request) -> HealthOut:
    """Перевірка стану для Docker healthcheck і ручної діагностики.

    Розрізняємо «сервіс працює» і «залежності працюють»: прогноз не потребує БД,
    тому недоступна БД дає status="degraded" (працюємо зі зниженою функціональністю),
    а не помилку. HTTP-код лишається 200: процес живий і запити обслуговує.
    """
    model_loaded = hasattr(request.app.state, "service")
    db_ok = check_db()
    status = "ok" if (model_loaded and db_ok) else "degraded"
    return HealthOut(status=status, model_loaded=model_loaded, db_ok=db_ok)



# Один сервер віддає і API, і сторінки: це «same-origin», тож CORS-налаштування
# не потрібні, а розгортання — один контейнер.
def _page(name: str) -> FileResponse:
    """Віддає HTML-сторінку з теки frontend/ або 404, якщо її ще не створено."""
    path = FRONTEND_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Сторінку {name} не знайдено")
    return FileResponse(path)


@app.get("/", include_in_schema=False)
def index_page() -> FileResponse:
    """Головна сторінка з формою прогнозу."""
    return _page("index.html")


@app.get("/analytics", include_in_schema=False)
def analytics_page() -> FileResponse:
    """Сторінка з графіками й метриками моделі."""
    return _page("analytics.html")


# Статика (CSS, JS, графіки), fronted-чатсина ще не раелізована. Монтується на /static, а не на «/»: монтування на
# корінь перехоплювало б будь-який шлях і «з'їдало» маршрути API. 
# Хоч fronted-чатсина ще не раелізована - backend усе одно стартує й працює.
if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
else:
    logger.warning(f"Frontend directory not found: {FRONTEND_DIR}. Pages and /static are disabled.")
