# Dependency license review

Technical review dated 2026-11-18. This is a maintainer assessment of the locked dependency artifacts, not independent legal advice, ownership verification or publication approval.

## Scope and result

The core package declares no runtime dependencies. The BigQuery and web extras resolve to 39 applicable packages on the reviewed Python 3.15 environment. License files were present in every installed distribution. The DataVouch wheel and source archive include the project MIT license; optional dependencies are installed separately and are not vendored into those artifacts.

No incompatible license requirement was identified for distributing the project source and wheel under MIT while retaining each dependency’s own terms. This does not relicense dependencies as MIT. Other platforms, future lockfile updates, development tools, native bundled libraries and operating-system/container redistribution require their own inventory and review. No container registry release is approved by this document.

## Locked runtime inventory

| Distribution | Version | License identified |
| --- | --- | --- |
| annotated-doc | 0.0.6 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.16.0 | MIT |
| certifi | 2026.10.23 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.1 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| fastapi | 0.163.2 | MIT |
| google-api-core | 2.44.0 | Apache-2.0 |
| google-auth | 2.62.2 | Apache-2.0 |
| google-cloud-bigquery | 3.47.0 | Apache-2.0 |
| google-cloud-core | 2.8.0 | Apache-2.0 |
| google-crc32c | 1.9.0 | Apache-2.0 |
| google-resumable-media | 2.11.0 | Apache-2.0 |
| googleapis-common-protos | 1.76.0 | Apache-2.0 |
| grpcio | 1.85.1 | Apache-2.0 |
| grpcio-status | 1.85.1 | Apache-2.0 |
| h11 | 0.16.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| proto-plus | 1.29.0 | Apache-2.0 |
| protobuf | 7.36.2 | BSD-3-Clause |
| pyasn1 | 0.6.5 | BSD-2-Clause |
| pyasn1_modules | 0.4.2 | BSD-2-Clause |
| pycparser | 3.12 | BSD-3-Clause |
| pydantic | 2.14.3 | MIT |
| pydantic_core | 2.50.4 | MIT |
| python-dateutil | 2.9.0.post0 | Apache-2.0 AND BSD-3-Clause |
| requests | 2.34.2 | Apache-2.0 |
| six | 1.17.0 | MIT |
| starlette | 1.10.0 | BSD-3-Clause |
| typing_extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.5 | MIT |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |

Jinja2’s missing license metadata was resolved by reading its bundled BSD three-clause license. The pyasn1_modules license contains two clauses. python-dateutil contains Apache terms for newer contributions and BSD terms for earlier contributions, so both are recorded rather than assuming one may always be discarded.

## Redistribution requirements

- Keep the DataVouch copyright and MIT permission notice with copies and substantial portions of the software. See the [MIT license text](https://opensource.org/license/mit).
- Preserve dependency copyright, license and applicable NOTICE files. Requests includes a NOTICE file in addition to its Apache license. Do not strip distribution metadata when assembling an environment. See [Apache 2.0 redistribution terms](https://www.apache.org/licenses/LICENSE-2.0).
- Certifi’s certificate bundle is MPL-2.0. Preserve its notice and provide access to the corresponding covered source when redistributing it. The locked source archive is recorded in uv.lock. MPL applies to covered files; it does not automatically relicense separate DataVouch source. See [Mozilla’s distribution guidance](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).
- Retain the bundled BSD, PSF and other applicable license notices. Review modifications to dependency code separately; this review assumes the locked packages are unmodified.

## Remaining decisions

The owner has confirmed complete source ownership and authorized publication. Replacing an example with synthetic numeric data does not establish rights to the underlying code. Independent ownership/license review, security and client acceptance remain pending. The owner separately authorized deletion of retained CI runs and artifacts; no CI-log/artifact export was performed.

Before a future publication, review all Git history and GitHub-visible records, isolate public CI from local runners, resolve review findings, and obtain the owner’s explicit release decision. Current-source scans cannot establish that historical material is safe to publish.
