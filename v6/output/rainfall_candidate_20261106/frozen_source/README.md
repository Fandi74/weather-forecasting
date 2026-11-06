# Engine V6: rainfall and soil-response research

V6 investigates 1/6/12/24-hour rainfall forecasts using the supplied X50 and X66
exports from 6 August through 6 November 2026. Temperature and humidity retain
V5 unchanged. No earlier version is edited and no GitHub publication is automatic.

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
