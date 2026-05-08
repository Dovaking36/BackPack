import pytest
from box_packer import PackingSolver
from tests.fixtures import *


def test_heavy_box_layer_limit():
    """Тяжёлые коробки с max_stack_layers=3 не могут быть выше 3 слоёв."""
    # Создаём коробку, занимающую всю площадь, чтобы была только вертикальная стопка
    tall_box = {
        'id': 'TALL', 'width': 360, 'depth': 120, 'height': 30,
        'weight': 100, 'items_per_box': 1, 'max_stack_layers': 3
    }
    solver = PackingSolver(containers=[V3], boxes=[tall_box])
    # 5 коробок требуют 5 слоёв, что превышает лимит
    result = solver.check_order({'TALL': 5})
    assert result.feasible is False
    assert any('превышен лимит слоёв' in w for w in result.warnings)


def test_light_on_heavy_forbidden():
    """Лёгкая коробка не может стоять на тяжёлой, если allow_light_on_heavy=False."""
    heavy = P4_HEAVY.copy()
    light = {
        'id': 'LIGHT', 'width': 50, 'depth': 50, 'height': 20,
        'weight': 1, 'items_per_box': 1, 'max_stack_layers': None
    }
    small_container = {'id': 'C', 'width': 50, 'depth': 50, 'height': 100}
    solver = PackingSolver(
        containers=[small_container], boxes=[heavy, light],
        allow_light_on_heavy=False
    )
    result = solver.check_order({'P4': 1, 'LIGHT': 1})
    assert result.feasible is False


def test_light_on_heavy_allowed():
    """При allow_light_on_heavy=True лёгкая может стоять на тяжёлой."""
    heavy = P4_HEAVY.copy()
    light = {
        'id': 'LIGHT', 'width': 50, 'depth': 50, 'height': 20,
        'weight': 1, 'items_per_box': 1, 'max_stack_layers': None
    }
    small_container = {'id': 'C', 'width': 50, 'depth': 50, 'height': 100}
    solver = PackingSolver(
        containers=[small_container], boxes=[heavy, light],
        allow_light_on_heavy=True
    )
    result = solver.check_order({'P4': 1, 'LIGHT': 1})
    assert result.feasible is True
    # Проверяем, что лёгкая действительно наверху
    light_placed = False
    for cu in result.containers_used:
        for p in cu.placements:
            if p.box_id == 'LIGHT':
                assert p.position[2] >= 40  # высота тяжёлой = 40
                light_placed = True
    assert light_placed


def test_mixed_boxes_in_one_container():
    """Несколько типов коробок в одном контейнере."""
    solver = PackingSolver(containers=[V2], boxes=[P1, P2, P3])
    order = {'P1': 300, 'P2': 40, 'P3': 60}  # 30,10,10 коробок
    result = solver.check_order(order)
    assert result.feasible is True
    found_types = set()
    for cu in result.containers_used:
        for p in cu.placements:
            found_types.add(p.box_id)
    assert found_types == {'P1', 'P2', 'P3'}