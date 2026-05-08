


V1 = {'id': 'V1', 'width': 120, 'depth': 80, 'height': 100}
V2 = {'id': 'V2', 'width': 240, 'depth': 120, 'height': 140}
V3 = {'id': 'V3', 'width': 360, 'depth': 120, 'height': 200}


P1 = {
    'id': 'P1',
    'width': 30, 'depth': 20, 'height': 15,
    'weight': 2.5, 'items_per_box': 10, 'max_stack_layers': None
}
P2 = {
    'id': 'P2',
    'width': 60, 'depth': 40, 'height': 30,
    'weight': 18.0, 'items_per_box': 4, 'max_stack_layers': 3
}
P3 = {
    'id': 'P3',
    'width': 45, 'depth': 30, 'height': 20,
    'weight': 8.0, 'items_per_box': 6, 'max_stack_layers': None
}
P4_HEAVY = {
    'id': 'P4',
    'width': 50, 'depth': 50, 'height': 40,
    'weight': 30.0, 'items_per_box': 2, 'max_stack_layers': 2
}


ORDER_BASIC = {'P1': 20, 'P2': 4, 'P3': 6}
ORDER_OVERFLOW = {'P1': 500, 'P2': 100, 'P3': 200}
ORDER_EMPTY = {}
ORDER_ONLY_P1 = {'P1': 50}
ORDER_HEAVY = {'P4': 8}