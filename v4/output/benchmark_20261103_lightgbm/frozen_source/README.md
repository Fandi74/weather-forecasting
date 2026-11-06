# Engine V4 — LightGBM

V4 uses V2's archived GFS and station dataset, and V3's experiment design/features.
Its LightGBM models are trained independently. V3's saved predictions are used only
as a comparison, never as training targets or predictor features. V2/V3 stay frozen.
No GitHub push is performed.

Three variants use the same training rows as their V3 counterparts: existing
inputs/full V2 dataset, existing inputs/exact weekly runs, and station-history
features/exact weekly runs. Feature definitions and initial contexts are identical.
LightGBM uses one fixed, modest CPU configuration: 400 rounds, depth 4, 15 leaves,
learning rate 0.04, L2 10 and at least 50 rows per leaf. No tuning or early stopping.

Validation fitting ends before 1 October; four October weekly forecasts select
methods. Final fitting uses only labels/assumed arrivals before 3 November midnight
WIB. The forecast uses the same 2 November 06 UTC GFS run as V2/V3 for 3–9 November.
October results are selection evidence, not an untouched test. November observations
remain withheld. V4 may retain V2 or raw forecasts for a component where LightGBM
does not improve the declared metric. V3 is excluded from V4 component selection.

From the workspace root, using the isolated local environment:

```powershell
$v4Python = './version/v4/.venv/Scripts/python.exe'
& $v4Python -m unittest discover -s version/v4/tests -v
& $v4Python version/v4/run.py build
& $v4Python version/v4/run.py verify
& $v4Python version/v4/run.py lock
```

The output is `version/v4/output/benchmark_20261103_lightgbm/`. Build needs the
existing V2 raw archive and normalized observations, plus V3's locked experiment.
Each new experiment needs its own empty output directory; a locked candidate
cannot be overwritten. Later `score --source-root PATH` verifies locks and uses
new measurements only for scoring, never for refitting.

Missing station histories are explicit. At the frozen issue, X50/X66 readings are
about nine hours old, so the inherited six-hour expiry masks latest/rolling values.
X66 retains its t/h discrepancy; X51/X67 lack October support and retain raw GFS.
Hourly rain event is >=0.28 mm. Joint 6/12/24-hour probabilities remain unavailable.

Before locking, generate the shared-scale V2/V3/V4 graphs:

```powershell
& $v4Python version/v4/make_graphs.py
```

The graph renderer refuses to overwrite a locked experiment. The resulting
`graphs/V4_prediction_7days.png` uses the selected V4 components, with retained
V2/raw components identified. Graphs and source are included in the candidate lock.
