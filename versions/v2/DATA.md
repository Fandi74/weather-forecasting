# Data dependencies

The frozen models, predictions, annual derived GFS CSVs and verification reports
are included. Raw training inputs are not included in this initial source import.

## Station exports

Provide one folder per station: `X50`, `X51`, `X66`, `X67`, containing CSV exports.
The existing reader expects `device_id`, `timestamp_ms`, `t`, `h`, `rf`, `rfc`
and the optional `error` field. Station metadata/expected device IDs are in
`engine_v2/stations.json`. Temperature is degrees C, humidity percent, rf interval
rain mm, and rfc the tip counter at 0.28 mm/tip. Keep original timestamps/counters.

Quality checks exclude bad sensor fields, counter resets, gaps and incomplete
rain hours. The supplied X67 export duplicated X66 and was excluded. X51 lacked
October validation; X66's t/h discrepancy is preserved in the reports.

## Provider archives

Original raw responses live in `data/engine_v2/gfs/` relative to this version root
and are Git-ignored. `engine_v2/collect.py` can request the historical archive, but
provider access/retention may change. Re-fetching does not guarantee the exact
bytes recorded in `input_checksums.json`. Exact experiment reconstruction needs
the original archived inputs from the research workspace.

`python engine_v2/run.py verify` checks the included frozen package. The deeper
`engine_v2/verify.py` audit requires original raw archives and source files; it
also writes verification.json and should not be run against a frozen package
merely to inspect it. Use a separate experiment/output for future rebuilds.

Raw input files, local databases and future actual measurements should not be
committed by default. Keep later scoring results separate from the locked benchmark.
