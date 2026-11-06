# V7 limitations and interpretation

## 1. A merged product, with no new accuracy result

V7 reuses V5 and corrected V6. It does not train or select a new joint model.
The merge tests establish correct composition and reproducibility, not improved
weather accuracy. V6 rain amount has not consistently beaten raw GFS, so V7
must not be described as a validated rainfall improvement.

V5's reported X66 humidity gain belongs to its earlier experiment. It is not
evidence of improvement in every variable, station, season or forecast horizon.
See [validation evidence](VALIDATION.md).

## 2. Retrospective data and evaluation boundaries

The included forecast issue is 3 November 2026 00:00 WIB; it is not a current
live forecast. November observations had already been revealed when V7 was
assembled. No new fitting or model selection is performed in V7, but that does
not turn the snapshot into an untouched blind test.

V6 weekly/E11 follow-ups were development experiments after earlier results
were inspected. Its overlapping hourly-issued windows are not independent
storms. The V7 graph has no measured observations or accuracy scoring; it only
compares component predictions. A prospective evaluation on unseen observations
is still required for the combined product.

## 3. Station and sensor-reference limits

The V5 humidity ensemble targets `hsht` at X66. X50, X51 and X67 retain existing
humidity behavior. V6 rain models cover X50/X66; X51/X67 use existing fallbacks.
There is no demonstrated spatial transfer to those stations or arbitrary farms.

Temperature remains V2, with its original training reference. V7 does not retrain
temperature against `(t + tsht) / 2`. Evaluation against a different reference
must state that change and must not be mistaken for unchanged-target accuracy.
Sensor disagreement, calibration and flags remain part of the inherited data
limitations.

## 4. Soil wetting is ambiguous

Rain and manual fertigation can both lower `srm`. An SRM drop alone cannot
establish rain, identify the irrigation cause or supply rainfall millimetres.
Neighboring gauges provide context, not interchangeable ground truth. The two
sites can receive different amounts even when they are only about 3.56 km apart.

E11 is treated as the user-described threshold flag. Available finite positive
raw `srm` is retained, while unavailable `sm` stays missing. The approximate
7000 threshold is not imposed, and its precise firmware meaning is unconfirmed.
A retained raw ADC value is not proof of sensor calibration or unrestricted
measurement accuracy. E3/E12 are treated according to the user's false-error
instruction; unrelated sensor flags do not invalidate the rain gauge.

## 5. Observation timing remains an assumption

The export contains assigned timestamps and their equivalent WIB display,
without a separate arrival field. It does not establish device-measurement
versus server-receipt semantics. V7 retains the conservative V6 +1h feature
availability assumption. It does not promote the immediate-CSV-time sensitivity.

No timestamp after issue is used as a forecast feature, but that check does
not prove real delivery latency. Soil/recent-rain values can be stale or missing;
V6's inherited recent-value expiry is six hours. Live arrival timestamps should
be established before using the replay as evidence of near-term operational skill.

## 6. Rain windows are separate, overlapping predictions

Each 1/6/12/24-hour amount covers the entire window after issue. They are not
disjoint periods and must not be summed or divided into guessed hourly amounts.

V6 fits/selects windows and amount/probability routes separately. Their results
do not establish a coherent joint distribution; monotonic nested-window
probabilities/totals and consistency between selected amount and selected
probability are not guaranteed by the composition layer.

X51/X67 have no supported multi-hour occurrence model in this package.
Their multi-hour probabilities are null, not zero and not estimates formed
by adding hourly probabilities or assuming independent rain events.

## 7. Archived GFS and observation gaps

Historical V6 replay reuses the latest archived weekly GFS snapshot between
recorded snapshot issues. It does not simulate newly refreshed hourly provider
runs. Snapshot issue time and model-run initialization are distinct metadata.

The original gauge exports have gaps, flags and counter discontinuities.
Earlier V6 processing can recover certain whole-window amounts using valid
counter endpoints and record continuity; it cannot recover unknown within-gap
rain timing. Gauge targets are not filled by copying a neighboring station.

## 8. Runtime, data and scope

V7 needs sibling versions in this monorepo. Its bundled models do not make
`v7/` alone a complete independent service. Verification needs the prior frozen
packages; rainfall replay needs their source helpers and the pinned ML runtime.

Raw station exports and provider-response archives remain local. The published
features support replay, not complete raw-data reconstruction. CatBoost humidity
inference is not rerun by V7's rainfall replay; upstream V5 forecasts are copied
and checked exactly.

The package has no live ingestion, forecast scheduling, automatic model refresh,
uncertainty intervals or new fertigation decision policy. Additional deployment
work and prospective evaluation are separate tasks.
