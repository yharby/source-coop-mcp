# Release Checklist

Quick reference for publishing a new release. See [PUBLISHING.md](PUBLISHING.md) for detailed instructions.

## Pre-Release Checklist

### 1. Version & Documentation
```bash
# Update version in pyproject.toml
# Update CHANGELOG.md with version and date
```
- [ ] `pyproject.toml` version updated
- [ ] `CHANGELOG.md` updated with new version
- [ ] All documentation up to date

### 2. Code Quality
```bash
uv run ruff format . && uv run ruff check --fix . && uv run ruff check .
```
- [ ] Code formatted and linted
- [ ] No errors

### 3. Tests & Build
```bash
# Run tests
uv run python tests/test_simplified_readme_integration.py
uv run python tests/test_search.py

# Build package
rm -rf dist/ && uv build
```
- [ ] All tests pass
- [ ] Build succeeds
- [ ] Package size reasonable (< 100KB)

### 4. Commit
```bash
git add .
git commit -m "Prepare v0.1.0 release"
git push origin main
```
- [ ] All changes committed and pushed

## Release

### 5. First Release Only
- [ ] PyPI Trusted Publisher configured ([setup guide](PUBLISHING.md#step-1-configure-pypi-trusted-publisher))
- [ ] GitHub `pypi` environment created

### 6. Create Release
```bash
# Tag version
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0

# Create release (auto-triggers workflow)
gh release create v0.1.0 --title "v0.1.0" --generate-notes
```
- [ ] Tag created and pushed
- [ ] Release published

### 7. Monitor & Verify
```bash
# Watch workflow: https://github.com/yharby/source-coop-mcp/actions
# Wait 2-3 minutes, then verify:
pip install source-coop-mcp==0.1.0
```
- [ ] Workflow completed (all green)
- [ ] Package on PyPI
- [ ] Installation works

## Post-Release

### 8. Cleanup
- [ ] Create `[Unreleased]` section in CHANGELOG.md
- [ ] Announce if needed

## Quick Commands

```bash
# Full pre-release flow
uv run ruff format . && uv run ruff check --fix .
uv run python tests/test_simplified_readme_integration.py
rm -rf dist/ && uv build
git add . && git commit -m "Prepare v0.1.0 release"
git push origin main

# Release
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
gh release create v0.1.0 --title "v0.1.0" --generate-notes

# Verify (wait 2-3 minutes)
pip install source-coop-mcp==0.1.0
```

## Troubleshooting

**Build fails**: `rm -rf dist/ && uv build`
**Workflow fails**: Check [Actions](https://github.com/yharby/source-coop-mcp/actions) logs
**Not on PyPI**: Wait 5 min, check for version conflict

## Version Format

- `v1.0.0` - Major (breaking)
- `v0.1.0` - Minor (features)
- `v0.0.1` - Patch (fixes)

---

**See**: [PUBLISHING.md](PUBLISHING.md) for detailed documentation
