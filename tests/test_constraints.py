"""
Тесты ограничений: максимальное количество слоёв, лёгкие на тяжёлых.
"""
import pytest
from box_packer import PackingSolver
from tests.fixtures import V2, V3, P2, P1, P3, P4_HEAVY


def test_heavy_box_layer_limit():
    """Тяжёлые коробки (max_stack_layers=3) не укладываются в 4 слоя."""
    # Создаём коробку, занимающую всю площадь контейнера -> вынуждена складываться вертикально
    big_box = {
        'id': 'BIG', 'width': 360, 'depth': 120, 'height': 30,
        'weight': 100, 'items_per_box': 1, 'max_stack_layers': 3
    }
    solver = PackingSolver(containers=[V3], boxes=[big_box])

    # 5 коробок потребуют 5 слоёв, но лимит = 3. 2 коробки не влезут.
    result = solver.check_order({'BIG': 5})
    assert result.feasible is False

    # Проверяем, что неупакованные коробки действительно остались
    assert len(result.unplaced_boxes) > 0
    assert any('BIG' in str(u) for u in result.unplaced_boxes)


def test_light_on_heavy_forbidden():
    """Лёгкая коробка (max_stack_layers=None) не должна ставиться на тяжёлую, если allow_light_on_heavy=False."""
    heavy = P4_HEAVY.copy()
    light = {
        'id': 'LIGHT', 'width': 50, 'depth': 50, 'height': 20,
        'weight': 1, 'items_per_box': 1, 'max_stack_layers': None
    }
    # Контейнер строго под размер коробок -> лёгкая вынуждена идти наверх
    small_container = {'id': 'C', 'width': 50, 'depth': 50, 'height': 100}

    solver = PackingSolver(containers=[small_container], boxes=[heavy, light], allow_light_on_heavy=False)
    # FFD сортирует по объёму: P4 (100k) > LIGHT (50k). P4 кладётся первым на дно.
    result = solver.check_order({'P4': 1, 'LIGHT': 1})
    assert result.feasible is False

    # Если разрешить, то поместится
    solver3 = PackingSolver(containers=[small_container], boxes=[heavy, light], allow_light_on_heavy=True)
    result3 = solver3.check_order({'P4': 1, 'LIGHT': 1})
    assert result3.feasible is True


def test_light_on_heavy_allowed():
    """При allow_light_on_heavy=True лёгкая коробка может стоять на тяжёлой."""
    heavy = P4_HEAVY.copy()
    light = {
        'id': 'LIGHT', 'width': 50, 'depth': 50, 'height': 20,
        'weight': 1, 'items_per_box': 1, 'max_stack_layers': None
    }
    small_container = {'id': 'C', 'width': 50, 'depth': 50, 'height': 100}

    solver = PackingSolver(containers=[small_container], boxes=[heavy, light], allow_light_on_heavy=True)
    result = solver.check_order({'P4': 1, 'LIGHT': 1})
    assert result.feasible is True

    # Проверяем, что лёгкая реально разместилась поверх тяжёлой (z >= 40)
    placed = False
    for cu in result.containers_used:
        for p in cu.placements:
            if p.box_id == 'LIGHT':
                assert p.position[2] >= pytest.approx(40.0)
                placed = True
    assert placed


def test_mixed_boxes_in_one_container():
    """Несколько типов коробок в одном контейнере."""
    solver = PackingSolver(containers=[V2], boxes=[P1, P2, P3])
    # Объём V2 = 4 032 000 см³. Заказ занимает ~1 260 000 см³ -> влезет с запасом.
    order = {'P1': 300, 'P2': 40, 'P3': 60}

    result = solver.check_order(order)
    assert result.feasible is True

    # Проверяем, что все три типа размещены
    found_types = set()
    for cu in result.containers_used:
        for p in cu.placements:
            found_types.add(p.box_id)
    assert {'P1', 'P2', 'P3'}.issubset(found_types)