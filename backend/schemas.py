from pydantic import BaseModel, ConfigDict, Field, model_validator

from common.logger import get_logger

logger = get_logger("backend.schemas")


class LaptopInput(BaseModel):
    model_config = ConfigDict(
       
        extra="forbid",
      
        str_strip_whitespace=True,
               
    )

    company: str = Field(min_length=1, description="Бренд, напр. Lenovo")
    type_name: str = Field(min_length=1, description="Тип: Notebook, Gaming, Ultrabook ...")
    opsys: str = Field(min_length=1, description="Операційна система")
    storage_type: str = Field(min_length=1, description="SSD / HDD / Hybrid / Flash Storage")
    cpu_model: str = Field(min_length=1, description="Модель процесора, напр. Core i5 7200U")
    gpu_model: str = Field(min_length=1, description="Модель відеокарти, напр. HD Graphics 620")
 
    inches: float = Field(ge=10, le=20, description="Діагональ екрана, дюйми")
    screen_width: int = Field(ge=1366, le=3840, description="Ширина екрана, px")
    cpu_ghz: float = Field(ge=0.8, le=4.0, description="Частота процесора, ГГц")
    ram_gb: int = Field(ge=1, le=64, description="Оперативна пам'ять, ГБ")
    storage_gb: int = Field(ge=8, le=2000, description="Обсяг накопичувача, ГБ")
    weight: float = Field(ge=0.5, le=6.0, description="Вага, кг")

   
    is_ips: bool = False
    is_touchscreen: bool = False

  
    screen_height: int | None = Field(
        default=None, ge=768, le=2160,
        description="Висота екрана, px (модель не використовує, лише для перевірки)",
    )

    @model_validator(mode="after")
    def check_resolution(self) -> "LaptopInput":
        if self.screen_height is not None and self.screen_height > self.screen_width:
            logger.warning(
                f"Rejected resolution {self.screen_width}x{self.screen_height}: "
                "height is greater than width."
            )
            raise ValueError("screen_height не може бути більшим за screen_width")
        return self


class PredictionOut(BaseModel):
   
    predicted_price: float = Field(description="Прогнозована ціна")
    price_low: float = Field(description="Нижня межа типового діапазону")
    price_high: float = Field(description="Верхня межа типового діапазону")
    model_name: str = Field(description="Яка модель дала прогноз")
 
    warnings: list[str] = Field(default_factory=list)


class OptionsOut(BaseModel):
    """Відповідь /api/options: з неї фронтенд будує випадні списки."""

    dropdowns: dict[str, list]
    cpu_models: list[str]
    gpu_models: list[str]
    numeric_ranges: dict[str, dict[str, float]]


class HealthOut(BaseModel):
    """Відповідь /health для Docker healthcheck і швидкої діагностики."""

    status: str
    model_loaded: bool
    db_ok: bool | None = None  # None = перевірку БД не виконували
