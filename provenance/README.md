# Provenance

`base-copy.json` records the SHA-256 and size of every file in the original skill baseline. It contains only relative paths and can be checked against the preserved files.

`engine-port.json` records path-level coverage of all bundled engine pages, implementation modules, tests, guides, provenance, tools, assets and catalog references. `sources.json` and per-module notices record source revisions and licenses.

`catalog/engines.json` tracks capability states. `catalog/engine-pages.json` maps each top-level engine page to its Python files and public symbols. No development source is imported at runtime. Any new implementation must record repository, revision, file, symbol range, SPDX license, changes and local test IDs before a capability can be upgraded.
