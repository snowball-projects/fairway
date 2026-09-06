"""Canonical travel-time precision shared by ranking and validation."""

from decimal import ROUND_HALF_UP, Decimal

SCORE_RESOLUTION_MILLISECONDS = 1


def travel_time_milliseconds(seconds):
    """Round nonnegative seconds to the nearest millisecond, with halves up."""
    return int(
        (Decimal(str(float(seconds))) * 1000).to_integral_value(rounding=ROUND_HALF_UP)
    )


def canonical_milliseconds(values):
    return tuple(travel_time_milliseconds(value) for value in values)
