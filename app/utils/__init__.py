"""Utility modules."""

from app.utils.deduplication import (
    cleanup_expired_deals,
    generate_deal_hash,
    is_flight_seen_recently,
    mark_flight_seen,
)
from app.utils.price_analysis import (
    calculate_median_price,
    calculate_price_drop,
    detect_deal,
    generate_route_id,
)

__all__ = [
    "calculate_median_price",
    "calculate_price_drop",
    "detect_deal",
    "generate_route_id",
    "cleanup_expired_deals",
    "generate_deal_hash",
    "is_flight_seen_recently",
    "mark_flight_seen",
]
