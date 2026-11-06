# Engine V2

This version preserves the existing Python engine and the locked GFS experiment.
Its internal folder layout is retained so paths and benchmark hashes remain valid.
Run all commands below from `versions/v2`.

## Install and test

Requires Python 3.10 or newer. A virtual environment is recommended.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p test_engine_v2.py -v
python engine_v2/run.py verify
```

The last command checks the immutable benchmark files included in this repository;
it does not require raw training data or access to the original computer.

## Contents

- `engine_v2/`: collector, station inventory/quality checks, fitting, prediction,
  plotting, scoring, configuration and original experiment documentation.
- `tests/`: existing V2 tests, including cutoff and no-refit checks.
- `output/engine_v2/benchmark_20261103/`: locked models, 672 hourly forecasts,
  1/6/12/24-hour initial rain totals, daily summaries, reports, plots, annual
  derived GFS tables, source snapshot and checksum lock.
- `output/engine_v2/engine_v2_frozen_benchmark_20261103.zip`: original sealed package.

## Score withheld actuals

Arrange new CSV exports in station-named folders under a separate source directory.

```sh
python engine_v2/run.py score --source-root /path/to/new-actual-exports
```

Scoring verifies the lock, reads new observations and writes separate timestamped
results. It does not refit or replace the frozen models. A complete week needs
readings through 10 November 2026, 00:00 WIB, to close the last rain interval.

## Research boundaries

The forecast is a retrospective reconstruction using the 2 November 2026 06 UTC
GFS run. Publication timing is assumed rather than independently verified.
Temperature/humidity are interval-end values; rain is the preceding hour's total.
Hourly rain probability means at least 0.28 mm/hour. Joint 6/12/24-hour probabilities
are unavailable. X66 retains the user-selected t/h stream despite its discrepancy
with the secondary sensor. Transfer to locations 50 km away is unproven.

See [data dependencies](DATA.md) and the [original engine notes](engine_v2/README.md).
The original notes retain workstation-specific paths as historical documentation;
the portable commands above are the repository entry point.
