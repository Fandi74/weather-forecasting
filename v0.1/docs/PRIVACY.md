# File-content de-identification

This release snapshot contains only the public v0.1 package. Identifying old archives,
configuration snapshots, raw device exports, original provenance records and
opaque binary model metadata are excluded.

The research was conducted by the author while working at a company, which
owns the underlying research and project intellectual property. The company
is intentionally unnamed. This general provenance statement does not identify
the company or its sites. See [ownership and license scope](../../NOTICE.md).

The release uses generic site aliases, relative forecast hours, generic feature
names and portable paths. It excludes project-specific organization names, original
telemetry labels, registration/device identifiers, precise coordinates,
private network addresses and personal source paths.

CatBoost is exported as numerical JSON without its original model-info block.
LightGBM feature labels are replaced and training-parameter metadata is removed.
The numeric model behavior is checked by native inference and full example
replay. No identifier mapping is published.

The package manifest fingerprints only the new public files. It does not
publish source-location or identifier-mapping records.

## Boundaries

Content cleaning applies to this release snapshot. Historical commits and
other refs may expose earlier identifiers. GitHub account and commit metadata
remain visible. Publishing or merging this snapshot is not a repository-wide
history purge.

Retained numerical models/examples can potentially be matched to previously
public data. Generic labels remove direct names; they do not provide a formal
anonymity or differential-privacy guarantee.

The structural scanner checks broad identifier/address/path patterns.
A separate publication review checks known source identifiers and all graph
labels. These checks reduce accidental disclosure; they are not a claim that
model weights or numeric measurements reveal no information.

See [limitations](LIMITATIONS.md) and [metric definitions](METRICS.md).
