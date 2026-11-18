# DataVouch review record template

Copy this file to a private review location. Do not commit client details, tokens or raw evidence. Blank fields mean pending, not approval. This template does not authenticate a reviewer or enforce publication permissions.

## Candidate and scope

- Source commit:
- Review date (UTC):
- Package version and wheel/source SHA-256:
- Image digest and chart version, if deployed:
- Configuration hash and private environment reference:
- Tested OS/architecture/Python:
- Owner and reviewers:
- Scope exclusions:

## Decisions

Use NOT RUN, PASS, FAIL or ACCEPTED LIMITATION. An accepted limitation requires the named owner's reason and does not turn a failed mandatory test into PASS.

| Review | Reviewer and independence | Outcome | Private evidence reference | Date |
| --- | --- | --- | --- | --- |
| Automated validation and exact-revision CI | | NOT RUN | | |
| Real IdP/gateway and browser access | | NOT RUN | | |
| Real network/TLS/CNI enforcement | | NOT RUN | | |
| Client workload and correctness oracle | | NOT RUN | | |
| Storage recovery and credential rotation | | NOT RUN | | |
| Independent security and history scan | | NOT RUN | | |
| Independent onboarding | | NOT RUN | | |
| Ownership and dependency licensing | | NOT RUN | | |
| Financial-method review | | NOT RUN | | |
| Public CI isolation and repository protections | | NOT RUN | | |

## Findings

| ID | Severity | Reproduction/evidence reference | Owner | Resolution or accepted limitation | Retest revision/result |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

For client tests, record each AUTH, UI and NET case from [client validation](client-validation.md), actual response/outcome, identity role, time, evidence reference and tester. Record backup restoration hashes and independently expected workload results separately.

## Decision and follow-up

- Open mandatory findings:
- Approved residual limitations and owner:
- Revalidation triggers/date:
- Independent reviewer sign-off references:
- Owner publication authorization: **NOT GRANTED**
- Authorized exact commit/artifact hashes, if approved:
- Publication date and URL, if performed:

Do not use a planned review date as proof a review occurred. Configuration or code changes require review of their effect on existing approvals.
