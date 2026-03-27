# Contributing

## Versioning

This project uses [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

| Change type | Bump | Example |
|---|---|---|
| Backward-incompatible change | MAJOR | `1.x.x` → `2.0.0` |
| New backward-compatible feature | MINOR | `1.2.x` → `1.3.0` |
| Bug fix or small improvement | PATCH | `1.2.1` → `1.2.2` |

### How to bump the version

1. **Edit `jira_tool/__init__.py`** — the single source of truth:
   ```python
   __version__ = "1.2.2"   # update this line
   ```
   The version is automatically picked up by the interactive menu header and every backup manifest (`tool_version` field in `manifest.json`).

2. **Add an entry to `CHANGELOG.md`** at the top of the file:
   ```markdown
   ## [1.2.2] - YYYY-MM-DD

   ### Fixed
   - Short description of the change.
   ```

Both files must be updated together in the same commit as the change that warrants the bump.

---

## Publishing a Release

Follow these steps in order every time a new version is ready:

### 1. Bump the version and update docs
- `jira_tool/__init__.py` — update `__version__`
- `CHANGELOG.md` — add a new entry at the top
- `README.md` — badges auto-update from PyPI, no manual change needed

### 2. Commit and push
```bash
git add jira_tool/__init__.py CHANGELOG.md
git commit -m "Bump version to X.Y.Z"
git push
```

### 3. Create a GitHub Release
- Go to **Releases → Create a new release**
- Tag: `vX.Y.Z`
- Title: `vX.Y.Z`
- Body: paste the new section from `CHANGELOG.md`
- Click **Publish release**

### 4. Build and upload to PyPI
```bash
pip install --upgrade build twine
python -m build
python -m twine upload dist/*
```

Enter your PyPI API token when prompted.

> The PyPI version badge in the README updates automatically within a few minutes of upload.
