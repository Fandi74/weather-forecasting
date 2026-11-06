# V2, V3 and V4 prediction graphs

V3 is the user-selected name for the frozen CatBoost candidate formerly stored as `engine_v2_catboost.1`. V4 is independently trained LightGBM on matched V2/V3 data and features; earlier locked artifacts remain unchanged.

All three graphs show the same seven-day period and share axis ranges. Every station has 168 hourly predictions. Temperature/humidity use the interval-end instant; rain uses the preceding hour. Rain probability is for at least 0.28 mm/hour. Actual observations remain withheld.

V3 retains V2 for X50 rain amount. V4 retains V2 for X50/X66 rain amounts and X66 rain probability. X51/X67 retain raw GFS in all versions; X66 retains the sensor warning. Source identities, hashes, selected methods and rain totals are in graph_metadata.json. Drawing the graphs does not refit models. V4 has not been pushed to GitHub.
