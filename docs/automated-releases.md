# Manual releases

Release automation is disabled by owner choice. Product CI uses the shared templates repository; it does not create release PRs, publish tags, upload packages or deploy images.

1. Prepare a PR updating pyproject.toml, the DataVouch entry in uv.lock, `src/datavouch/__init__.py`, Helm Chart.yaml and CHANGELOG.md consistently. Preserve dependency versions and previous changelog entries.
2. Use semantic versions: patch for compatible fixes, minor for compatible features and major for breaking supported contracts. Describe breaking changes and migration steps.
3. Run the full validator. The protected PR must pass `Public CI passed`; only the owner can merge main.
4. After merge, wait for successful main CI on the exact commit. Create an annotated version tag on that revision and a GitHub release with source release notes only. Do not move existing published tags.
5. Verify the tag, version metadata, release notes and absence of uploaded assets. GitHub supplies source archives automatically.

The current release is v1.0.0. Earlier alpha tags and releases were removed at the owner's request; source commit history and historical changelog entries remain. Local context and VM automation are ignored and excluded from product distributions.

A release is not client-specific deployment acceptance. Use [client validation](client-validation.md) before shared production use.
