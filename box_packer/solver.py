"""
Решатель задачи упаковки коробок в контейнеры.
"""
from typing import List, Dict, Tuple, Optional
import copy
from box_packer.models import Container, Box, Order, PackingResult, ContainerUsage, Placement, Rotation, SolverConfig
from box_packer.constraints import get_rotated_dimensions, check_stack_layer_limit


class PackingSolver:
    def __init__(
            self,
            containers: List[dict],
            boxes: List[dict],
            fill_threshold: float = 0.9,
            **kwargs
    ):
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

        all_boxes = []
        for box_id, qty in boxes_needed.items():
            box = self.box_types[box_id]
            for _ in range(qty):
                all_boxes.append(copy.deepcopy(box))

        all_boxes.sort(key=lambda b: b.volume, reverse=True)

        containers_used = []
        current_box_index = 0

        for container in self.containers:
            if current_box_index >= len(all_boxes):
                break

            packed_boxes, packed_info = self._pack_into_container(
                container, all_boxes[current_box_index:], self.config.allow_light_on_heavy
            )

            if packed_boxes:
                container_fill_ratio = sum(b.volume for b in packed_boxes) / container.volume
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
                current_box_index += len(packed_boxes)
            else:
                continue

        unplaced_boxes = all_boxes[current_box_index:]
        unplaced_dict = {}
        for box in unplaced_boxes:
            unplaced_dict[box.id] = unplaced_dict.get(box.id, 0) + 1
        unplaced_list = [{k: v} for k, v in unplaced_dict.items()]

        feasible = (len(unplaced_boxes) == 0)

        # ИСПРАВЛЕНИЕ: считаем заполненность только по ИСПОЛЬЗОВАННЫМ контейнерам
        used_containers_ids = {cu.container_id for cu in containers_used}
        used_volume = sum(c.volume for c in self.containers if c.id in used_containers_ids)
        packed_volume = sum(b.volume for b in all_boxes[:current_box_index])

        total_fill_ratio = (packed_volume / used_volume) if used_volume > 0 else 0.0

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
        layers = []
        packed_boxes = []
        packed_info = []

        for box in boxes:
            # 1. Попытка разместить в существующих слоях
            for layer_idx, layer in enumerate(layers, start=1):
                if not check_stack_layer_limit(box, layer_idx):
                    continue
                if not allow_light_on_heavy and box.max_stack_layers is None:
                    if any(b.max_stack_layers is not None for (b, _, _, _, _, _) in layer['items']):
                        continue

                position, rotation = self._find_position_in_layer(
                    layer, box, container, self.config.use_rotation
                )
                if position is not None:
                    w, d, _ = get_rotated_dimensions(box, rotation)
                    x, y = position
                    layer['items'].append((box, x, y, w, d, rotation))
                    packed_boxes.append(box)
                    packed_info.append({
                        'box': box, 'quantity': 1, 'layer': layer_idx,
                        'position': (x, y, layer['z']), 'rotation': rotation
                    })
                    break  # Коробка успешно размещена → переходим к следующей
            else:
                # 2. Блок else выполняется ТОЛЬКО если цикл выше завершился без break
                # (т.е. коробка не влезла ни в один существующий слой)
                new_layer_z = sum(l['height'] for l in layers) if layers else 0.0
                h = box.height

                if new_layer_z + h > container.height + 1e-9:
                    continue  # Не хватает высоты в контейнере

                new_layer_number = len(layers) + 1
                if not check_stack_layer_limit(box, new_layer_number):
                    continue

                if not allow_light_on_heavy and box.max_stack_layers is None:
                    heavy_below = any(
                        any(b2.max_stack_layers is not None for (b2, _, _, _, _, _) in l['items'])
                        for l in layers
                    )
                    if heavy_below:
                        continue

                # Определяем допустимый поворот inline
                w0, d0, _ = get_rotated_dimensions(box, '0')
                w90, d90, _ = get_rotated_dimensions(box, '90')

                rotation = None
                if w0 <= container.width + 1e-9 and d0 <= container.depth + 1e-9:
                    rotation, w, d = '0', w0, d0
                elif self.config.use_rotation and w90 <= container.width + 1e-9 and d90 <= container.depth + 1e-9:
                    rotation, w, d = '90', w90, d90

                if rotation is None:
                    continue  # Коробка физически не помещается в контейнер ни в одном повороте

                # Создаём новый слой и сразу размещаем первую коробку
                new_layer = {
                    'z': new_layer_z,
                    'height': h,
                    'items': [(box, 0.0, 0.0, w, d, rotation)]
                }
                layers.append(new_layer)
                packed_boxes.append(box)
                packed_info.append({
                    'box': box, 'quantity': 1, 'layer': new_layer_number,
                    'position': (0.0, 0.0, new_layer_z), 'rotation': rotation
                })

        return packed_boxes, packed_info

    def _find_position_in_layer(
            self,
            layer: dict,
            box: Box,
            container: Container,
            use_rotation: bool
    ) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
        rotations = ['0']
        if use_rotation:
            rotations.append('90')

        for rot in rotations:
            w, d, _ = get_rotated_dimensions(box, rot)
            x_candidates = {0.0}
            y_candidates = {0.0}
            for (_, ox, oy, ow, od, _) in layer['items']:
                x_candidates.add(ox + ow)
                y_candidates.add(oy + od)

            x_list = sorted(x_candidates)
            y_list = sorted(y_candidates)

            for x in x_list:
                if x + w > container.width + 1e-9:
                    continue
                for y in y_list:
                    if y + d > container.depth + 1e-9:
                        continue

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
        for box_id in max_items:
            if box_id not in self.box_types:
                return PackingResult(
                    feasible=False, containers_used=[], unplaced_boxes=[{box_id: max_items[box_id]}],
                    total_fill_ratio=0.0, warnings=[f"Неизвестный тип коробки {box_id}"]
                )

        current_order = dict(max_items)

        result = self.check_order(current_order)
        if result.feasible and result.total_fill_ratio >= self.fill_threshold - 1e-6:
            return result

        # Жадно уменьшаем заказ только до достижения feasible=True
        sorted_boxes = sorted(max_items.keys(), key=lambda bid: self.box_types[bid].volume, reverse=True)
        reduced = True
        while not result.feasible and reduced:
            reduced = False
            for box_id in sorted_boxes:
                if current_order.get(box_id, 0) > 0:
                    current_order[box_id] -= 1
                    result = self.check_order(current_order)
                    reduced = True
                    if result.feasible:
                        break

        if not result.feasible:
            result = result.model_copy(update={
                "warnings": list(result.warnings) + ["Не удалось разместить заказ. Проверьте габариты коробок."]
            })
            return result

        if result.total_fill_ratio < self.fill_threshold - 1e-6:
            result = result.model_copy(update={
                "warnings": list(result.warnings) + [
                    f"Заказ размещён, но fill_ratio {result.total_fill_ratio:.2f} < порога {self.fill_threshold}"
                ]
            })
        return result