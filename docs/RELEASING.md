# Releasing

Simple guide to release a new version.

## Quick Release (3 Commands)

```bash
# 1. Run release script (handles everything)
./scripts/release.sh

# Script will:
# - Bump version in pyproject.toml
# - Run tests
# - Create git tag
# - Create GitHub release (auto-generates changelog)
# - Trigger PyPI publish
```

That's it! ✅

---

## Manual Release (If Needed)

### 1. Update Version

```bash
# Edit pyproject.toml
version = "0.1.5"  # Bump this
```

### 2. Run Tests

```bash
uv run python -u tests/test_all_mcp_tools.py
```

### 3. Commit & Push

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.1.5"
git push origin main
```

### 4. Create Release

```bash
# Create & push tag
git tag -a v0.1.5 -m "Release v0.1.5"
git push origin v0.1.5

# Create GitHub release (auto-generates changelog from PRs/commits)
gh release create v0.1.5 --title "v0.1.5" --generate-notes
```

### 5. Verify (Wait 2-5 min)

```bash
# Check release page
open https://github.com/yharby/source-coop-mcp/releases/tag/v0.1.5

# Check PyPI
open https://pypi.org/project/source-coop-mcp/

# Test install
uvx source-coop-mcp@0.1.5
```

---

## What Happens Automatically

When you create a GitHub release:

1. **GitHub** auto-generates changelog from:
   - Merged PRs
   - Commit messages
   - Contributor list

2. **GitHub Actions** (`.github/workflows/publish.yml`):
   - Builds package with `uv build`
   - Publishes to PyPI (trusted publishing - no token!)
   - Adds build attestations
   - Updates release notes

---

## Version Numbers

```
v0.1.5
  │ │ └─ Patch (bug fixes)
  │ └─── Minor (new features, backward compatible)
  └───── Major (breaking changes)
```

Use release script with:
```bash
./scripts/release.sh patch   # 0.1.5 → 0.1.6
./scripts/release.sh minor   # 0.1.5 → 0.2.0
./scripts/release.sh major   # 0.1.5 → 1.0.0
```

---

## First Time Setup

Only needed once:

### PyPI Trusted Publisher

1. Go to https://pypi.org/manage/account/publishing/
2. Add new publisher:
   - **PyPI Project**: `source-coop-mcp`
   - **Owner**: `yharby`
   - **Repository**: `source-coop-mcp`
   - **Workflow**: `publish.yml`
   - **Environment**: `pypi`

3. Create `pypi` environment on GitHub:
   - Go to repo Settings → Environments
   - Click "New environment"
   - Name: `pypi`

Done! ✅

---

## Troubleshooting

**Tests fail?**
```bash
uv run python -u tests/test_all_mcp_tools.py
# Fix issues before releasing
```

**Tag already exists?**
```bash
# Delete and recreate
git tag -d v0.1.5
git push origin :refs/tags/v0.1.5
# Then create again
```

**PyPI publish fails?**
- Check https://github.com/yharby/source-coop-mcp/actions
- Verify trusted publisher is configured
- Ensure version doesn't already exist on PyPI

**Release script not found?**
```bash
chmod +x scripts/release.sh
```

---

## Full Automation (Optional Future)

For completely hands-free releases, add `python-semantic-release`:

```bash
# Install
uv add --dev python-semantic-release

# Use conventional commits
git commit -m "feat: new feature"  # → Minor bump
git commit -m "fix: bug fix"       # → Patch bump
git commit -m "feat!: breaking"    # → Major bump

# Push to main = automatic release!
```

With this setup, every push to main automatically:
- Determines version bump from commits
- Updates `pyproject.toml`
- Generates `CHANGELOG.md`
- Creates git tag
- Creates GitHub release
- Publishes to PyPI

See https://python-semantic-release.readthedocs.io/ for setup.

---

## Files Reference

- **Release script**: `scripts/release.sh`
- **Publish workflow**: `.github/workflows/publish.yml`
- **Test workflow**: `.github/workflows/test-and-report.yml`
- **Version**: `pyproject.toml`
- **Changelog**: `CHANGELOG.md` (optional, GitHub auto-generates)

---

**Questions?** Open an issue or check the workflows in `.github/workflows/`
