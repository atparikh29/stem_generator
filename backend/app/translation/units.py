"""Shared pint unit registry for physics translation and verification."""
from __future__ import annotations

from pint import UnitRegistry

# One registry process-wide; quantities from different registries can't be compared.
ureg = UnitRegistry()
Q_ = ureg.Quantity
