# Using V7

Run these commands from the repository root with the complete `v2/` through
`v7/` folders present. Python 3.12 is the tested runtime.

## Inspect and verify without ML dependencies

```sh
python -m unittest discover -s v7/tests -v
python v7/verify_package.py
python v7/run.py verify
```

The publication verifier also checks the per-file publication manifest.
Neither verifier requires station CSVs, CatBoost, LightGBM or a network connection.
They require the earlier frozen packages and source files in the monorepo.

## Replay the rainfall models

In your chosen virtual environment:

```sh
python -m pip install -r v7/requirements.txt
python v7/run.py replay
```

The pinned dependencies are LightGBM, NumPy and matplotlib. Replay runs inference
against the saved past-only feature snapshot, checks the result against the
frozen rain predictions and removes its scratch directory inside `v7/`.
It does not retrain models, refresh weather data or use new observations.

CatBoost's V5 humidity model is bundled for provenance and upstream reuse.
This replay does not execute it: temperature/humidity come from the verified
V5 forecast stream. Generating new humidity forecasts needs the V5 pipeline and
its own CatBoost/LightGBM runtime described in [V5](../../v5/README.md).

## Compose aligned component forecasts

```python
import json
from pathlib import Path
from v7 import compose_forecasts, point_forecasts

folder = Path("v7/output/merged_candidate_20261106")
hourly = json.loads(
    (folder / "humidity_temperature_component.json").read_text(encoding="utf-8")
)["predictions"]
rain = json.loads(
    (folder / "v6_corrected_rainfall_predictions.json").read_text(encoding="utf-8")
)
windows = compose_forecasts(hourly, rain)
points = point_forecasts(hourly)
```

The API inputs are component forecasts, not raw station readings:

| Input | Required fields |
| --- | --- |
| Each hourly V5 row | `station`, `issue`, `time`, `selected_t`, `selected_h`, `humidity_method`; fallback rain also uses `selected_rain` and `selected_rain_probability` |
| Each V6 rain row | `station`, `issue`, `horizon`, `end`, `selected_amount`, `selected_probability`, `selected_amount_method`, `selected_probability_method` |

Times are Unix seconds. All hourly rows must share one issue. Every supplied
station needs hourly coverage through the requested 24-hour range. For each
supplied X50/X66 station, all four V6 rain windows are required.
Other station names receive fallback behavior, not a newly calibrated rain model;
the published station support is X50, X51, X66 and X67.

## Output meanings

| Field | Meaning |
| --- | --- |
| `temperature_c` | Temperature at the window end, degrees C |
| `humidity_pct` | Relative humidity at the window end, percent |
| `rainfall_mm` | Rain amount over the whole window, mm |
| `rain_probability` | Probability that whole-window total reaches 0.28 mm; null when unsupported |
| `horizon` | 1, 6, 12 or 24 hours from issue |
| `issue`, `end` | Unix seconds; the corresponding `*_wib` fields display UTC+7 |
| `*_source`, `*_method` | Component and route used for that output |

A six-hour row has temperature/humidity at hour six and rain total across
hours one through six. It is not an average of six temperature/humidity points.
The four windows overlap and must not be added together.

The bundled JSON/CSV outputs contain 16 combined rows plus 672 separate hourly
temperature/humidity points. The point file intentionally contains no invented
hourly rain series.

## One-time snapshot build

`python v7/run.py build` refuses to overwrite the included frozen output.
It originally used the local X50/X66 CSV exports to construct V6 features, the
frozen GFS forecast and the sibling versions' final models. Those raw exports
are not published. Its original source paths remain in provenance records.

The saved feature snapshot and frozen component forecasts are sufficient for
verification and rainfall replay. They are not a replacement for the original
data needed to rebuild feature extraction.

## A fresh forecast issue

Obtain aligned future V5 hourly outputs and V6 rain outputs from their upstream
pipelines, with actual then-available station context and the same weather input.
Pass those streams to `compose_forecasts`. Do not change the dates on the bundled
snapshot and present it as a new forecast.

V7 currently has no automatic live-data collector, scheduler, retraining job or
one-command end-to-end future forecast pipeline. New data arrival semantics and
prospective forecast evaluation still need to be established.
