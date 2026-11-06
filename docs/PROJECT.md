# Weather forecasting system: confirmed product goals

Updated 5 November 2026 from the user's revised requirements. This scope supersedes the original Garut-only, station-dashboard and mandatory seven-day product plan. Existing prototype behavior is described separately below.

## Main goal

Provide users with forecasts for their own location: rain probability and expected amount over the next 1, 6, 12 and 24 hours, plus hourly temperature and relative humidity. Improve Open-Meteo forecasts using the installed weather station network, and later incorporate users' local rain-status reports as additional evidence.

The product is applicable wherever deployed, especially in Indonesia. Garut is the pilot network, not the product's geographic boundary. A user in Majalengka receives their local Majalengka forecast; a user in Tasikmalaya receives their local Tasikmalaya forecast.

## Confirmed initial scope

- Research prototype first, on the current computer. Production scale and commercial operation are later decisions.
- Two weather inputs: Open-Meteo forecasts and measurements from installed weather stations. Stations teach corrections to Open-Meteo forecasts; original measurements remain unchanged.
- Rain timing, occurrence probability and amount are the first priority. Hourly temperature and relative humidity are also required.
- Rain summaries cover 1, 6, 12 and 24 hours. These are forecast/accumulation windows, not four update frequencies.
- Use whole-hour windows initially, with actual start/end times. At 10:23, the next complete hour is 11:00–12:00 and a six-hour window is 11:00–17:00. Do not describe these as starting exactly now.
- Seven-day forecasts are optional.
- Resolve the user's local timezone; use UTC internally. Indonesia-wide support must not assume every user is in WIB.
- ThingsBoard integration is outside the current scope. Its exported data remains useful historical input.
- Other previously investigated providers are optional future comparisons, not required production inputs.

The rain-event threshold, predictive ranges, product name, location-acquisition interface and refresh schedule remain design choices to validate. See [research and recommended design](FORECAST_RESEARCH_2026-11-05.md).

## Spatial correction is a core research objective

Investigate whether the station network can improve forecasts at a location without a station, including a target approximately 50 km from the network. The target retains its own Open-Meteo forecast. A station's measurements are not substituted as the target's weather.

Distance, terrain, elevation, season, forecast lead, sensor reliability and observation age may affect transfer. No universal correction radius or improvement at 50 km has been established. Test transfer against observations withheld at genuinely different locations. Use raw-forecast fallback where correction has insufficient evidence.

## User feedback: later third input

Users can report current local conditions as `dry`, `rain` or `heavy_rain`. Reports need observation time and location. These are qualitative status reports, not measured rainfall amounts or numerical rain-gauge replacements.

Approximately 20 reports per day was an example volume, not a confirmed submission cap, guaranteed rate or number of independent observations. Feedback is a later phase; initial forecast calculations use the two inputs above. Potential future uses include occurrence checking, identifying local misses and short-range updates after quality assessment.

## Pilot station metadata

The user supplied these coordinates on 5 November 2026. They supersede older candidate GPS fixes for new station-specific requests. Historical position changes remain unknown; retain original export provenance.

| Station | Latitude | Longitude | Provided elevation, m above sea level | Data-readiness notes |
| --- | ---: | ---: | ---: | --- |
| X50-Nunang | -7.397703 | 107.833976 | 1230, estimated | Historical CSV imported; current feed and latest health not checked |
| X51-Wawan | -7.371024609 | 107.8115768 | 1190 | Export confirms history through 25 August 2026; no October validation |
| X66-Adis | -7.372810364 | 107.8136597 | 1299 | History through 2 November prepared for engine v2; t/h retained by user despite discrepancy with tsht/hsht |
| X67-Ucu | -7.404071808 | 107.8261642 | 1161 | Supplied export duplicates X66 and is excluded as X67 truth; earlier rain-fault report remains unverified |

Elevations are user-provided, not independently surveyed; X50's is explicitly estimated. Great-circle separations range from about 0.304 km (X51–X66) to 4.011 km (X51–X67), using Earth radius 6371 km. This clustered network cannot by itself verify transfer over 50 km.

Hardware is custom. Previously confirmed sampling is every 10 minutes, with six readings sent hourly while retaining original measurement times. Current transport latency still needs verification.

## Existing assets and limitations

- X50 has 56,458 imported readings, an archived original CSV, normalized SQLite records and field-specific quality flags. See [X50 import notes](X50_IMPORT.md).
- Verified X50 semantics: `t` in °C; `h` in percent; `ap` in hPa with pressure type unconfirmed; `rf` already in mm; `rfc` is a tip counter at 0.28 mm/tip. E2 flags temperature/humidity/pressure, E4 rainfall, E5 lux and E16 GPS. Unknown codes remain flagged for review.
- A year of GFS and ECMWF fixed-day-lead archives exists for the old Cisurupan area reference, not these station coordinates. It is exploratory material, not yet aligned training data for the revised product.
- Saved X50 CSV forecasts from 3 November use Open-Meteo Best Match at an earlier CSV GPS fix. They have no fitted X50 correction.
- The local dashboard contains real X50 descriptive history, but forecast/calibration examples are synthetic. Its original station/seven-day views are demonstration features, not this revised product specification.
- `dashboard/engine.mjs` implements an available-source average, shrunk temperature/humidity residual and shrunk rain-amount ratio. Constants 72 and 30, bounds and sample thresholds are prototype choices, not validated values. Real probability calibration, spatial transfer and rain-onset correction are not implemented.
- A fresh offline engine v2 now has a real-data GFS training/validation experiment. Its [3–9 November benchmark report](../output/engine_v2/benchmark_20261103/baseline_report.md) separates earlier validation from deliberately withheld November actuals. No prospective November improvement, spatial operating radius or production service has been demonstrated.

## Next sequence

1. Inventory per-variable history and current sensor status for all four stations; preserve timestamps, units, faults and metadata.
2. Obtain matching, versioned Open-Meteo data at each confirmed station coordinate. Preserve run, initialization, availability/retrieval, target interval and model identity. Begin archiving useful ensemble trajectories.
3. Define measurable rain events and aligned whole-hour evaluation targets. Match temperature/humidity instants separately from accumulated rainfall.
4. Measure raw Best Match, explicit models, simple averages and suitable probability baselines on identical valid cases.
5. Test small corrections with rolling temporal evaluation and wholly withheld locations. Tune on training/validation data; reserve later dates for final testing.
6. Enable corrections by variable, horizon and supported location only when evidence supports them. Retain honest raw fallback and freshness.
7. Obtain independent observations near distant target areas to assess the 50 km objective. A temporary verification station remains part of the station-network input category.
8. Build the location-specific research interface after establishing the data/evaluation contract. Add feedback and test its incremental value in a later phase.
