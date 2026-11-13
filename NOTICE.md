# Research origin, ownership and license scope

## Company research and ownership

This public base model is derived from research carried out by its author
while working at a company. The company owns the underlying research and
project intellectual property, including the project-owned material in this
release. The company's name and original site and device identities are
intentionally withheld in this public release. The anonymous copyright notice
in [LICENSE](LICENSE) refers to that company; repository hosting and authorship
do not imply personal ownership of the company intellectual property.

## Public release under MIT

The [MIT license](LICENSE) covers the project-owned source code, released model
artifacts and associated documentation in this release snapshot. It permits
reuse, modification and distribution, including commercial use, subject to its
copyright and license notice requirements. Copyright ownership remains with
the company.

The full company system, unreleased features, private datasets, confidential
research and deployment components are outside this release. This release
grants no license to those unreleased materials or to company trademarks.
This notice explains provenance and scope; it adds no restrictions to the MIT
license for the covered public material.

## Reduced feature set and accuracy

This is a limited base model, rather than the full company implementation.
It does not use **air pressure**, **light intensity (lux)** or **UV index**
as model inputs. These inputs and the full system's additional capabilities
are outside the public package.

Treat its forecasts as a baseline with limited accuracy. The reduced feature
set may make forecasts less accurate than those from the full system; adding
inputs alone does not guarantee an improvement. No direct benchmark against
the full system is published here, so the size of any accuracy difference is
unknown. The published graphs and percentages describe only the public
model's stated evaluation conditions. See
[limitations](v0.1/docs/LIMITATIONS.md) and
[metric definitions](v0.1/docs/METRICS.md).

## Third-party material

Third-party data and dependencies retain their applicable upstream terms;
the MIT license does not replace them. Existing weather-data attribution is
retained: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0).

The MIT license text follows the
[Open Source Initiative MIT license](https://opensource.org/license/mit).
