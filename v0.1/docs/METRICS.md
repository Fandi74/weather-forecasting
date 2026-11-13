# Accuracy percentages and evaluation scope

There is no mathematically meaningful single accuracy percentage that combines
these continuous temperature/humidity predictions and rain occurrence/amount.

## Point diagnostics: 84 paired observations at Site A

| Variable | Definition | v0.1 | MAE | RMSE |
| --- | --- | ---: | ---: | ---: |
| Temperature | Fraction with absolute error <= 1 C | 66.7% (56/84) | 0.957 C | 1.241 C |
| Humidity | Fraction with absolute error <= 5 percentage points | 72.6% (61/84) | 4.111 pp | 5.903 pp |

The humidity baseline is within the same tolerance in 48.8% of cases (41/84)
and has MAE 8.982 pp. The MAE reduction is
100 × (1 - 4.11071058796586 / 8.982142857142858) = 54.2%.
This is an error reduction, not 54.2% humidity accuracy.

Temperature reference is the mean of two temperature sensors; the temperature
model was not retrained to that averaged reference. Humidity reference is the
dedicated humidity-sensor stream. These previously inspected observations form
a retrospective diagnostic, not an untouched test or a new cross-site result.

Exact values and unrounded metrics are in [metrics.json](../results/metrics.json).
The [anonymous pairs](../data/point_evaluation.csv) reproduce the calculations.
Neither temperature accuracy nor humidity accuracy is defined as 100 minus MAE.

## Rainfall development replay

Scores cover 2,314 overlapping station/window cases from an earlier
chronological rolling-fit development experiment. Models in that experiment
were refit at prior cutoffs. The exported final weights were fitted later,
so these results must not be presented as a new benchmark of those final weights.

Rain event = whole-window rain >= 0.28 mm.
Predicted rain event = probability >= 0.5.

- Ordinary accuracy = 100 × (TP + TN) / N.
- Balanced accuracy = 50 × (TP / wet_cases + TN / dry_cases).
- Recall = 100 × TP / wet_cases.
- Precision = 100 × TP / (TP + FP).
- Brier score = mean squared probability error; lower is better.
- Rain amount RMSE is in mm over the whole window; lower is better.
- A balanced score is unavailable when a group lacks wet or dry cases.

| One-hour group | Balanced accuracy | Ordinary accuracy | All-dry accuracy | Recall | N |
| --- | ---: | ---: | ---: | ---: | ---: |
| Site A | 57.5% | 83.7% | 84.9% | 20.0% | 332 |
| Site B | 58.4% | 75.7% | 76.1% | 25.0% | 301 |

Ordinary accuracy below the all-dry baseline is not evidence of a strong rain
classifier. The full [score table](../results/rainfall_development_scores.csv)
includes wet/dry support, confusion counts, all four horizons, Brier scores and
raw-weather amount controls. Rain amounts have not consistently beaten raw
weather forecasts. Overlapping cases are not independent storms.

All results are diagnostic/development evidence. No new overall accuracy,
prospective validation or universal station-transfer claim is made.
