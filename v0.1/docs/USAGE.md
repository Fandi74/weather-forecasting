# Use the public v0.1 package

Python 3.12 was tested with the pinned requirements. This package is standalone:
no private archive, registration system, absolute source path or external
repository is needed for inference/replay.

## Commands

```sh
python v0.1/verify_package.py
python -m pip install -r v0.1/requirements.txt
python -m unittest discover -s v0.1/tests -v
python v0.1/run.py replay
python v0.1/plot_results.py
```

Hash verification and metric arithmetic use only the standard library.
Inference/replay uses NumPy, CatBoost and LightGBM. Matplotlib regenerates plots.
CatBoost is loaded from cleaned JSON rather than an opaque binary with original
training metadata. The model files retain their numerical behavior within
the documented replay tolerance.

## Python API

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("v0.1").resolve()))
from engine import load, predict_points, predict_rain_windows, compose

points = predict_points(load("data/point_inputs.json"))
rain = predict_rain_windows(load("data/rain_inputs.json"))
windows = compose(points, rain)
```

All rows in a composition call must belong to the same forecast issue.
The public schema uses relative lead hours; maintaining a shared issue is the
caller's responsibility.

Point inputs provide an anonymous site key, lead hours, local hour, forecast
day 1–7, raw forecast temperature/humidity/rain and prepared past-only humidity
history features. Missing history is represented as null and converted to NaN.
See the complete example in [point_inputs.json](../data/point_inputs.json).

Rain inputs provide Site A/B, a 1/6/12/24-hour horizon, prepared feature values
and the hourly raw forecasts spanning that window. An optional
max_context_available_offset_hours must be <= 0. See
[rain_inputs.json](../data/rain_inputs.json). These are prepared features,
not raw sensor packets; the package does not reconstruct device telemetry or
measure actual ingestion latency.

## Output meanings

- Point output temperature is degrees C and humidity is percent, at the stated
  forecast lead. Its baseline_rain_mm and baseline_rain_probability fields are
  hourly baseline/control values, not the updated direct rain-window prediction.
- predict_rain_windows returns rain amount in mm over the entire window and
  the probability that this total reaches 0.28 mm.
- compose pairs point temperature/humidity at each window end with the direct
  rain-window result at Sites A/B.
- Other sites use summed hourly baseline amounts; unsupported multi-hour
  probabilities are null. Probabilities are never added.
- The 1/6/12/24-hour windows overlap. Do not add their totals or invent an hourly
  distribution by dividing them.

The demo reproduces 672 point rows, eight direct rain windows and 16 composed
window rows. It is a historical example, not a refreshed live forecast.
New forecasts require matching raw weather forecasts and prepared observations
available at the real issue time.
