# Limitations

## Public base-model scope

This package is a limited base model derived from research conducted by its
author while working at a company. The company owns the research and project
intellectual property; its identity is withheld. The public package contains
a subset of the full company system's features. See [ownership and license
scope](../../NOTICE.md).

**Air pressure, light intensity (lux), and UV index are not model inputs in
this release.** Its accuracy is limited, and its reduced feature set may
produce less accurate forecasts than the full system. Additional inputs do
not automatically guarantee higher accuracy. No direct full-system comparison
is included, and no numerical accuracy gap has been established. Public
evaluation percentages must not be presented as measurements of the full
company system.

## Evaluation and operational limits

1. **No new blind benchmark.** The point observations had already been inspected;
   rainfall percentages are earlier rolling-fit development evidence. The
   exported final model has no new combined accuracy result.
2. **Site-specific support.** The humidity ensemble is configured for Site A.
   Direct rainfall routes cover Sites A/B. The other example sites retain
   baseline/fallback behavior. Transfer to arbitrary sites is not established.
3. **Rainfall remains experimental.** Rain amount has not consistently improved
   over raw weather forecasts. Rain occurrence recall is low in the reported
   one-hour development groups. Ordinary dry-dominated accuracy is misleading.
4. **Sensor reference matters.** Temperature evaluation averages two sensors,
   while the retained model used its earlier reference. Humidity uses a dedicated
   humidity sensor. Agreement with these references is not calibration proof.
5. **Prepared observations and assumed timing.** Features must use readings
   available before issue. A one-hour availability delay is inherited as an
   assumption. The export does not establish separate measurement/receipt times.
   Ready-feature input checks do not replace a live ingestion-time audit.
6. **Soil ambiguity.** Rain and manual irrigation/fertigation can both change
   soil readings. A wetting signal alone cannot identify the cause or determine
   rainfall millimetres. Nearby gauges are context, not interchangeable truth.
7. **Overlapping rain windows.** Separate 1/6/12/24-hour routes do not establish
   a coherent joint distribution. Nested probabilities/totals need not be
   monotonic, and selected amount/probability routes can differ. Do not sum
   these windows or divide them into guessed hourly rain.
8. **Missing occurrence estimates.** Multi-hour probabilities at fallback sites
   are null, not zero and not sums of hourly probabilities.
9. **Historical weather replay.** Earlier development replay reused archived
   weather snapshots between recorded issues; it did not simulate new hourly
   provider refreshes. Missing observation timing cannot be reconstructed fully.
10. **No live service or retraining workflow.** This package provides inference,
    historical examples, metrics and plots. It does not collect new weather,
    ingest raw device packets, schedule forecasts or retrain automatically.
11. **De-identification scope.** Files in this release use anonymous labels and
    cleaned model metadata. Historical commits, other refs and GitHub account/commit
    metadata are not purged. Numeric data may be linkable to earlier public
    data; this is not a formal anonymity or differential-privacy guarantee.
