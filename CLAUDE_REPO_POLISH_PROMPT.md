# Repo Polish Prompt

Copy and paste the block below into Claude Code (or Claude.ai) inside any repository.

---

```
Please polish this repository to a professional GitHub standard. Do all of the following steps:

---

## 1. Version audit
- Find where the version is defined (e.g. __version__, package.json, pyproject.toml, etc.)
- Read the full `git log --oneline` history
- Using semver (MAJOR.MINOR.PATCH), determine the correct version based on the commits:
  - Bug fixes → PATCH bump
  - New features → MINOR bump
  - Breaking changes → MAJOR bump
- Update the version to the correct value everywhere it is defined
- If the version is hardcoded in multiple places, fix all of them to use the single canonical source
- Create CHANGELOG.md at the repo root documenting every version with date and changes
- Create CONTRIBUTING.md explaining the semver policy and the two-file update rule
  (version file + CHANGELOG.md must be updated together with every change)

---

## 2. README
Rewrite README.md to a professional GitHub standard:
- Shields.io badges at the top: CI status, version, language/runtime, license, platform
- Short one-line description of what the tool does
- Why? section — what problem does it solve
- Features table (2 columns: Feature | Description)
- Quick Start section with install, configure, and run steps (copy-paste ready)
- Configuration Reference table if the project has config options
- Project structure tree
- Known limitations if applicable
- Links to CHANGELOG.md and CONTRIBUTING.md
- License section

---

## 3. GitHub Actions CI
- Create .github/workflows/ci.yml
- Run on push and pull_request to master/main
- Matrix: test on the last 3-4 supported language/runtime versions
- Steps: install dependencies → lint → verify imports/entry point loads
- Before creating the workflow, run the linter locally and fix any issues so CI passes on the first run
- Add the CI badge to the README

---

## 4. Dependabot
- Create .github/dependabot.yml
- Weekly schedule on Mondays
- Cover the project's package ecosystem (pip, npm, etc.)

---

## 5. Issue templates
Create .github/ISSUE_TEMPLATE/ with two templates:
- bug_report.yml — fields: version, runtime version, OS, how to reproduce, expected vs actual, log output
- feature_request.yml — fields: problem it solves, proposed solution, area affected

---

## 6. PR template
Create .github/PULL_REQUEST_TEMPLATE.md with:
- Summary field
- Type of change checkboxes (bug fix / feature / refactor / docs)
- Checklist: tested locally, linter passes, version bumped, changelog updated, README updated if needed

---

## 7. Final checks
- Run the linter one more time and fix any remaining issues
- Verify all imports and entry points work
- Commit everything with a clear message and push to the working branch
```
