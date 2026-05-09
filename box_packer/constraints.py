"""
Модуль ограничений для упаковки коробок.
"""
from typing import List, Tuple, Optional
from box_packer.models import Container, Box

def get_rotated_dimensions(box: Box, rotation: str) -> Tuple[float, float, float]:
    if rotation == '90':
        return box.depth, box.width, box.height
    return box.width, box.depth, box.height

def is_within_container(box: Box, position: Tuple[float, float, float],
                        rotation: str, container: Container) -> bool:
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
    x1, y1, z1 = pos1
    w1, d1, h1 = get_rotated_dimensions(box1, rot1)
    x2, y2, z2 = pos2
    w2, d2, h2 = get_rotated_dimensions(box2, rot2)

    if x1 + w1 <= x2 + 1e-9 or x2 + w2 <= x1 + 1e-9:
        return False
    if y1 + d1 <= y2 + 1e-9 or y2 + d2 <= y1 + 1e-9:
        return False
    if z1 + h1 <= z2 + 1e-9 or z2 + h2 <= z1 + 1e-9:
        return False
    return True

def is_supported(box: Box, position: Tuple[float, float, float], rotation: str,
                 placed_boxes: List[Tuple[Box, Tuple[float, float, float], str]]) -> bool:
    x, y, z = position
    w, d, h = get_rotated_dimensions(box, rotation)

    if abs(z) < 1e-9:
        return True

    for other_box, other_pos, other_rot in placed_boxes:
        ox, oy, oz = other_pos
        ow, od, oh = get_rotated_dimensions(other_box, other_rot)

        if abs(oz + oh - z) > 1e-9:
            continue

        x_overlap = (x + w > ox + 1e-9) and (x < ox + ow - 1e-9)
        y_overlap = (y + d > oy + 1e-9) and (y < oy + od - 1e-9)
        if x_overlap and y_overlap:
            return True
    return False

def check_light_on_heavy(box: Box, position: Tuple[float, float, float], rotation: str,
                         placed_boxes: List[Tuple[Box, Tuple[float, float, float], str]],
                         allow_light_on_heavy: bool) -> bool:
    if allow_light_on_heavy:
        return True

    if box.max_stack_layers is not None:
        return True

    x, y, z = position
    w, d, h = get_rotated_dimensions(box, rotation)

    for other_box, other_pos, other_rot in placed_boxes:
        if other_box.max_stack_layers is None:
            continue

        ox, oy, oz = other_pos
        ow, od, oh = get_rotated_dimensions(other_box, other_rot)

        if abs(oz + oh - z) > 1e-9:
            continue

        x_overlap = (x + w > ox + 1e-9) and (x < ox + ow - 1e-9)
        y_overlap = (y + d > oy + 1e-9) and (y < oy + od - 1e-9)
        if x_overlap and y_overlap:
            return False
    return True

def check_stack_layer_limit(box: Box, layer: int) -> bool:
    if box.max_stack_layers is None:
        return True
    return layer <= box.max_stack_layers

def is_position_valid(box: Box, position: Tuple[float, float, float], rotation: str,
                      container: Container,
                      placed_boxes: List[Tuple[Box, Tuple[float, float, float], str]],
                      layer: int,
                      allow_light_on_heavy: bool = False) -> Tuple[bool, Optional[str]]:
    if not is_within_container(box, position, rotation, container):
        return False, "коробка выходит за границы контейнера"

    for other_box, other_pos, other_rot in placed_boxes:
        if boxes_overlap(box, position, rotation, other_box, other_pos, other_rot):
            return False, f"пересечение с коробкой {other_box.id}"

    if not is_supported(box, position, rotation, placed_boxes):
        return False, "коробка не имеет опоры (висит в воздухе)"

    if not check_stack_layer_limit(box, layer):
        return False, f"превышен лимит слоёв для {box.id}: макс {box.max_stack_layers}, слой {layer}"

    if not check_light_on_heavy(box, position, rotation, placed_boxes, allow_light_on_heavy):
        return False, f"лёгкая коробка {box.id} не может стоять на тяжёлой"

    return True, None