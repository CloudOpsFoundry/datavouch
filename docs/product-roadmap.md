# Product objective and delivery sequence

DataVouch helps users assess data workload changes through reproducible correctness, performance, reliability and financial evidence. Missing evidence must remain UNKNOWN. The UI and CLI must use the same verification engines and produce consistent conclusions.

## One repository

Keep all DataVouch product code in this monorepo. The existing UI uses FastAPI, Jinja templates and CSS; it does not need a separate frontend repository.

| Location | Responsibility |
| --- | --- |
| `src/datavouch/web/` | UI routes, templates, styles and local access controls |
| `src/datavouch/` | CLI, shared engines, adapters and report generation |
| `tests/` | Unit, contract and integration checks |
| `examples/` | Reproducible sample inputs and extension examples |
| `docs/` | User setup, contributor guides, architecture and release gates |
| `.github/` | CI workflows and repository configuration |

Machine-specific runner infrastructure remains local and ignored as previously agreed. Credentials, private evidence and local runtime files must also remain outside tracked product files. Future UI and backend components belong in this repository, with shared contracts and coordinated validation.

## Delivery milestones

1. **Local review, available today.** Start the authenticated viewer, explore saved experiment history, inspect PASS/FAIL/UNKNOWN and download summaries. Acceptance: follow the getting-started guide and reproduce the example outcomes.
2. **Guided experiment setup, next.** Add forms for workload identity, baseline and candidate job selections, windows and check policies. Explain required inputs in plain language, validate them before execution and preserve a replayable experiment plan. Acceptance: create a valid plan through the UI and show actionable errors for invalid input without submitting cloud queries.
3. **Run and retain experiments.** Add explicitly initiated, bounded collection with progress, failure handling, saved history and report inspection. Keep cloud credentials on the backend. Acceptance: UI and CLI agree for successful, failed and incomplete evidence, including real validation in the authorized sandbox.
4. **Shared end-user deployment.** Add durable storage, background execution, identity, workspace permissions, audit history and TLS deployment instructions. Acceptance: test access isolation, recovery and the complete documented deployment workflow.
5. **Public release.** Complete the release-readiness gates, independent onboarding and security review, and publish only after owner approval. Maintain the licence, contribution guide and security reporting process alongside tested setup instructions.

These are delivery milestones, not completed features or calendar promises. Each functional milestone needs automated checks and a local UI walkthrough before moving on. Public release remains separate from whether a local demonstration works.
