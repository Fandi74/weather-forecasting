# Weather forecasting

Research monorepo for local forecasts using Open-Meteo forecasts and physical
weather-station measurements to learn statistical and machine-learning corrections.
The product goal is hourly temperature/humidity and rain probability/amount for
1-, 6-, 12- and 24-hour windows, with a seven-day extension where supported.

## Versions

| Folder | Status | Scope |
| --- | --- | --- |
| [versions/v2](versions/v2/README.md) | Frozen research baseline | GFS correction and blind 3–9 November 2026 benchmark |

Each engine version owns its source, dependencies, tests and experiment artifacts.
New versions belong in separate folders under `versions/`; preserve earlier frozen
models and predictions. Engine V1 and proposed future model experiments are not
included in this initial import.

## Engine V2

V2 fits temperature/humidity median-error corrections and rain regression/classification
models from earlier forecast–observation pairs. It selects candidates on October
validation and freezes hourly predictions for four pilot locations. X51/X67 retain
raw GFS fallback. November benchmark accuracy is pending withheld measurements.

Start with the [V2 instructions](versions/v2/README.md),
[baseline report](versions/v2/output/engine_v2/benchmark_20261103/baseline_report.md),
and [confirmed product scope](docs/PROJECT.md).

## Data and provenance

The initial import includes trained models, frozen forecasts, annual derived GFS
tables, quality/provenance reports, graphs and the sealed benchmark ZIP. Source
and frozen experiment files are copied byte-for-byte from the research workspace.
Raw station CSV exports, raw provider-response archives, local databases and
build environments remain outside Git. See [data requirements](versions/v2/DATA.md).
Some historical provenance records contain original local filesystem paths.

Open-Meteo weather-data attribution: https://open-meteo.com/ (CC BY 4.0).
No software license has been selected for this repository.
