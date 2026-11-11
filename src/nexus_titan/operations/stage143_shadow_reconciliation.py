from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class PaperOrder:
    order_id: str
    quantity: int


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    order_id: str
    quantity: int
    price: float


@dataclass(frozen=True)
class ReconciliationReport:
    accepted: bool
    order_count: int
    fill_count: int
    total_filled_quantity: int
    reasons: tuple[str, ...]
    live_authorized: bool = False


def reconcile_shadow_orders(
    orders,
    fills,
) -> ReconciliationReport:
    if not isinstance(orders, (list, tuple)):
        raise TypeError("Orders must be a sequence")

    if not isinstance(fills, (list, tuple)):
        raise TypeError("Fills must be a sequence")

    reasons = []
    order_map = {}
    filled = {}
    fill_ids = set()
    total_quantity = 0

    for order in orders:
        if not isinstance(order, PaperOrder):
            raise TypeError("PaperOrder required")

        if (
            type(order.order_id) is not str
            or not order.order_id.strip()
            or type(order.quantity) is not int
            or order.quantity <= 0
        ):
            raise ValueError("Invalid order")

        if order.order_id in order_map:
            reasons.append("duplicate_order_id")

        order_map[order.order_id] = order
        filled.setdefault(order.order_id, 0)

    for fill in fills:
        if not isinstance(fill, PaperFill):
            raise TypeError("PaperFill required")

        if (
            type(fill.fill_id) is not str
            or not fill.fill_id.strip()
            or type(fill.order_id) is not str
            or not fill.order_id.strip()
            or type(fill.quantity) is not int
            or fill.quantity <= 0
            or type(fill.price) not in (int, float)
            or not isfinite(fill.price)
            or fill.price <= 0
        ):
            raise ValueError("Invalid fill")

        if fill.fill_id in fill_ids:
            reasons.append("duplicate_fill_id")
            continue

        fill_ids.add(fill.fill_id)

        if fill.order_id not in order_map:
            reasons.append("unknown_order_id")
            continue

        filled[fill.order_id] += fill.quantity
        total_quantity += fill.quantity

    for order_id, order in order_map.items():
        actual = filled[order_id]

        if actual > order.quantity:
            reasons.append("overfill")

        if actual < order.quantity:
            reasons.append("incomplete_fill")

    unique_reasons = tuple(dict.fromkeys(reasons))

    return ReconciliationReport(
        accepted=not unique_reasons,
        order_count=len(orders),
        fill_count=len(fills),
        total_filled_quantity=total_quantity,
        reasons=unique_reasons,
        live_authorized=False,
    )
