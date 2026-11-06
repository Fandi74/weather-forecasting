# Engine V6: rainfall and soil-response research

V6 investigates 1/6/12/24-hour rainfall forecasts using the supplied X50 and X66
exports from 6 August through 6 November 2026. Temperature and humidity retain
V5 unchanged. No earlier version is edited and no GitHub publication is automatic.

## Current findings

**V6 remains experimental. Rainfall amount is not consistently more accurate than
raw GFS.** Nearby recent gauge rain is the more consistent occurrence signal;
adding every soil feature has not shown a reliable extra gain.

| Later-period comparison | Original fit | Weekly-refresh follow-up |
| --- | ---: | ---: |
| Selected V6 amount RMSE lower than past-only V2 recipe | 5/8 groups | 3/8 groups |
| Selected V6 amount RMSE lower than raw GFS | 1/8 groups | 0/8 groups |
| Nearby-rain learner Brier lower than weather-only learner | 8/8 groups | 8/8 groups |
| Adding both soil streams improves nearby-rain learner Brier | 0/8 groups | 3/8 groups |

Groups are two stations × four forecast windows, not independent storms. Both
evaluations are retrospective development checks. The weekly schedule was tried
after inspecting the first results, with the original routing/settings unchanged.

With valid soil readings, srm decreased within an hour in 53/65 X50 and 29/35 X66
eligible rain-onset examples. There were also 391 X50 and 96 X66 hourly cases with
a drop of at least 5% while neither checked gauge reported rain nearby. These
are unconfirmed wetting cases; the data alone cannot label their causes.

E11 currently excludes soil signals. At X66, E11 rows still contain raw srm
(3484–4996) while sm is blank. A separate raw-ADC sensitivity gives 33/41 rain
onsets with a one-hour drop, but this bypass is unconfirmed and was not used to
fit or select the current models. The status of raw srm under E11 and packet
arrival timing should be confirmed before the next operational iteration.

Read the [balanced findings and control comparison](output/review_20261106/review.md),
[original model report](output/rainfall_candidate_20261106/report.md),
[three-month pattern graph](output/rainfall_candidate_20261106/rain_soil_patterns_3months.png),
[rain/mirrored-SRM examples](output/review_20261106/wetting_examples.png),
and [independent numerical checks](output/review_20261106/independent_verification.json).

The selected final rainfall models are in
`output/rainfall_candidate_20261106/models/final/`. All 315 earlier locked files,
64 initial V6 files and 672 V5 temperature/humidity rows verify unchanged. Eleven
V6 tests passed before training. Nothing has been pushed to GitHub.

The two stations are approximately 3.56 km apart. Their rainfall and soil signals
provide complementary inputs; each target keeps its own independent gauge labels.
Rain and manual fertigation may both reduce `srm`. Soil drops are evidence of
wetting, not confirmed rain or a measured rainfall amount.

V6 compares five fixed LightGBM hurdle designs: GFS only, own rain history, own
rain plus soil, both gauges, and both gauges plus soil. Predictors use only readings
available before the forecast issue (measurement plus one hour receipt assumption).
Recent soil values expire after six hours. Future soil response is used only in
descriptive pattern analysis, never as a forecast predictor.

Gauge labels use checked `rf` millimetres and `rfc` at 0.28 mm/tip. Where packets
are missing, valid boundary counters and continuous record IDs may recover a whole
window total. Missing within-gap timing is not imputed and neighbor rain is never
copied into target labels. E11 invalidates the soil fields; unrelated flags do not
invalidate the rain gauge.

Training ends before 1 October. Validation on 1–19 October selects components per
station/window; the later 20 October–2 November period is then scored with that
selection fixed. All split boundaries purge labels not yet received. Earlier
November data is an additional development diagnostic, not a blind test.

Historical replay uses the latest archived weekly GFS snapshot between issues.
It does not invent hourly GFS refreshes. The V2 recipe comparison is refitted on
the same earlier period, rather than applying its final November parameters to
earlier outcomes. Window probabilities are fitted directly, not summed from
hourly probabilities. Separate window/component selections are a research
prototype and do not establish a coherent joint predictive distribution.

```sh
python -m unittest discover -s v6/tests -v
python v6/run.py build
python v6/run.py verify
```

Use the existing LightGBM/NumPy/matplotlib environment. Raw source files and the
original local GFS archive are needed to build. A locked output cannot be rebuilt;
new experiments require a different `--output` directory.
