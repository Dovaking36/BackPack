"""
Решатель задачи упаковки коробок в контейнеры.

Использует эвристический алгоритм:
- Сортировка коробок по убыванию объёма (First-Fit Decreasing).
- Упаковка в контейнеры последовательно (по приоритету из списка).
- Внутри контейнера – размещение по слоям (2D упаковка на каждом слое).
- Поддержка поворотов коробок в горизонтальной плоскости.
- Проверка ограничений: максимальное количество слоёв, лёгкие на тяжёлых.
"""

from typing import List, Dict, Tuple, Optional, Any
import copy
import math

from models import Container, Box, Order, PackingResult, ContainerUsage, Placement, Rotation, SolverConfig
from constraints import (
    get_rotated_dimensions,
    check_stack_layer_limit,
    check_light_on_heavy,
    boxes_overlap  # для проверки пересечений в слое
)


class PackingSolver:
    """
    Решатель задачи упаковки коробок.
    """

    def __init__(
        self,
        containers: List[dict],
        boxes: List[dict],
        fill_threshold: float = 0.9,
        **kwargs
    ):
        """
        Инициализация решателя.

        Args:
            containers: Список словарей с описанием контейнеров.
            boxes: Список словарей с описанием типов коробок.
            fill_threshold: Целевой коэффициент заполнения (0..1).
            **kwargs: Дополнительные параметры (allow_light_on_heavy, use_rotation, algorithm и т.д.)
        """
        self.containers = [Container(**c) for c in containers]
        self.box_types = {b['id']: Box(**b) for b in boxes}
        self.fill_threshold = fill_threshold
        self.config = SolverConfig(
            fill_threshold=fill_threshold,
            use_rotation=kwargs.get('use_rotation', True),
            allow_light_on_heavy=kwargs.get('allow_light_on_heavy', False),
            algorithm=kwargs.get('algorithm', 'ffd_local'),
            time_limit_seconds=kwargs.get('time_limit_seconds', 5.0)
        )

    def check_order(self, order: Dict[str, int]) -> PackingResult:
        """
        Проверить, помещается ли заказ в доступные контейнеры.

        Args:
            order: Словарь {box_id: количество_изделий}.

        Returns:
            PackingResult с деталями размещения.
        """
        # Преобразуем количество изделий в количество коробок
        try:
            order_obj = Order(items=order)
            boxes_needed = order_obj.to_boxes_count(self.box_types)
        except (KeyError, ValueError) as e:
            return PackingResult(
                feasible=False,
                containers_used=[],
                unplaced_boxes=[{str(e): 0}],
                total_fill_ratio=0.0,
                warnings=[f"Ошибка в заказе: {e}"]
            )

        # Создаём список всех коробок для упаковки (с повторениями)
        all_boxes = []
        for box_id, qty in boxes_needed.items():
            box = self.box_types[box_id]
            for _ in range(qty):
                all_boxes.append(copy.deepcopy(box))

        # Сортируем по убыванию объёма (FFD)
        all_boxes.sort(key=lambda b: b.volume, reverse=True)

        # Результат
        containers_used = []
        unplaced = []  # список (box, почему не поместилась)
        current_box_index = 0

        # Перебираем контейнеры по порядку (приоритет = индекс в списке)
        for container in self.containers:
            if current_box_index >= len(all_boxes):
                break

            # Пытаемся упаковать оставшиеся коробки в этот контейнер
            packed_boxes, packed_info = self._pack_into_container(
                container, all_boxes[current_box_index:], self.config.allow_light_on_heavy
            )

            if packed_boxes:
                # Формируем информацию о размещении
                container_fill_ratio = sum(b.volume for b in packed_boxes) / container.volume
                # Преобразуем packed_info в список Placement
                placements = []
                for info in packed_info:
                    placements.append(Placement(
                        box_id=info['box'].id,
                        quantity=info['quantity'],
                        layer=info['layer'],
                        position=info['position'],
                        rotation=Rotation(info['rotation'])
                    ))

                containers_used.append(ContainerUsage(
                    container_id=container.id,
                    fill_ratio=container_fill_ratio,
                    placements=placements
                ))

                # Продвигаем индекс
                current_box_index += len(packed_boxes)
            else:
                # Ни одной коробки не упаковано – этот контейнер бесполезен, переходим к следующему
                continue

        # Определяем, какие коробки не упакованы
        unplaced_boxes = all_boxes[current_box_index:]
        unplaced_dict = {}
        for box in unplaced_boxes:
            unplaced_dict[box.id] = unplaced_dict.get(box.id, 0) + 1
        unplaced_list = [{k: v} for k, v in unplaced_dict.items()]

        feasible = (len(unplaced_boxes) == 0)
        total_fill_ratio = sum(cu.fill_ratio * (self.containers[i].volume / sum(c.volume for c in self.containers))
                               for i, cu in enumerate(containers_used)) if containers_used else 0.0

        warnings = []
        if not feasible:
            warnings.append(f"Не удалось упаковать {len(unplaced_boxes)} коробок")

        return PackingResult(
            feasible=feasible,
            containers_used=containers_used,
            unplaced_boxes=unplaced_list,
            total_fill_ratio=total_fill_ratio,
            warnings=warnings
        )

    def _pack_into_container(
        self,
        container: Container,
        boxes: List[Box],
        allow_light_on_heavy: bool
    ) -> Tuple[List[Box], List[dict]]:
        """
        Упаковывает коробки в один контейнер, используя слоевой алгоритм.

        Args:
            container: Контейнер.
            boxes: Список коробок (уже отсортированных по убыванию объёма).
            allow_light_on_heavy: Разрешить лёгкие на тяжёлых.

        Returns:
            (список упакованных коробок, список информации о каждой упакованной группе)
        """
        # Структура слоёв: каждый слой имеет:
        # - z (высота нижней границы)
        # - высоту слоя (определяется максимальной высотой коробки в слое)
        # - список размещённых коробок с их координатами (x, y, width, depth, box, rotation)
        layers = []

        packed_boxes = []
        packed_info = []

        for box in boxes:
            placed = False
            # Пробуем разместить в существующих слоях
            for layer_idx, layer in enumerate(layers, start=1):
                # Проверяем ограничение по слоям для этой коробки
                if not check_stack_layer_limit(box, layer_idx):
                    continue

                # Проверяем, можно ли поставить лёгкую на тяжёлый слой (если слой содержит тяжёлые коробки)
                if not allow_light_on_heavy and box.max_stack_layers is None:
                    # Новая коробка лёгкая – смотрим, есть ли в этом слое тяжёлые
                    if any(b.max_stack_layers is not None for (b, _, _, _, _) in layer['items']):
                        continue  # Нельзя лёгкую на слой с тяжёлыми

                # Пытаемся разместить на свободном месте в слое
                position, rotation = self._find_position_in_layer(layer, box, container, self.config.use_rotation)
                if position is not None:
                    # Размещаем
                    w, d, h = get_rotated_dimensions(box, rotation)
                    layer['items'].append((box, position[0], position[1], w, d, rotation))
                    packed_boxes.append(box)
                    packed_info.append({
                        'box': box,
                        'quantity': 1,
                        'layer': layer_idx,
                        'position': (position[0], position[1], layer['z']),
                        'rotation': rotation
                    })
                    placed = True
                    break

            if not placed:
                # Пытаемся создать новый слой
                new_layer_z = sum(l['height'] for l in layers) if layers else 0.0
                # Высота нового слоя = высота коробки (вместе с поворотом)
                _, _, h = get_rotated_dimensions(box, '0') if not self.config.use_rotation else (
                    get_rotated_dimensions(box, '0') + get_rotated_dimensions(box, '90')
                )
                # На самом деле высота коробки не зависит от поворота, т.к. высота не меняется.
                h = box.height
                if new_layer_z + h <= container.height + 1e-9:
                    # Проверяем ограничение по слоям для новой коробки
                    new_layer_number = len(layers) + 1
                    if check_stack_layer_limit(box, new_layer_number):
                        # Проверяем, не нарушится ли правило "лёгкая на тяжёлый слой" (новый слой будет над существующими)
                        # Если под новым слоем есть тяжёлые коробки, а новая лёгкая – запрещено
                        if not allow_light_on_heavy and box.max_stack_layers is None:
                            # Проверяем, есть ли тяжёлые коробки в любом из нижних слоёв
                            heavy_below = any(
                                any(b2.max_stack_layers is not None for (b2, _, _, _, _, _) in layer['items'])
                                for layer in layers
                            )
                            if heavy_below:
                                placed = False
                                continue
                        # Создаём новый слой
                        new_layer = {
                            'z': new_layer_z,
                            'height': h,
                            'items': []  # (box, x, y, width, depth, rotation)
                        }
                        # Размещаем коробку в начале слоя (0,0)
                        w, d, _ = get_rotated_dimensions(box, '0')
                        new_layer['items'].append((box, 0.0, 0.0, w, d, '0'))
                        layers.append(new_layer)
                        packed_boxes.append(box)
                        packed_info.append({
                            'box': box,
                            'quantity': 1,
                            'layer': new_layer_number,
                            'position': (0.0, 0.0, new_layer_z),
                            'rotation': '0'
                        })
                        placed = True
                # Если не помещается по высоте – не размещаем

        return packed_boxes, packed_info

    def _find_position_in_layer(
        self,
        layer: dict,
        box: Box,
        container: Container,
        use_rotation: bool
    ) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
        """
        Ищет свободное место в слое для коробки (2D упаковка).

        Используется простой эвристический поиск: перебираем возможные позиции
        вдоль правых и верхних границ уже уложенных коробок + начало координат.

        Args:
            layer: Словарь слоя с ключом 'items'.
            box: Коробка.
            container: Контейнер (нужен для границ по ширине и глубине).
            use_rotation: Разрешать ли поворот.

        Returns:
            ( (x, y), rotation ) или (None, None), если место не найдено.
        """
        # Генерируем возможные повороты
        rotations = ['0']
        if use_rotation:
            rotations.append('90')

        for rot in rotations:
            w, d, _ = get_rotated_dimensions(box, rot)
            # Собираем все потенциальные координаты x, y на основе существующих коробок
            # Простейший вариант: перебираем все возможные x от 0 до container.width - w с шагом, но это долго.
            # Более эффективно: собираем "точки привязки" – правые границы коробок и левую границу 0.
            x_candidates = {0.0}
            y_candidates = {0.0}
            for (_, x, y, bw, bd, _) in layer['items']:
                x_candidates.add(x + bw)  # правая граница
                y_candidates.add(y + bd)  # верхняя граница

            # Сортируем кандидатов
            x_list = sorted(x_candidates)
            y_list = sorted(y_candidates)

            # Перебираем позиции
            for x in x_list:
                if x + w > container.width + 1e-9:
                    continue
                for y in y_list:
                    if y + d > container.depth + 1e-9:
                        continue
                    # Проверяем, не пересекается ли с другими коробками в слое
                    overlap = False
                    for (_, ox, oy, ow, od, _) in layer['items']:
                        if not (x + w <= ox + 1e-9 or x >= ox + ow - 1e-9 or
                                y + d <= oy + 1e-9 or y >= oy + od - 1e-9):
                            overlap = True
                            break
                    if not overlap:
                        return (x, y), rot
        return None, None

    def optimize(self, max_items: Dict[str, int]) -> PackingResult:
        """
        Находит оптимальное количество изделий для достижения fill_threshold.

        Простая эвристика: пытаемся упаковать max_items, если не влезает,
        уменьшаем количество по одному (по очереди) до тех пор, пока не станет feasible и fill_ratio >= threshold.

        Args:
            max_items: Словарь {box_id: максимальное количество изделий}.

        Returns:
            PackingResult для найденного заказа.
        """
        # Проверяем, что все box_id существуют
        for box_id in max_items:
            if box_id not in self.box_types:
                return PackingResult(
                    feasible=False,
                    containers_used=[],
                    unplaced_boxes=[{box_id: max_items[box_id]}],
                    total_fill_ratio=0.0,
                    warnings=[f"Неизвестный тип коробки {box_id}"]
                )

        # Текущий заказ копируем
        current_order = dict(max_items)

        # Функция для проверки, достигнут ли порог fill_threshold
        def meets_threshold(res: PackingResult) -> bool:
            return res.feasible and res.total_fill_ratio >= self.fill_threshold

        # Пробуем исходный заказ
        result = self.check_order(current_order)
        if meets_threshold(result):
            return result

        # Если не влезает, уменьшаем количество коробок (жадно, по одному)
        # Сортируем типы коробок по убыванию "важности" (например, по объёму)
        box_volumes = {bid: self.box_types[bid].volume for bid in max_items}
        sorted_boxes = sorted(max_items.keys(), key=lambda bid: box_volumes[bid], reverse=True)

        # Пока не достигли порога и есть что уменьшать
        improved = True
        while not meets_threshold(result) and improved:
            improved = False
            for box_id in sorted_boxes:
                if current_order[box_id] > 0:
                    current_order[box_id] -= 1
                    new_result = self.check_order(current_order)
                    if meets_threshold(new_result):
                        return new_result
                    if new_result.feasible and new_result.total_fill_ratio > result.total_fill_ratio:
                        result = new_result
                        improved = True
                        break  # начнём заново с новым результатом
                    else:
                        # откатываем
                        current_order[box_id] += 1

        # Если ничего не улучшилось, возвращаем последний feasible (или worst)
        if result.feasible:
            return result
        else:
            # Возвращаем результат с предупреждением, что порог не достигнут
            result.warnings.append(f"Не удалось достичь fill_threshold {self.fill_threshold}")
            return result