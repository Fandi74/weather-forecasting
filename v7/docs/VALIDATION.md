# V7 validation and reproducibility

The checks below validate the composition and artifact integrity. They are
distinct from a prospective weather-accuracy benchmark.

| Check | Result |
| --- | --- |
| V7 integration tests | 11 pass |
| Frozen V7 files | 32 verify |
| Earlier V2–V6 frozen files | 535 unchanged |
| Copied model/selection files | 16 match their recorded sources |
| Hourly temperature/humidity | 672 points exactly match V5 |
| Independent point-value checks | 1,344 binary-float comparisons |
| Combined window-end temperature/humidity | 32 independent binary-float comparisons |
| Combined output coverage | 16 rows, four stations × four windows |
| Corrected V6 rain inference | Eight windows reproduce identically |
| Feature timestamp checks | Used measurements/assumed availability do not exceed issue |

The integration tests cover shared issue/end times, duplicate and missing
coverage, rain bounds, unchanged point values, direct V6 window values and
fallback probability semantics. Standard-library package verification checks
the publication manifest, frozen locks, dependency hashes and source model copies.

The saved [local validation record](../validation_20261106.json) predates
publication and keeps that historical status. The [publication manifest](../publication.json)
records the published snapshot. A replay scratch-path fix in the current CLI
keeps temporary files under V7; the original build-time source snapshot is
retained without changing predictions or models.

## What model replay verifies

`python v7/run.py replay` runs the copied V6 final models on the saved feature
snapshot and compares the full result with the frozen rain component.
V5 temperature/humidity values are checked against their frozen source.
The replay does not rerun the bundled CatBoost humidity model, gather fresh
observations or evaluate predictions against new measurements.

## Inherited evidence

V5 selected its X66 equal-third humidity ensemble using October development
validation. The already-revealed November humidity comparison was a diagnostic.
See [the V5 training report](../../v5/output/benchmark_20261103_humidity_v5/training_report.md)
and [November comparison](../../v5/output/evaluation_20261106/report.md).

V6's corrected +1h weekly follow-up did not beat raw GFS on selected rain-amount
RMSE in any of its eight station/window groups. This is an earlier V6 development
comparison, not a V7 score or a test of the new 16-row composition. See
[the V6 clarification report](../../v6/output/e11_corrected_20261106/report.md)
and [independent comparison summary](../../v6/output/e11_correction_independent_verification_20261106.json).

No new V7 accuracy score is asserted. The next accuracy evaluation needs
unseen observations, the intended sensor references, identical weather inputs
and actual then-available station context. Report humidity, rain occurrence and
rain amount separately and retain raw GFS as a rain control.

## Commands

From the full repository root:

```sh
python -m unittest discover -s v7/tests -v
python v7/verify_package.py
python v7/run.py replay
```

The first two commands need only the standard library. Replay requires the
pinned dependencies in [requirements.txt](../requirements.txt).
