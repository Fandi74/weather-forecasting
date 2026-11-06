# V7 component models

These are exact copies of already-trained components, not models fitted by V7.
The frozen [copy audit](../output/merged_candidate_20261106/component_copies.json)
records each source path, destination and SHA-256.

| Path | Role |
| --- | --- |
| `humidity/catboost/humidity.cbm` | V5 CatBoost residual learner targeting X66 hsht |
| `humidity/lightgbm/humidity.txt` | V5 LightGBM residual learner targeting X66 hsht |
| `humidity_selection.json` | V5 equal-third ensemble, including the V2 humidity term |
| `temperature/v2_models.json` | Original V2 parameters, including its baseline corrections |
| `rainfall/local_rain/` | Corrected V6 selected rainfall family |
| `rainfall/local_rain_soil/` | Corrected V6 selected rainfall family |
| `rainfall/network_rain_soil/` | Corrected V6 selected rainfall family |
| `rainfall/baselines.json` | V6 rain-recipe and window-probability controls |
| `rainfall_selection.json` | Unchanged validation-selected V6 routes |
| `rainfall_catalog.json` | Corrected V6 component provenance and timing policy |

The V5 ensemble uses its upstream feature preparation and V2 humidity component.
V7 preserves the resulting forecast stream; its rainfall replay does not execute
new CatBoost humidity inference. The rain family files contain an occurrence
model, positive-amount model and feature descriptor. See the
[architecture](../docs/ARCHITECTURE.md) and [limitations](../docs/LIMITATIONS.md).
