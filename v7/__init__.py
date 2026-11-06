"""V7 combines aligned V5 temperature/humidity and V6 rainfall forecasts."""
from .composition import compose_forecasts, point_forecasts

__version__ = 'engine_v7_combined.1'
__all__ = ['compose_forecasts', 'point_forecasts']
