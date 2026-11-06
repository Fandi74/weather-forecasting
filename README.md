# Weather forecasting

Research monorepo for local forecasts using Open-Meteo forecasts and physical
weather-station measurements to learn statistical and machine-learning corrections.
The product goal is hourly temperature/humidity and rain probability/amount for
1-, 6-, 12- and 24-hour windows, with a seven-day extension where supported.

## Engine versions

| Folder | Status | Scope |
| --- | --- | --- |
| [versions/v2](versions/v2/README.md) | Frozen original baseline | GFS correction and blind 3–9 November 2026 benchmark |
| [version/v3](version/v3/README.md) | Frozen CatBoost candidate | Existing-input and station-history experiments; selected methods and all trained variants |
| [version/v4](version/v4/README.md) | Frozen LightGBM candidate | Same V2 data and V3 feature design; independently trained LightGBM variants |

Each version owns its source, dependencies, tests and experiment artifacts.
Earlier locked models and predictions are preserved.

## V2, V3 and V4 prediction comparison

All three graphs show **3–9 November 2026**, with 168 hourly intervals for each of
X50, X51, X66 and X67, in **WIB (UTC+7)**. They use the same archived GFS run
initialized on 2 November at 06:00 UTC and matching axis ranges.
**Actual measurements remain withheld; benchmark accuracy is pending.**

### Engine V2

![Engine V2 — frozen hourly predictions, 3–9 November 2026](version/v4/output/benchmark_20261103_lightgbm/graphs/V2_prediction_7days.png)

### Engine V3 — CatBoost

![Engine V3 — frozen hourly predictions, 3–9 November 2026](version/v4/output/benchmark_20261103_lightgbm/graphs/V3_prediction_7days.png)

### Engine V4 — LightGBM

![Engine V4 — frozen hourly predictions, 3–9 November 2026](version/v4/output/benchmark_20261103_lightgbm/graphs/V4_prediction_7days.png)

V3 retains V2 for **X50 rain amount**. V4 retains V2 for **X50/X66 rain amounts**
and **X66 rain probability**. X51/X67 retain raw GFS in all versions. X66 retains the user-selected t/h stream and its sensor
discrepancy warning. Temperature/humidity are interval-end values; rain is the
preceding hour's total. Hourly rain probability means at least 0.28 mm.

## October validation

These values were used to select methods; they are **not untouched final-test accuracy**.

| X50 metric — lower is better | Original V2 | V3 selected method | V4 selected method |
| --- | ---: | ---: | ---: |
| Temperature MAE, °C | 1.748 | 1.704 | 1.696 |
| Humidity MAE, percentage points | 9.748 | 6.219 | 6.831 |
| Rain probability Brier score | 0.1086 | 0.1047 | 0.1056 |
| Rain amount RMSE, mm/hour | 1.670 | 1.670 — V2 retained | 1.670 — V2 retained |

V4 uses V2’s archived observations/forecasts and V3’s feature/evaluation design.
It learns independently; CatBoost predictions and weights are not training inputs.
V3/V4 training-row signatures and frozen feature values match exactly.

The history-only experiment has a matched exact-run control. At the frozen issue,
station readings are about nine hours old; expired latest/rolling features remain
missing. The larger X66 improvements measure agreement with its flagged sensor
stream. Joint 6/12/24-hour probabilities and 50 km spatial transfer remain unproven.

Read the [V4 training report](version/v4/output/benchmark_20261103_lightgbm/training_report.md),
[V4 validation graph](version/v4/output/benchmark_20261103_lightgbm/validation.png),
[V3 training report](version/v3/output/benchmark_20261103_catboost/training_report.md),
[V2 baseline report](versions/v2/output/engine_v2/benchmark_20261103/baseline_report.md),
and [confirmed product scope](docs/PROJECT.md).

## Verify and run

```sh
# Verify all three frozen snapshots and comparison graphs; Python standard library only.
python version/v4/verify_package.py
```

See [V2 instructions](versions/v2/README.md), [V3 instructions](version/v3/README.md)
and [V4 instructions](version/v4/README.md)
for dependencies, tests and data requirements. V3's internal identifier remains
`engine_v2_catboost.1` to preserve the original sealed experiment.

## Data and provenance

The repository includes source, trained models, frozen forecasts, reports, plots,
derived GFS history and sealed packages. Raw station exports, raw provider-response
archives, local databases and runtime/download caches remain outside Git.
Some original provenance records contain local filesystem paths and historical
pre-publication notes. See [V2 data requirements](versions/v2/DATA.md).

Open-Meteo weather-data attribution: https://open-meteo.com/ (CC BY 4.0).
No software license has been selected for this repository.
