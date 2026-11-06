# Engine V5: humidity improvement

V5 keeps **V2 temperature, rainfall amount and rain probability exactly unchanged**.
Only humidity can change. The first supported station is X66, which has independent
historical `hsht` readings from June through 2 November 2026. Other stations retain
their V2 humidity output until equivalent training/validation evidence exists.

The humidity target is `hsht`, not `h`. V5 combines V2's humidity baseline with
new humidity-only CatBoost and LightGBM learners based on V3/V4's residual-model
designs. These new learners are trained against SHT humidity; the old V3/V4 models
and their predictions remain frozen. Forecast inputs are GFS temperature/humidity/
rain, local hour and lead day, plus then-available SHT humidity history/errors.

Two later October weekly forecasts evaluate eight small candidate combinations.
Learned weights use only earlier available October outcomes. A humidity update must
beat V2's development MAE by at least 0.5 percentage points to activate. Final
humidity fits use only labels/assumed arrivals before 3 November 00:00 WIB. No
November measurements are used to fit or select the candidate.

The 3–6 November outcomes have already been discussed, so that comparison is a
development diagnostic. Confirmation requires later observations unseen when V5
is sealed. Historical forecast publication/receipt timings remain assumptions.

## Run locally

The current workspace already has separate CatBoost and LightGBM environments.
The driver reuses those interpreters without changing them; explicit interpreter
paths can be supplied. A single environment with both packages also works.

```powershell
& ./version/v4/.venv/Scripts/python.exe -m unittest discover -s v5/tests -v
& ./version/v4/.venv/Scripts/python.exe v5/run.py build
& ./version/v4/.venv/Scripts/python.exe v5/run.py verify
& ./version/v4/.venv/Scripts/python.exe v5/run.py score --actuals C:/path/to/new-X66.csv
```

Never rebuild a locked output. New experiments require a different `--output`.
Training reads the existing local raw station/GFS archives; those private inputs
are not silently replaced by later station exports. Source hashes, availability
audits, learned weights, predictions and original-reference checks are recorded.

## Version boundaries

- V2/V3/V4 stay frozen; V5 is a separate top-level folder.
- V5 does not train temperature or rain models, and does not use `sm`/`srm`.
- V6 is reserved for rainfall work and comparison with `sm`/`srm`.
- No GitHub publication is performed by these commands. Future publication uses
  `main` with separate top-level version folders.
