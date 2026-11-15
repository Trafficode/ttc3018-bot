"""Bounded isolation-band settings; no machine or geometry dependencies."""


def validate_isolation_passes(value=1):
    """Only the two supported, reviewed toolpath modes are accepted."""
    if type(value) is not int or value not in (1, 2):
        raise ValueError("Izolacja: wybierz 1 lub 2 przejazdy.")
    return value
