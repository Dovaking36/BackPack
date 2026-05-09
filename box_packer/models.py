from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, List, Dict, Tuple, Any
from enum import Enum

# Вспомогательные типы и перечисления
class Rotation(str, Enum):
    """Допустимые повороты коробки в горизонтальной плоскости."""
    R0 = "0"      # без поворота
    R90 = "90"    # поворот на 90°

Position = Tuple[float, float, float]

# 1. Модель контейнера
class Container(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {"id": "V1", "width": 120.0, "depth": 80.0, "height": 100.0}
    })
    id: str = Field(..., description="Уникальный идентификатор контейнера, например 'V1'")
    width: float = Field(..., gt=0, description="Ширина, см")
    depth: float = Field(..., gt=0, description="Глубина, см")
    height: float = Field(..., gt=0, description="Высота, см")
    priority: Optional[int] = Field(default=None, ge=0)

    @property
    def volume(self) -> float:
        return self.width * self.depth * self.height

# 2. Модель коробки
class Box(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "P1", "width": 30.0, "depth": 20.0, "height": 15.0,
            "weight": 2.5, "items_per_box": 10, "max_stack_layers": None
        }
    })
    id: str = Field(..., description="Идентификатор типа коробки, например 'P1'")
    width: float = Field(..., gt=0, description="Ширина коробки, см")
    depth: float = Field(..., gt=0, description="Глубина коробки, см")
    height: float = Field(..., gt=0, description="Высота коробки, см")
    weight: float = Field(..., ge=0, description="Вес одной коробки, кг")
    items_per_box: int = Field(..., ge=1, description="Количество изделий в одной коробке")
    max_stack_layers: Optional[int] = Field(
        default=None, ge=1,
        description="Максимальное количество слоёв (None — без ограничений)"
    )
    allow_rotation: bool = Field(default=True, description="Разрешить поворот на 90°")

    @property
    def volume(self) -> float:
        return self.width * self.depth * self.height

    @field_validator("max_stack_layers")
    @classmethod
    def check_max_stack_layers(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("max_stack_layers должно быть положительным целым или None")
        return v

# 3. Размещение одной коробки
class Placement(BaseModel):
    box_id: str = Field(..., description="Тип коробки")
    quantity: int = Field(..., ge=1, description="Количество коробок в данной позиции")
    layer: int = Field(..., ge=1, description="Номер слоя (1 – самый нижний)")
    position: Position = Field(..., description="Координаты (x, y, z) угла коробки")
    rotation: Rotation = Field(default=Rotation.R0, description="Применённый поворот")

# 4. Использование одного контейнера
class ContainerUsage(BaseModel):
    container_id: str
    fill_ratio: float = Field(..., ge=0.0, le=1.0, description="Коэффициент заполнения объёма")
    placements: List[Placement] = Field(default_factory=list)
    total_weight: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def compute_total_weight_if_missing(self) -> "ContainerUsage":
        return self

# 5. Результат упаковки
class PackingResult(BaseModel):
    feasible: bool = Field(..., description="True – весь заказ помещается в контейнеры")
    containers_used: List[ContainerUsage] = Field(default_factory=list)
    unplaced_boxes: List[Dict[str, int]] = Field(
        default_factory=list,
        description="Список типов коробок и их количества, которые не удалось разместить"
    )
    total_fill_ratio: float = Field(..., ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list, description="Предупреждения")

    @model_validator(mode="after")
    def check_consistency(self) -> "PackingResult":
        if self.feasible and self.unplaced_boxes:
            raise ValueError("Если feasible=True, то unplaced_boxes должен быть пуст")
        if not self.feasible and not self.unplaced_boxes:
            raise ValueError("Если feasible=False, необходимо указать хотя бы одну неразмещённую коробку")
        return self

# 6. Входной заказ
class Order(BaseModel):
    items: Dict[str, int] = Field(
        ..., description="Словарь {box_id: количество_изделий}."
    )

    @field_validator("items")
    @classmethod
    def positive_quantities(cls, v: Dict[str, int]) -> Dict[str, int]:
        for box_id, qty in v.items():
            if qty < 0:
                raise ValueError(f"Количество изделий для {box_id} не может быть отрицательным")
        return v

    def to_boxes_count(self, boxes: Dict[str, Box]) -> Dict[str, int]:
        result = {}
        for box_id, item_qty in self.items.items():
            if box_id not in boxes:
                raise KeyError(f"Коробка {box_id} не найдена в списке доступных типов")
            items_per_box = boxes[box_id].items_per_box
            if item_qty % items_per_box != 0:
                raise ValueError(f"Количество изделий {item_qty} для {box_id} не кратно items_per_box={items_per_box}")
            result[box_id] = item_qty // items_per_box
        return result

# 7. Конфигурация решателя
class SolverConfig(BaseModel):
    fill_threshold: float = Field(default=0.9, ge=0.0, le=1.0, description="Минимальный целевой коэффициент заполнения")
    use_rotation: bool = Field(default=True, description="Разрешить поворот коробок")
    allow_light_on_heavy: bool = Field(default=False, description="Разрешить ставить лёгкие коробки на тяжёлые")
    algorithm: str = Field(default="ffd_local", description="Алгоритм: 'ffd', 'ffd_local', 'ilp_pulp', 'ilp_ortools'")
    time_limit_seconds: Optional[float] = Field(default=5.0, gt=0, description="Ограничение времени для точных методов")