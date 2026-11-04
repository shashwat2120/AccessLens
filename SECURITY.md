# Security policy

AccessLens parses documents from untrusted sources, so security reports are welcome and taken
seriously. The full design is in [`docs/03-SECURITY.md`](docs/03-SECURITY.md).

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private reporting instead: open the repository's **Security** tab and choose
**Report a vulnerability**. Include what you found, how to reproduce it (a minimal file or
request is ideal), and the impact you expect. Please do not include real personal or
confidential documents; a synthetic file that triggers the problem is enough.

This is a personal project maintained on a best-effort basis. You can expect an acknowledgement
within about a week, and a fix or a clear explanation for anything confirmed. Reporters are
credited in the changelog unless they ask not to be.

## What is in scope

- Upload handling: zip bombs, XML entity or DOCTYPE tricks, macro-enabled or disguised files,
  path traversal in archive names, SSRF through external relationships.
- The parser sandbox: escaping the child process, exceeding its time or memory limits.
- The API: authentication bypass, rate-limit bypass, response headers, error messages that leak
  internals or document content, request-size handling.
- Report output: script injection in the HTML report, formula injection in the XLSX export.
- The LLM layer: prompt injection that changes or hides findings, or sends data it should not.
- The MCP server: reading files outside `MCP_ALLOWED_DIR`.
- Secrets handling: keys appearing in logs, responses, images or the repository.

## Out of scope

- Findings that need a vulnerable dependency we cannot update yet, if the upstream advisory is
  already public (Dependabot and `pip-audit` track these).
- Denial of service through sheer request volume against a public demo.
- Accessibility rule accuracy (a missed or false finding) is a bug, not a vulnerability; please
  open a normal issue.

## Supported versions

Only the latest release and the `main` branch receive security fixes.

## What the project already does

Uploads are validated before parsing and parsed in a resource-limited child process; the LLM
has no tools and can only add findings; documents are never stored; logs never contain document
text; API keys are stored only as hashes; and CI runs `gitleaks`, `bandit`, `pip-audit`, `ruff`
security rules and a Trivy image scan. If you find a gap in any of that, we want to hear it.

## If a key leaks

Revoke it at the provider immediately, create a new one, purge it from git history, and note
the incident in `CHANGELOG.md`.
