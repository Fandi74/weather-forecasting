# Model methods

v0.1 is a hybrid forecast correction model. It uses external numerical weather
forecasts as inputs instead of learning weather entirely from scratch.

## Temperature and baseline controls

The statistical baseline applies its selected raw, median-residual or hourly
median-residual corrections by site and forecast day. Point temperature is
retained from that baseline. Coefficients and transform values are provided in
[point_parameters.json](../models/point_parameters.json).

## Humidity

Site A combines three humidity components with equal one-third weights:
the statistical baseline, a CatBoost residual learner and a LightGBM residual
learner. Residual predictions are added to raw forecast humidity and clipped
to 0–100 before the selected blend. Other sites retain baseline humidity.

Features include forecast temperature/humidity/rain, local-hour sine/cosine,
forecast day, available recent humidity, rolling coverage/means and recent
forecast-error summaries. Inputs must be prepared from observations available
when the forecast is issued.

## Rainfall

The selected rainfall families are fixed LightGBM occurrence/positive-amount
learners. Candidate feature groups combine weather, recent own rain, nearby
rain and soil-wetting signals. Separate controls include a baseline rain recipe,
a direct weather-window logistic learner and past climatology.

| Site | Window | Amount route | Probability route |
| --- | ---: | --- | --- |
| A | 1h | own rain | nearby rain + soil |
| A | 6/12/24h | baseline rain recipe | weather-window logistic |
| B | 1h | own rain + soil | own rain + soil |
| B | 6h | own rain + soil | weather-window logistic |
| B | 12/24h | own rain + soil | past window climatology |

The probability and amount can come from different selected routes.
The exported models use the inherited conservative one-hour observation
availability assumption. It is an assumption, not measured transmission latency.

Model metadata and direct identifying labels were removed or replaced.
Numerical equivalence is checked against the reference implementation.
The release does not retrain models or change the selected routes.

See [metrics](METRICS.md) and [limits](LIMITATIONS.md).
