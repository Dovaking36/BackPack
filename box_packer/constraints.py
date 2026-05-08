"""
Модуль ограничений для упаковки коробок.

Содержит функции проверки допустимости размещения коробки:
- габаритные проверки (внутри контейнера)
- пересечения с уже уложенными коробками
- физическая поддержка (не "в воздухе")
- ограничение по максимальному количеству слоёв для тяжёлых коробок
- запрет на установку лёгкой коробки поверх тяжёлой (опционально)
"""

from typing import List, Tuple, Optional

# Импорт моделей (предполагается, что models.py описывает Container, Box)
from models import Container, Box


def get_rotated_dimensions(box: Box, rotation: str) -> Tuple[float, float, float]:
    """
    Возвращает (ширина, глубина, высота) коробки после поворота.

    Поворот разрешён только в горизонтальной плоскости (на 90°),
    поэтому высота не меняется.

    Args:
        box: Коробка.
        rotation: Строка '0' (без поворота) или '90' (поворот на 90°).

    Returns:
        Кортеж (width, depth, height) после поворота.
    """
    if rotation == '90':
        return box.depth, box.width, box.height
    else:   # '0' или любое другое значение трактуется как без поворота
        return box.width, box.depth, box.height


def is_within_container(box: Box, position: Tuple[float, float, float],
                        rotation: str, container: Container) -> bool:
    """
    Проверяет, помещается ли коробка в контейнер без выхода за грани.

    Args:
        box: Коробка.
        position: (x, y, z) – координаты левого нижнего ближнего угла.
        rotation: Поворот ('0' или '90').
        container: Контейнер.

    Returns:
        True, если коробка целиком внутри контейнера.
    """
    x, y, z = position
    w, d, h = get_rotated_dimensions(box, rotation)

    if x < 0 or y < 0 or z < 0:
        return False
    if x + w > container.width + 1e-9:
        return False
    if y + d > container.depth + 1e-9:
        return False
    if z + h > container.height + 1e-9:
        return False
    return True


def boxes_overlap(box1: Box, pos1: Tuple[float, float, float], rot1: str,
                  box2: Box, pos2: Tuple[float, float, float], rot2: str) -> bool:
    """
    Проверяет пересечение двух коробок в пространстве.

    Args:
        box1, pos1, rot1: Первая коробка, её позиция и поворот.
        box2, pos2, rot2: Вторая коробка, её позиция и поворот.

    Returns:
        True, если коробки пересекаются (имеют общий объём).
    """
    x1, y1, z1 = pos1
    w1, d1, h1 = get_rotated_dimensions(box1, rot1)
    x2, y2, z2 = pos2
    w2, d2, h2 = get_rotated_dimensions(box2, rot2)

    # Пересечение по X
    if x1 + w1 <= x2 + 1e-9 or x2 + w2 <= x1 + 1e-9:
        return False
    # Пересечение по Y
    if y1 + d1 <= y2 + 1e-9 or y2 + d2 <= y1 + 1e-9:
        return False
    # Пересечение по Z
    if z1 + h1 <= z2 + 1e-9 or z2 + h2 <= z1 + 1e-9:
        return False
    return True


def is_supported(box: Box, position: Tuple[float, float, float], rotation: str,
                 placed_boxes: List[Tuple[Box, Tuple[float, float, float], str]]) -> bool:
    """
    Проверяет, стоит ли коробка на дне контейнера или на других коробках.

    Коробка считается поддерживаемой, если:
    - её нижняя грань находится на уровне 0 (дно), или
    - существует хотя бы одна коробка, чья верхняя грань совпадает с её нижней
      гранью и проекции перекрываются.

    Args:
        box: Новая коробка.
        position, rotation: Её позиция и поворот.
        placed_boxes: Список уже размещённых коробок (каждый элемент –
            (box, position, rotation)).

    Returns:
        True, если коробка имеет опору.
    """
    x, y, z = position
    w, d, h = get_rotated_dimensions(box, rotation)

    # Дно
    if abs(z) < 1e-9:
        return True

    # Поиск опоры среди уже размещённых
    for other_box, other_pos, other_rot in placed_boxes:
        ox, oy, oz = other_pos
        ow, od, oh = get_rotated_dimensions(other_box, other_rot)

        # Верхняя грань other совпадает с нижней гранью current?
        if abs(oz + oh - z) > 1e-9:
            continue

        # Перекрытие проекций по X и Y
        x_overlap = (x + w > ox + 1e-9) and (x < ox + ow - 1e-9)
        y_overlap = (y + d > oy + 1e-9) and (y < oy + od - 1e-9)
        if x_overlap and y_overlap:
            return True

    return False


