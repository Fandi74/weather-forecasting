# Engine V2 CatBoost candidate

Separate local experiment beside the immutable Engine V2 baseline. No GitHub push.
Three variants are trained: existing inputs/full V2 dataset, existing inputs/exact
weekly runs, and station-history features on the identical exact-run training rows.
The matched exact-only pair isolates the added value of history features.

Run from the workspace root with Python 3.10+ and the dependencies in requirements.txt.
The local `.venv` is isolated and excluded from Git.

```powershell
$cbPython = './versions/v2_catboost/.venv/Scripts/python.exe'
& $cbPython -m unittest discover -s versions/v2_catboost/tests -v
& $cbPython versions/v2_catboost/run.py build
& $cbPython versions/v2_catboost/run.py verify
& $cbPython versions/v2_catboost/run.py lock
```

Build requires the existing `engine_v2/` source, original locked benchmark at
`output/engine_v2/benchmark_20261103/`, raw GFS archives and normalized observations
at `data/engine_v2/`. A monorepo workspace can instead contain the baseline under
`versions/v2/`; pass `--workspace` to select its containing workspace.
No new forecasts are downloaded. Newly supplied actual exports are never opened
during build. Original V2 source, model parameters and outputs are never rewritten.

The output defaults to `versions/v2_catboost/output/benchmark_20261103_catboost/`.
`training_report.md` explains the comparison, limitations and selected components.
Original V2's October-selected recipe is reconstructed using pre-October fitted
parameters for validation; the November-trained frozen parameters are not applied
to October targets. October scores select methods and are not an untouched test.

The frozen benchmark covers 168 hours at four locations from 3 November 00:00 WIB
through 10 November 00:00 WIB. GFS initialization is the same 2 November 06 UTC run
used by original V2. November observations are still withheld. All feature histories
for the entire forecast are fixed at the initial issue, using V2's assumed
measurement-plus-one-hour arrival delay. Actual historical receipts are unavailable.

X51/X67 keep raw fallback because they have no eligible October validation. X66
retains the user-selected t/h stream with the sensor discrepancy prominently flagged.
Hourly rain event threshold is 0.28 mm. Joint 6/12/24-hour probabilities remain
unavailable. Corrections at arbitrary issue hours or distant locations are untested.

To score withheld actuals later, use a new station-folder source directory:

```powershell
& $cbPython versions/v2_catboost/run.py score --source-root 'PATH_TO_NEW_ACTUAL_EXPORTS'
```

Scoring verifies the lock and writes separate timestamped reports. It never fits
models or replaces frozen predictions. A locked candidate cannot be rebuilt.

If the correct X67 device identity is supplied later, pass `--device-map` with a
JSON mapping such as `{"X67":"CONFIRMED_DEVICE_ID"}`. This changes only observation
matching during scoring; frozen models and predictions remain unchanged.

The final X50/X66 input readings are about nine hours old at the benchmark issue.
Their latest/rolling station values expire under the six-hour feature rule; the
history variant receives missing values plus ages and available recent-error
features. Its October gains may not transfer to this less recent context.
