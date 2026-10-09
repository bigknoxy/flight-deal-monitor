"""Test price analysis utilities."""


from app.utils import (
    calculate_price_drop,
    detect_deal,
    generate_route_id,
)


def test_calculate_price_drop():
    """Test price drop calculation."""
    drop = calculate_price_drop(300.0, 500.0)

    assert drop == 40.0


def test_calculate_price_drop_zero_median():
    """Test price drop calculation with zero median."""
    drop = calculate_price_drop(100.0, 0.0)

    assert drop == 0.0


def test_detect_deal_flash_sale():
    """Test flash sale detection (>=50% off, but not mistake fare)."""
    is_deal, deal_type = detect_deal(200.0, 500.0)  # 60% off

    assert is_deal is True
    assert deal_type == "flash_sale"


def test_detect_deal_mistake_fare():
    """Test mistake fare detection."""
    is_deal, deal_type = detect_deal(100.0, 500.0)

    assert is_deal is True
    assert deal_type == "mistake_fare"


def test_detect_deal_not_a_deal():
    """Test non-deal detection."""
    is_deal, deal_type = detect_deal(600.0, 500.0)

    assert is_deal is False
    assert deal_type is None


def test_detect_deal_equal_price():
    """Test equal price detection."""
    is_deal, deal_type = detect_deal(500.0, 500.0)

    assert is_deal is False
    assert deal_type is None


def test_generate_route_id():
    """Test route ID generation."""
    route_id_1 = generate_route_id("MCI", "LHR", "2024-06-01", "BA")
    route_id_2 = generate_route_id("MCI", "LHR", "2024-06-01", "BA")
    route_id_3 = generate_route_id("MCI", "LHR", "2024-06-02", "BA")

    assert route_id_1 == route_id_2
    assert route_id_1 != route_id_3
    assert len(route_id_1) == 16

def test_route_type_unknown_airports():
    """Test that unknown airports outside known sets don't silently default to domestic.
    
    SYD (Sydney, Australia) and CPT (Cape Town, South Africa) are not in any
    of the hardcoded sets, so get_route_type should not silently return
    'domestic' — it should be explicit about unknown regions.
    """
    from app.utils.price_analysis import get_route_type
    
    # SYD and CPT are both outside US/EU/Asia/LatAm sets
    result = get_route_type("SYD", "CPT")
    # Currently this silently returns "domestic" — the bug
    assert result != "domestic", (
        f"get_route_type('SYD', 'CPT') returned 'domestic' but should not "
        f"silently default to domestic for unknown airports. Got: {result}"
    )