def check_light_on_heavy(box: Box, position: Tuple[float, float, float], rotation: str,
                         placed_boxes: List[Tuple[Box, Tuple[float, float, float], str]],
                         allow_light_on_heavy: bool) -> bool:
    """
    Проверяет правило: лёгкие коробки не ставятся поверх тяжёлых.

    "Тяжёлыми" считаются коробки, у которых задано поле max_stack_layers
    (то есть для них есть ограничение по слоям). "Лёгкие" – у кого max_stack_layers = None.

    Args:
        box: Новая (проверяемая) коробка.
        position, rotation: Её позиция и поворот.
        placed_boxes: Уже размещённые коробки.
        allow_light_on_heavy: Флаг, разрешающий нарушение правила.

    Returns:
        True, если правило соблюдено (или разрешено нарушение).
    """
    if allow_light_on_heavy:
        return True

    # Если новая коробка тяжёлая – правило не про неё (тяжёлые могут стоять на тяжёлых/лёгких)
    if box.max_stack_layers is not None:
        return True

    # Новая коробка лёгкая – проверим, не опирается ли она на тяжёлую
    x, y, z = position
    w, d, h = get_rotated_dimensions(box, rotation)

    for other_box, other_pos, other_rot in placed_boxes:
        if other_box.max_stack_layers is None:
            continue   # other – лёгкая, не нарушает

        ox, oy, oz = other_pos
        ow, od, oh = get_rotated_dimensions(other_box, other_rot)

        # Проверка, что other поддерживает current (верх other = низ current)
        if abs(oz + oh - z) > 1e-9:
            continue

        x_overlap = (x + w > ox + 1e-9) and (x < ox + ow - 1e-9)
        y_overlap = (y + d > oy + 1e-9) and (y < oy + od - 1e-9)
        if x_overlap and y_overlap:
            return False   # Лёгкая на тяжёлой – нарушение

    return True


def check_stack_layer_limit(box: Box, layer: int) -> bool:
    """
    Проверяет, не превышает ли коробка свой лимит по слоям.

    Args:
        box: Коробка.
        layer: Номер слоя, в который планируется укладка (начиная с 1 – самый нижний).

    Returns:
        True, если лимит не задан или layer <= max_stack_layers.
    """
    if box.max_stack_layers is None:
        return True
    return layer <= box.max_stack_layers


def is_position_valid(box: Box, position: Tuple[float, float, float], rotation: str,
                      container: Container,
                      placed_boxes: List[Tuple[Box, Tuple[float, float, float], str]],
                      layer: int,
                      allow_light_on_heavy: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Комплексная проверка допустимости размещения коробки.

    Выполняет все проверки:
    1. Выход за границы контейнера.
    2. Пересечение с уже размещёнными коробками.
    3. Отсутствие опоры (висит в воздухе).
    4. Ограничение по слоям (max_stack_layers).
    5. Лёгкая на тяжёлой (если запрещено).

    Args:
        box: Проверяемая коробка.
        position, rotation: Предлагаемая позиция и поворот.
        container: Контейнер, в который укладываем.
        placed_boxes: Список уже размещённых коробок.
        layer: Номер слоя для этой коробки (назначается алгоритмом укладки).
        allow_light_on_heavy: Разрешить ставить лёгкие коробки на тяжёлые.

    Returns:
        Кортеж (ok, причина_отказа). Если ok == False, причина содержит описание.
    """
    # 1. Геометрия контейнера
    if not is_within_container(box, position, rotation, container):
        return False, "коробка выходит за границы контейнера"

    # 2. Пересечения
    for other_box, other_pos, other_rot in placed_boxes:
        if boxes_overlap(box, position, rotation, other_box, other_pos, other_rot):
            return False, f"пересечение с коробкой {other_box.id}"

    # 3. Поддержка (не в воздухе)
    if not is_supported(box, position, rotation, placed_boxes):
        return False, "коробка не имеет опоры (висит в воздухе)"

    # 4. Лимит слоёв
    if not check_stack_layer_limit(box, layer):
        return False, f"превышен лимит слоёв для {box.id}: макс {box.max_stack_layers}, слой {layer}"

    # 5. Лёгкая на тяжёлой
    if not check_light_on_heavy(box, position, rotation, placed_boxes, allow_light_on_heavy):
        return False, f"лёгкая коробка {box.id} не может стоять на тяжёлой"

    return True, None