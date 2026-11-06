# Engine v2: blinded GFS baseline

Fresh Python implementation, independent of `dashboard/engine.mjs`.

The benchmark is frozen at **3 November 2026, 00:00 WIB**, for 168 hourly rain intervals ending through **10 November, 00:00 WIB**. Temperature/humidity refer to interval-end instants. No November 3/4/5 GFS update or benchmark observation enters model fitting.

## Research design

- Downloaded GFS history: 3 November 2025–2 November 2026, at four user-confirmed coordinates/elevations. Seven fixed day-lead series per variable; monthly archives retain provenance/checksums.
- Thirty earlier exact weekly GFS runs: weekly simulated issues from 7 April–27 October, each using the prior day's 06 UTC initialization. These add matching seven-day examples and supply exact-run October validation.
- Candidate training cutoff: 1 October. Selection: exact weekly issues 6/13/20/27 October, with observations received before the November cutoff. Final fit: all eligible pre-cutoff pairs.
- Annual fixed-day lead rows are representatives of forecast-day bands, not exact subdaily leads. Exact earlier run rows are preferred for a matching station/target/day band, and validation tests the transfer to real seven-day run trajectories.
- Temperature/humidity: raw, median-residual or day/hour median-residual, selected by validation MAE.
- Rain amount: raw, nonnegative least-squares slope or a two-part regularized occurrence/positive-amount model, selected by validation RMSE. No legacy 72/30 shrinkage constants.
- Hourly event probability: regularized logistic regression versus training-only climatology; threshold ≥0.28 mm/hour, selected by Brier score. It is not the provider's >0.1 mm event. Joint 6/12/24-hour probabilities remain unavailable.
- Minimum training pairs 168, validation pairs 48 and local-hour residual pairs 8 are explicit prototype support guards, not proven sufficiency thresholds.
- Observations: BME280 t/h only; six valid checked rain intervals/hour; missing/gaps/resets excluded; hourly arrival-delay assumption retained.
- The supplied X67 export belongs to X66 and is excluded as X67 truth. X51 has no October observations. Both receive raw forecast fallback.
- X66's t/h disagrees with tsht/hsht in recent history. The user explicitly retained t/h for this benchmark. The report flags this reference uncertainty rather than replacing sensors or hiding the large temperature error.
- The final 2 November 06 UTC run is reconstructed retrospectively. A six-hour availability assumption gives a margin before the simulated freeze, but actual historical Open-Meteo availability was not independently verified.

## Commands

Use the bundled Python executable returned by Codex workspace dependencies; NumPy is required. Matplotlib is used for plots, with the existing local plotting dependency as a fallback when it is absent from the bundled runtime. Run from the project directory. These commands use the configured Python rather than a different system installation.

```powershell
$v2Python = 'C:/Users/isnad/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $v2Python engine_v2/collect.py --phase all
& $v2Python engine_v2/inventory.py --source-root "C:/Users/isnad/Documents/Dayatani/Forecast Data"
& $v2Python engine_v2/run.py build --source-root "C:/Users/isnad/Documents/Dayatani/Forecast Data"
& $v2Python -m unittest discover -s tests -p test_engine_v2.py -v
& $v2Python engine_v2/verify.py
& $v2Python engine_v2/run.py lock
& $v2Python engine_v2/run.py verify
```

The first build is followed by review and locking. A build refuses to overwrite a locked benchmark. Locked source code, model parameters, forecasts and training/input checksums are preserved. Use a different version/output for a later model; never change this benchmark after revealing actuals.

Before locking, run `python engine_v2/verify.py` and review the plotted forecasts and baseline report. This checks the year/weekly coverage, cutoffs, source hashes, prediction ranges, output totals and selected fallbacks, then writes `verification.json`.

## Later scoring

Place the newly supplied actual exports in station-named folders under a new source root. Historical overlap is accepted only when records agree. Correct station identities are required.

```powershell
& $v2Python engine_v2/run.py score --source-root "PATH_TO_NEW_ACTUAL_EXPORTS"
```

Scoring verifies immutable hashes, does not download GFS or refit, and writes a separate timestamped accuracy report, hourly comparisons, 1/6/12/24-hour rain-window metrics and measured-versus-forecast plots. Incomplete hours remain unavailable. Partial weeks are scored only where actual observations exist.

For a complete seven-day rainfall comparison, include the midnight reading at the beginning of 3 November and readings through 10 November, 00:00 WIB. The final reading closes the last rain interval. Keep original device timestamps, counters and error fields.

If the correct X67 device ID becomes available, provide a separate scoring-only JSON map such as `{"X67":"CONFIRMED_DEVICE_ID"}` with `--device-map PATH`. This does not alter the frozen model or forecast.

Primary output: `output/engine_v2/benchmark_20261103/baseline_report.md`. The sealed package is `output/engine_v2/engine_v2_frozen_benchmark_20261103.zip`.
