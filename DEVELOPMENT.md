# Development Guide

Technical documentation for contributors and developers.

## Table of Contents

- [Architecture](#architecture)
- [Setup](#setup)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Performance](#performance)
- [Contributing](#contributing)
- [CI/CD](#cicd)

---

## Architecture

### System Overview

```
┌─────────────────────┐
│   AI Client         │  (Claude Desktop, Cursor, etc.)
└──────────┬──────────┘
           │ MCP Protocol (JSON-RPC)
           ▼
┌─────────────────────────────────────┐
│  Source Cooperative MCP Server      │
│  • FastMCP 2.12.5+                  │
│  • Python 3.11+                     │
│  • 7 Tools                          │
└──────────┬────────────┬─────────────┘
           │            │
           ▼            ▼
   ┌───────────┐  ┌──────────────┐
   │ HTTP API  │  │ S3 Direct    │
   │ (metadata)│  │ (obstore)    │
   └───────────┘  └──────────────┘
```

### Hybrid Data Access

**Why Two Sources?**

1. **HTTP API** (`source.coop/api/v1`)
   - Rich metadata (titles, descriptions)
   - Only published products
   - Rate limited

2. **S3 Direct** (`s3://us-west-2.opendata.source.coop`)
   - All files and products (published + unpublished)
   - Fast access (obstore = 9x faster than boto3)
   - No rate limits

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | FastMCP 2.12.5+ | MCP server implementation |
| S3 Client | obstore 0.8.2+ | Rust-backed storage (fast!) |
| HTTP Client | httpx 0.28.1+ | Async API calls |
| Search | difflib (stdlib) | Fuzzy matching |
| Python | 3.11+ | Runtime |

---

## Setup

### Development Installation

```bash
# Clone repository
git clone https://github.com/yharby/source-coop-mcp.git
cd source-coop-mcp

# Install with uv (includes dev dependencies)
uv sync

# Install pre-commit hooks
uv run pre-commit install

# Run tests
uv run python -u tests/test_all_mcp_tools.py
```

### Local Testing

#### Option 1: Claude Desktop (Recommended for End-to-End Testing)

**Step 1: Backup your Claude config**
```bash
cp ~/Library/Application\ Support/Claude/claude_desktop_config.json \
   ~/Library/Application\ Support/Claude/claude_desktop_config.json.backup
```

**Step 2: Edit Claude Desktop config**
```bash
# Open config in default editor
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Step 3: Add local development server**

Choose ONE of these methods:

**Method A: Using `uvx` with local path** (fastest)
```json
{
  "mcpServers": {
    "source-coop-mcp-dev": {
      "command": "uvx",
      "args": [
        "--from",
        "/Users/yharby/Documents/gh/walkthru-lat/source-soop-mcp",
        "source-coop-mcp"
      ]
    }
  }
}
```

**Method B: Using `uv run` directly** (more control)
```json
{
  "mcpServers": {
    "source-coop-mcp-dev": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/yharby/Documents/gh/walkthru-lat/source-soop-mcp",
        "python",
        "-m",
        "source_coop_mcp.server"
      ]
    }
  }
}
```

**Step 4: Restart Claude Desktop**
- Completely quit Claude Desktop (Cmd+Q)
- Reopen Claude Desktop
- Your local development server is now active

**Step 5: Test your changes**

Try these in Claude Desktop:

1. **Test search with fuzzy matching:**
   ```
   Search for products matching "exopase"
   ```
   Should find "exiobase-3" with 80% similarity

2. **Test tree optimization:**
   ```
   List files for fused/fsq-os-places with tree view
   ```
   Should show `[0-326].parquet (327 files, ...)` instead of listing each file

3. **Test pattern detection:**
   ```
   Show me the file structure for fused/overture
   ```
   Should detect and summarize numbered parquet files

**Troubleshooting:**

**❌ Common Mistake: Extra Quotes in Path**

```json
// WRONG - Has quotes in the string value
{
  "args": ["--from", "\"/Users/yharby/Documents/gh/walkthru-lat/source-soop-mcp\"", "source-coop-mcp"]
}

// CORRECT - No quotes inside string values
{
  "args": ["--from", "/Users/yharby/Documents/gh/walkthru-lat/source-soop-mcp", "source-coop-mcp"]
}
```

**Error**: `Distribution not found at: file://.../%22/Users/...%22`
- The `%22` indicates URL-encoded quotes in the path
- Remove quotes from inside the JSON string values

**Verification Commands:**
```bash
# Check if uvx can find your local package
uvx --from /Users/yharby/Documents/gh/walkthru-lat/source-soop-mcp source-coop-mcp --help

# View Claude Desktop logs
tail -f ~/Library/Logs/Claude/mcp*.log

# View Goose logs (if using Goose)
cat ~/.config/goose/sessions/*/logs/*

# Test server manually
cd /Users/yharby/Documents/gh/walkthru-lat/source-soop-mcp
uv run source-coop-mcp  # Should output JSON messages
```

#### Option 2: MCP Inspector (Best for Tool Testing)

```bash
# Install MCP Inspector globally (one-time)
npm install -g @modelcontextprotocol/inspector

# Run with your local server
mcp-inspector uvx --from /Users/yharby/Documents/gh/walkthru-lat/source-soop-mcp source-coop-mcp
```

Opens a web interface at `http://localhost:5173` where you can:
- See all available tools
- Call tools with custom parameters
- View JSON-RPC requests/responses in real-time
- Debug errors interactively

#### Option 3: Manual Server Testing

```bash
cd /Users/yharby/Documents/gh/walkthru-lat/source-soop-mcp

# Start server in stdio mode (MCP protocol)
uv run python -m source_coop_mcp.server

# Server will wait for MCP protocol messages on stdin
# Press Ctrl+C to stop
```

#### Quick Testing Checklist

After configuring Claude Desktop with your local server:

- [ ] Claude Desktop completely quit and reopened
- [ ] Server shows in Claude's available tools
- [ ] Search "exopase" finds "exiobase-3" (fuzzy match ✓)
- [ ] Tree view detects numbered file patterns
- [ ] No errors in `~/Library/Logs/Claude/mcp*.log`
- [ ] All changes reflected in behavior
- [ ] Ready to commit!

---

## Testing

### Comprehensive Test Suite

**Single unified test file**: `tests/test_all_mcp_tools.py`

Tests all 8 MCP tools with:
- Performance timing
- Success/failure tracking
- Detailed reporting
- Token optimization verification
- Pattern detection testing

**Run tests**:

```bash
uv run python -u tests/test_all_mcp_tools.py
```

**Expected output**:

```
Total Tests: 11
✓ Passed: 11
✗ Failed: 0
Success Rate: 100.0%
Total Duration: ~8-9s
```

### Test Coverage

| Tool | Test Case | Expected |
|------|-----------|----------|
| `list_accounts` | List all orgs | 94+ accounts, <1s |
| `list_products` | Published only | Via HTTP API |
| `list_products_from_s3` | All products | Includes unpublished |
| `get_product_details` | With README | Auto-included |
| `list_product_files` | File listing | S3 + HTTP URLs |
| `list_product_files` | Tree mode | 72.3% token reduction |
| `get_file_metadata` | HEAD request | No download |
| `search_products` | Exact match | Relevance scoring |
| `search_products` | Fuzzy match | Typo handling (60% threshold) |
| `list_product_files` | Numbered files | Pattern detection (Foursquare) |
| `list_product_files` | Date directories | Temporal snapshot detection |

---

## Code Quality

### Pre-commit Hooks

**Automatic code quality checks** run before every commit:

```bash
# Install hooks (one-time setup)
uv run pre-commit install

# Manually run on all files
uv run pre-commit run --all-files

# Update hook versions
uv run pre-commit autoupdate
```

**Hooks include (17 total):**

*Git Safety:*
- ✅ Branch protection (prevents commits to main/master)
- ✅ Merge conflict detection

*Code Quality:*
- ✅ Ruff linting (with auto-fix and exit-non-zero)
- ✅ Ruff formatting

*File Format Validation:*
- ✅ YAML syntax check (multi-document support)
- ✅ TOML syntax check (pyproject.toml)
- ✅ JSON syntax check
- ✅ GitHub workflows validation

*File Hygiene:*
- ✅ End-of-file newline enforcement
- ✅ Trailing whitespace removal (markdown-aware)
- ✅ Mixed line ending fixes (LF enforced)

*Security:*
- ✅ Private key detection
- ✅ Large file detection (>1MB)

*Python-Specific:*
- ✅ AST syntax validation
- ✅ Builtin literals check
- ✅ Debug statements detection

*Cross-Platform:*
- ✅ Case conflict detection (macOS/Windows/Linux)

### Manual Checks

```bash
# Format code
uv run ruff format .

# Lint
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .
```

### Code Style

- **Line length**: 100 characters
- **Target**: Python 3.11+
- **Formatter**: Ruff
- **Linter**: Ruff
- **Pre-commit**: Enabled
- **Type hints**: Encouraged (not enforced)

---

## Performance

### Benchmarks

| Operation | Duration | Notes |
|-----------|----------|-------|
| List accounts | ~850ms | Directory listing (fast!) |
| List products (API) | ~1000ms | HTTP API |
| List products (S3) | ~240ms | S3 direct (fastest) |
| Get product details | ~650ms | + README fetch |
| List files | ~240ms | S3 listing |
| List files (tree mode) | ~980ms | Token-optimized (72% reduction) |
| File metadata | ~230ms | HEAD operation |
| Search | ~620ms | With fuzzy matching |

### Token Optimization

**list_product_files() Tree Mode**:
- **Old approach**: Returned both files array + tree string = ~1,500 tokens for 10 files
- **New approach**: Returns only tree string = ~415 tokens for 10 files
- **Savings**: 72.3% reduction (~1,085 tokens for 10 files)
- **For 1000 files**: Saves ~108,500 tokens per request
- **Why**: Tree contains all info (paths, sizes, structure) - no duplication needed

**Smart Pattern Detection** (3 types):

1. **Hive-style Partitions**:
   - Detects patterns like `year=2020/`, `format=ixi/`
   - Shows: `year={1995,1996,...,2007 (13 total)}/`
   - Instead of listing all partition values
   - Saves 10-50% tokens for partitioned datasets

2. **Numbered Files**:
   - Detects sequential files: `0.parquet`, `1.parquet`, ..., `80.parquet`
   - Shows: `[0-80].parquet (81 files, 6.0 MB - 465.3 MB, total: 12.7 GB)`
   - Includes size range (min, max, total)
   - Saves 28.7%-70% tokens for numbered datasets
   - Example: Foursquare dataset (335 files) → ~2,400 tokens saved

3. **Date Directories**:
   - Detects temporal patterns: `2024-11-19/`, `2024-12-03/`
   - Shows: `{2024-11-19, 2024-12-03, ..., 2025-02-06} (4 temporal snapshots)`
   - Displays structure from first date as example
   - Saves significant tokens for time-series datasets

**Combined Impact**:
- Base tree optimization: 72.3% reduction
- Pattern detection: +28.7% to +70% additional savings
- **Total possible savings: >98%** for large partitioned datasets

### Performance Tips

**Use S3 direct for discovery**:
```python
# Fast - S3 direct
list_products_from_s3("account")  # ~240ms

# Slower - HTTP API
list_products("account")  # ~1000ms
```

**Always specify account_id for search**:
```python
# Fast - single account
search_products("climate", account_id="harvard")  # ~620ms

# Slow - all 94 accounts
search_products("climate")  # ~60s
```

### Why obstore?

| Metric | boto3 | obstore | Improvement |
|--------|-------|---------|-------------|
| Throughput | 1x | 9x | 900% faster |
| Memory | 100% | 60% | 40% less |
| List 1000 files | 2-3s | 0.5-1s | 2-6x faster |

---

## Contributing

### Development Workflow

1. **Fork** the repository
2. **Create** feature branch: `git checkout -b feature/my-feature`
3. **Install** pre-commit hooks: `uv run pre-commit install`
4. **Make** changes
5. **Test**: `uv run python -u tests/test_all_mcp_tools.py`
6. **Commit**: Pre-commit hooks run automatically (lint, format, checks)
7. **Push**: `git push origin feature/my-feature`
8. **PR**: Create pull request

**Note**: Pre-commit hooks will automatically:
- Format code with ruff
- Fix linting issues
- Check YAML syntax
- Prevent commits to main branch

### Commit Message Format

```
type(scope): short description

Longer description if needed.

Fixes #123
```

**Types**: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`

### Pull Request Checklist

- [ ] Tests pass locally
- [ ] Code is formatted (ruff)
- [ ] No linting errors
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (if needed)

---

## CI/CD

### GitHub Actions Workflows

**1. Test and Report** (`test-and-report.yml`)

Triggers:
- Push to `main` or `develop`
- Pull requests to `main`
- Manual workflow dispatch

Features:
- Runs full test suite
- Generates Markdown reports (Python script, not inline bash)
- Comments results on PRs
- Stores reports as artifacts (30 days)

Best Practices:
- Clean separation: logic in `.github/scripts/`, not in workflow
- Uses `uv run python` for consistency
- Minimal inline code
- Proper error handling

**2. Publish to PyPI** (`publish.yml`)

Trigger: GitHub release published

Features:
- Builds package with `uv`
- Publishes to PyPI (Trusted Publishing)
- Auto-generates release notes

### Viewing Test Reports

**From PR**:
- Reports automatically commented on PRs

**From Actions**:
1. Go to Actions tab
2. Click workflow run
3. Download from Artifacts

**From Repository**:
- View `reports/latest-test-report.md`

---

## Project Structure

```
source-coop-mcp/
├── src/
│   └── source_coop_mcp/
│       ├── __init__.py
│       └── server.py          # Main MCP server
├── tests/
│   └── test_all_mcp_tools.py  # Comprehensive tests
├── docs/
│   ├── ARCHITECTURE.md         # Detailed architecture
│   ├── SOURCE_COOP_API.md      # API documentation
│   ├── PUBLISHING.md           # PyPI publishing guide
│   └── technical/              # Technical reports
├── .github/
│   └── workflows/
│       ├── test-and-report.yml # Test automation
│       ├── publish.yml         # PyPI publishing
│       └── README.md           # Workflow docs
├── README.md                   # User documentation
├── DEVELOPMENT.md              # This file
├── CHANGELOG.md                # Version history
└── pyproject.toml              # Project config
```

---

## Advanced Topics

### Fuzzy Search Algorithm

Uses `difflib.SequenceMatcher` for similarity scoring:

```python
from difflib import SequenceMatcher

def calculate_similarity(text1, text2):
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
```

**Threshold**: 0.6 (60% similarity minimum)

**Scoring**:
- Exact match: Full points
- Fuzzy match: Proportional to similarity

**Example**:
- "ovrture" vs "overture" = 0.93 similarity (93% match)
- Threshold 0.6, so it passes
- Returns with score: 4.65 points

### obstore Performance

Why it's fast:
- Written in Rust
- Uses Apache Arrow format
- Zero-copy data structures
- Concurrent operations optimized

**Usage**:
```python
import obstore as obs
from obstore.store import S3Store

# Public bucket (no credentials)
store = S3Store(bucket, region="us-west-2", skip_signature=True)

# Fast directory listing
result = await obs.list_with_delimiter_async(store, prefix="account/")
prefixes = result.get("common_prefixes", [])

# Fast file metadata
metadata = await obs.head_async(store, "path/to/file")
```

---

## Debugging

### Enable Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### MCP Inspector

Best tool for debugging MCP servers:

```bash
npx @modelcontextprotocol/inspector uv run src/source_coop_mcp/server.py
```

Features:
- Test tools interactively
- See JSON-RPC messages
- Debug errors in real-time

### Common Issues

**Tests timeout**:
- Check internet connection (S3 access required)
- Increase timeout in test runner

**Import errors**:
- Run `uv sync` to install dependencies
- Check Python version (3.11+ required)

**Performance issues**:
- Use S3 direct (`list_products_from_s3`) not API
- Always specify `account_id` for search
- Check network latency to S3

---

## Release Process

### Version Bump

1. Update `pyproject.toml` version
2. Update `CHANGELOG.md`
3. Commit: `git commit -m "chore: bump version to X.Y.Z"`
4. Tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
5. Push: `git push && git push --tags`

### Create Release

```bash
gh release create vX.Y.Z \
  --title "vX.Y.Z" \
  --notes "See CHANGELOG.md for details"
```

This triggers:
- Automated build
- PyPI publication (Trusted Publishing)
- Auto-generated release notes

---

## Resources

- [FastMCP Documentation](https://gofastmcp.com/)
- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [obstore Documentation](https://developmentseed.org/obstore/)
- [Source Cooperative API](https://source.coop/api/v1)
- [Python Packaging Guide](https://packaging.python.org/)

---

## License

MIT License - see LICENSE file for details.

---

**Questions?** Open an issue on [GitHub](https://github.com/yharby/source-coop-mcp/issues)
