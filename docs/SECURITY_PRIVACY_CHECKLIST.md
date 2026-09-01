# Security and Privacy Release Checklist

Use this checklist before every public update or release.

## Repository Content

- [ ] Run `python -m pytest tests/test_privacy_hygiene.py -q`.
- [ ] Confirm examples use placeholders, `localhost`, `$HOME`, `$PSScriptRoot`, or environment-derived paths.
- [ ] Confirm no personal aliases, employee names, corporate email addresses, internal hostnames, tenant IDs, or workstation paths are tracked.
- [ ] Confirm no customer report names, account names, domains, or production connection details appear in examples or fixtures.
- [ ] Confirm generated migration output remains excluded by `.gitignore` and `git ls-files artifacts` returns no files.
- [ ] Delete local `artifacts/` and `scripts/artifacts/` output before sharing, archiving, or transferring the workspace.
- [ ] Review staged changes with `git diff --cached` before pushing.

## Credentials and Configuration

- [ ] Run repository secret scanning before pushing.
- [ ] Keep tokens, passwords, connection strings, tenant IDs, client IDs, and workspace IDs in environment variables or an ignored `.env` file.
- [ ] Verify logs and generated reports redact passwords, tokens, API keys, and database credentials.
- [ ] Use synthetic principals and data in committed tests and examples.

## GitHub and Release Hygiene

- [ ] Review issue titles, bodies, comments, pull requests, and release notes for private environment details.
- [ ] Confirm `CODEOWNERS` references only a public project account or team.
- [ ] Decide whether historical commit author metadata requires a coordinated history rewrite before public distribution.
- [ ] If history is rewritten, coordinate force-push timing and require all contributors to re-clone.

## Cleanup Completed for the Next Update

- [x] Replaced the legacy private account alias in tracked content.
- [x] Replaced hard-coded Windows user paths with portable path discovery.
- [x] Replaced the internal PBIRS hostname with `localhost` examples.
- [x] Removed customer-specific PBIX filenames from script defaults.
- [x] Added an automated tracked-file privacy regression test.
- [x] Verified that migration artifacts are ignored and not tracked.
- [x] Removed local migration and PBIX scratch artifacts containing exported customer metadata.
- [x] Checked GitHub issues; none currently exist in this repository.

## Scope Note

This checklist protects the current tree and future commits. Existing commit author metadata remains part of Git history until the repository owner explicitly approves a coordinated history rewrite.