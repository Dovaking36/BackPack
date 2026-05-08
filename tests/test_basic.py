import pytest
from box_packer import PackingSolver
from tests.fixtures import V1, V2, V3, P1, P2, P3, ORDER_BASIC, ORDER_OVERFLOW, ORDER_EMPTY


@pytest.fixture
def basic_solver():
    return PackingSolver(containers=[V1], boxes=[P1])


@pytest.fixture
def multi_container_solver():
    return PackingSolver(containers=[V1, V2, V3], boxes=[P1, P2, P3])


def test_simple_order_fits(basic_solver):
    """Один тип коробок помещается в контейнер V1."""
    # 100 коробок P1 (1000 изделий) -> объём 100*30*20*15 = 900 000 см³
    # объём V1 = 960 000, fill_ratio ~ 0.9375 > 0.5
    result = basic_solver.check_order({'P1': 1000})
    assert result.feasible is True
    assert result.total_fill_ratio > 0.5


def test_order_does_not_fit(basic_solver):
    """Превышение объёма V1 -> feasible=False."""
    result = basic_solver.check_order({'P1': 5000})  # 500 коробок, не влезут
    assert result.feasible is False
    assert len(result.unplaced_boxes) > 0


def test_basic_order_fits_multi(multi_container_solver):
    """Заказ ORDER_BASIC должен поместиться в V2/V3."""
    result = multi_container_solver.check_order(ORDER_BASIC)
    assert result.feasible is True
    assert result.total_fill_ratio > 0.0


def test_order_overflow_does_not_fit(multi_container_solver):
    """ORDER_OVERFLOW не помещается ни в один контейнер."""
    result = multi_container_solver.check_order(ORDER_OVERFLOW)
    assert result.feasible is False
    assert len(result.unplaced_boxes) > 0


def test_empty_order(basic_solver):
    """Пустой заказ -> feasible=True, fill_ratio=0."""
    result = basic_solver.check_order(ORDER_EMPTY)
    assert result.feasible is True
    assert result.total_fill_ratio == 0.0
    assert len(result.containers_used) == 0


def test_exact_fill():
    """Граничный случай: 100% заполнения."""
    box_exact = {
        'id': 'P_exact', 'width': 120, 'depth': 80, 'height': 100,
        'weight': 100, 'items_per_box': 1, 'max_stack_layers': None
    }
    solver = PackingSolver(containers=[V1], boxes=[box_exact])
    result = solver.check_order({'P_exact': 1})
    assert result.feasible is True
    assert abs(result.total_fill_ratio - 1.0) < 1e-6


@pytest.mark.parametrize("order, expected_feasible", [
    ({'P1': 0}, True),
    ({'P1': 10}, True),
    ({'P1': 1000}, True),
    ({'P1': 5000}, False),
])
def test_parametrized_quantities(basic_solver, order, expected_feasible):
    result = basic_solver.check_order(order)
    assert result.feasible == expected_feasible