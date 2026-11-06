# Data contract for the real-data phase

These are proposed normalized product fields, not telemetry-key names. X50 already has a local import/database; the complete forecast pipeline and product response below are not implemented. Updated scope is in [PROJECT.md](PROJECT.md); existing demo semantics are explicitly identified below.

## Observations

| Field | Meaning |
| --- | --- |
| station_id | Stable identity mapped to a ThingsBoard device ID |
| observed_at_utc | Original sensor timestamp, never replaced by upload time |
| received_at_utc | When the record became available to the forecasting pipeline |
| interval_start_utc / interval_end_utc | Measurement/accumulation interval, where applicable |
| temperature_c | Temperature, retaining original units and sensor metadata separately |
| relative_humidity_pct | Relative humidity, 0–100 percent |
| rain_counter_mm | Original cumulative counter, if confirmed as such |
| rain_interval_mm | Derived only when counter and reset semantics are established |
| pressure_hpa / pressure_type | Keep station pressure separate from mean-sea-level pressure |
| illuminance_lux | Measured light level; do not relabel as W/m² |
| quality_by_variable | good / missing / faulty / stale / suspect / reset / gap |
| provenance | Source record ID, import batch, original units and raw-record reference |

Duplicate timestamps need a documented conflict policy. A failed rain sensor is not a zero rainfall observation. An hourly rain total needs valid interval coverage; it must not silently skip gaps. A mean temperature/humidity value must report coverage and use the same temporal definition as its forecast target.

Hourly batch uploads retain the six original 10-minute timestamps. When reconstructing past forecast issuance, a reading is usable only once it was actually available. If old arrival times are unknown, use a declared conservative delay assumption and do not silently treat those records as real-time.

Counter differencing must handle resets, wraparound, replacement gauges and missing samples. The prototype helper returns missing at resets and gaps; a later adapter can use verified reset metadata to recover defensible values. Never infer a dry spell from a broken gauge.

## Forecast snapshots

Store provider, model family/version, station/query coordinate, returned grid/source coordinate, elevation and its provenance, run identifier, initialized_at_utc, published/available_at_utc when known, service_issued_at_utc, fetched_at_utc, target interval, variable, value, unit and raw payload reference. Initialization, publication, retrieval and service issuance are different events; unknown times remain unknown. Add first_seen_at_utc when archiving operational responses.

Archive each run without updating old forecast values when newer runs arrive. A retrieval timestamp is not a model run time. APIs sharing the same upstream run are related evidence.

Precipitation totals, rates and probabilities have different semantics. Store probability event threshold and interval. Do not add hourly probabilities into daily probability, or assume independence between hours.

For the prototype only, hourly chart and CSV timestamps identify the start of each forecast hour; correction lead bands use the end of that hour. The fixed scenario begins 30 October 2026 at 07:00 WIB. Real adapters must explicitly carry both interval endpoints before comparison.

## Calibration pairs and evaluation

Each pair identifies station, variable, forecast run, raw/ensemble recipe version, issued time, target time/interval, observation arrival time, observed value and quality.

Fit only pairs with target and arrival times strictly before the training cutoff. Deduplicate verification times within each station/variable/lead band. Reject negative lead times and invalid measurements. Evaluation must use a model fitted no later than the forecast issue time.

Train corrections against the exact blend/model recipe used at prediction time. Refit or invalidate corrections when the source recipe changes. The prototype recalculates its synthetic training blend when source controls change.

Use rolling temporal evaluation for real data; do not randomly shuffle timestamps. Record sample counts, missing coverage and rain-event counts. Compare raw and corrected forecasts on identical valid pairs, including unadjusted fallback cases when judging overall system performance.

The current demo's calibration table reports only eligible corrected models. It does not claim an overall system improvement or a score for missing sensor targets.

## Location-specific forecast response: proposed

The target is the user's local location, including places without a station. Retain target coordinate, location precision, resolved timezone, source/model recipe, forecast issue time, retrieval/age, model version and correction status/reason. Station support is variable- and horizon-specific; correction can be unsupported while a raw forecast remains available.

Rain windows are 1, 6, 12 and 24 whole hours with explicit window_start_utc and window_end_utc. At 10:23 local time, the first complete window is 11:00–12:00. A provider precipitation value timestamped 12:00 describes the preceding hour; do not relabel its 11:00 value as that interval.

Probabilities need an event definition, threshold, comparison operator, units and interval. Record whether the event concerns window-total rain or any wet hour. Missing window probabilities remain unavailable; hourly probabilities do not establish their joint distribution. Amounts identify raw deterministic values, predictive means or conditional amounts; quantiles need levels and validation status.

Temperature/humidity have hourly valid instants, not accumulated-rain intervals. Match observations with a declared sampling/tolerance rule and retain coverage/time offsets. Support each target's timezone; fixed Asia/Jakarta timestamps belong to the Garut demo.

## User rain-status feedback: later phase

Proposed fields: report_id, pseudonymous_reporter_id, status (`dry`, `rain`, `heavy_rain`), observed_at_utc, received_at_utc, location/cell, location_accuracy_m, duplicate/quality flags and provenance. No numerical rain amount is requested or inferred. Missing reports do not mean dry. Twenty reports/day is illustrative volume, not a cap or guaranteed independent sample count.

Keep reports separate from gauges. Only reports received before issuance may become features in a later feedback model; evaluate using independent outcomes. Initial forecasting uses Open-Meteo and station measurements only.

## Integration boundary

Future network adapters run on the server. Browser clients never receive provider or station-service credentials, request URLs containing keys, or raw privileged errors. Local credentials belong in environment configuration excluded from version control. ThingsBoard-specific integration is outside the revised scope. The current static sample application contains no credentials, login flow, real API calls or background scheduler.
