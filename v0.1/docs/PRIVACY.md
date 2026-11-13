# File-content de-identification

This branch contains only the public v0.1 package. Identifying old archives,
configuration snapshots, raw device exports, original provenance records and
opaque binary model metadata are excluded.

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

This is a separate branch. Other branches and Git history remain unchanged,
and may expose earlier identifiers. GitHub account and commit metadata remain
visible. Changing this branch is not a repository-wide history purge.

Retained numerical models/examples can potentially be matched to previously
public data. Generic labels remove direct names; they do not provide a formal
anonymity or differential-privacy guarantee.

The structural scanner checks broad identifier/address/path patterns.
A separate publication review checks known source identifiers and all graph
labels. These checks reduce accidental disclosure; they are not a claim that
model weights or numeric measurements reveal no information.

See [limitations](LIMITATIONS.md) and [metric definitions](METRICS.md).
