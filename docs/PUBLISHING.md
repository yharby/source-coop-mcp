# Publishing Guide

Complete guide for publishing `source-coop-mcp` to PyPI using modern Trusted Publishing.

## Overview

This project uses **PyPI Trusted Publishing** (OIDC-based authentication) which eliminates the need for API tokens or passwords. The GitHub Actions workflow automatically publishes to PyPI when you create a GitHub release.

## Prerequisites

- PyPI account (create at https://pypi.org/account/register/)
- GitHub repository with admin access
- Package ready for publishing

## One-Time Setup

### Step 1: Configure PyPI Trusted Publisher

1. **Go to PyPI Publishing Settings**
   - Visit: https://pypi.org/manage/account/publishing/
   - Or navigate: Account Settings → Publishing

2. **Add a New Pending Publisher**
   - Click "Add a new pending publisher"
   - Fill in the form:
     ```
     PyPI Project Name: source-coop-mcp
     Owner: yharby
     Repository name: source-coop-mcp
     Workflow name: publish.yml
     Environment name: pypi
     ```
   - Click "Add"

3. **Important Notes**
   - You must do this BEFORE the first release
   - The project name `source-coop-mcp` will be created automatically on first publish
   - No API tokens or passwords needed

### Step 2: Configure GitHub Environment

1. **Go to GitHub Repository Settings**
   - Navigate to: https://github.com/yharby/source-coop-mcp/settings/environments
   - Click "New environment"
   - Name it exactly: `pypi`
   - Click "Configure environment"

2. **Optional: Add Protection Rules**
   - Enable "Required reviewers" if you want manual approval before publishing
   - Add deployment branch pattern: `main` or `v*` for version tags
   - Click "Save protection rules"

### Step 3: Verify Workflow File

The workflow file is already created at `.github/workflows/publish.yml`. It will:
- Trigger on GitHub releases
- Build the package using `uv build`
- Publish to PyPI using Trusted Publishing
- Update the release notes with auto-generated changelog

**See**: [.github/workflows/README.md](../.github/workflows/README.md) for detailed workflow documentation and diagrams.

## Publishing a Release

### Method 1: GitHub Web UI (Recommended)

1. **Go to Releases**
   - Navigate to: https://github.com/yharby/source-coop-mcp/releases
   - Click "Draft a new release"

2. **Create Release**
   ```
   Tag version: v0.1.0
   Release title: v0.1.0
   Description: Initial release (auto-generated changelog will be appended)
   ```
   - Click "Publish release"

3. **Monitor Workflow**
   - Go to: https://github.com/yharby/source-coop-mcp/actions
   - Watch "Publish to PyPI" workflow run
   - Verify all jobs complete successfully

4. **Verify on PyPI**
   - Visit: https://pypi.org/project/source-coop-mcp/
   - Confirm version appears

### Method 2: GitHub CLI (Advanced)

```bash
# Create and push tag
git tag -a v0.1.0 -m "Initial release"
git push origin v0.1.0

# Create release
gh release create v0.1.0 \
  --title "v0.1.0" \
  --notes "Initial release - See CHANGELOG.md for details"
```

## Automated Release Notes

The workflow uses **GitHub's built-in automatic release notes generation**, which includes:

- All merged pull requests since the previous tag
- Contributor attribution
- Full changelog comparison link
- Categorization by labels (if configured)

**What's Generated**:
- Automatically created when you publish a release
- Based on merged PRs and commits
- No hardcoded scripts - uses GitHub's native feature
- Appended to any manual release description you write

**Note**: The `CHANGELOG.md` file in the repository is manually maintained following [Keep a Changelog](https://keepachangelog.com/) format. GitHub release notes are separate and auto-generated.

## Version Management

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (v1.0.0): Breaking changes
- **MINOR** (v0.1.0): New features, backward compatible
- **PATCH** (v0.1.1): Bug fixes, backward compatible

### Version Checklist

Before releasing:

1. **Update pyproject.toml**
   ```toml
   [project]
   version = "0.1.0"  # Match your release tag
   ```

2. **Update CHANGELOG.md**
   - Move items from `[Unreleased]` to new version section
   - Add release date
   - Update comparison links

3. **Test Build Locally**
   ```bash
   uv build
   # Verify dist/ contains .whl and .tar.gz
   ```

4. **Create Release**
   - Follow publishing steps above

## Workflow Details

The GitHub Actions workflow has three jobs:

### Job 1: Build
```yaml
- Checkout code
- Install uv
- Build package (creates .whl and .tar.gz)
- Upload artifacts
```

### Job 2: Publish to PyPI
```yaml
- Download build artifacts
- Publish using Trusted Publishing (no credentials!)
- Create package attestations
```

### Job 3: Update Release Notes
```yaml
- Use GitHub's automatic release notes generation
- Append to any manual release description
- No custom scripts needed
```

## Troubleshooting

### Error: "Publishing is not configured"

**Cause**: PyPI Trusted Publisher not set up

**Fix**: Complete Step 1 above, then retry release

### Error: "Environment protection rules not satisfied"

**Cause**: GitHub environment requires approval

**Fix**:
- Go to Actions tab
- Click on failed workflow
- Click "Review deployments"
- Approve deployment

### Build Fails Locally

```bash
# Clean and rebuild
rm -rf dist/
uv build

# Verify package
uv run python -m tarfile -l dist/*.tar.gz
```

### Package Not Appearing on PyPI

**Check**:
1. Workflow completed successfully in GitHub Actions
2. All three jobs (build, publish, release) show green checkmarks
3. No errors in job logs
4. PyPI Trusted Publisher configured correctly

## Post-Publication

After successful publication:

### 1. Verify Installation

```bash
# Test installation
uvx source-coop-mcp --version

# Or with pip
pip install source-coop-mcp
```

### 2. Update Documentation

If README or docs changed, consider:
- Updating PyPI description (edit on PyPI web UI)
- Announcing in relevant communities

### 3. Tag Management

```bash
# View all tags
git tag -l

# Delete local tag (if needed)
git tag -d v0.1.0

# Delete remote tag (if needed)
git push origin --delete v0.1.0
```

## Security Notes

### Trusted Publishing Benefits

- No API tokens to manage or rotate
- No credentials stored in GitHub Secrets
- Cryptographic proof of authenticity
- Automatic package attestations

### What Gets Published

The workflow publishes:
- Source distribution (.tar.gz)
- Wheel distribution (.whl)
- Package attestations (provenance)

### Environment Security

The `pypi` environment:
- Limits who can deploy
- Adds audit trail
- Optional manual approval gate

## Testing Before Release

### Test with TestPyPI (Optional)

For extra safety, test with TestPyPI first:

1. **Configure TestPyPI Trusted Publisher**
   - Visit: https://test.pypi.org/manage/account/publishing/
   - Add same configuration as PyPI

2. **Create Test Workflow**
   ```yaml
   # .github/workflows/test-publish.yml
   - uses: pypa/gh-action-pypi-publish@release/v1
     with:
       repository-url: https://test.pypi.org/legacy/
   ```

3. **Test Installation**
   ```bash
   pip install --index-url https://test.pypi.org/simple/ source-coop-mcp
   ```

## Resources

- **PyPI Trusted Publishing**: https://docs.pypi.org/trusted-publishers/
- **GitHub Actions Publishing**: https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/
- **Semantic Versioning**: https://semver.org/
- **Keep a Changelog**: https://keepachangelog.com/

## Quick Reference

```bash
# Local build and verify
uv build
ls dist/

# Create tag
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0

# Create release (triggers workflow)
gh release create v0.1.0 --title "v0.1.0" --generate-notes

# Verify published
pip install source-coop-mcp==0.1.0
uvx source-coop-mcp --version
```
