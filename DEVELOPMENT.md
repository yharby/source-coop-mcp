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

# Install with uv
uv sync

# Run tests
uv run python -u tests/test_all_mcp_tools.py
```

### Local Testing

**With MCP Inspector** (recommended):

```bash
npx @modelcontextprotocol/inspector uv run src/source_coop_mcp/server.py
```

Opens web interface to test all tools interactively.

**With Claude Desktop** (local development):

```json
{
  "mcpServers": {
    "source-coop-dev": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/source-coop-mcp",
        "run",
        "src/source_coop_mcp/server.py"
      ]
    }
  }
}
```

---

## Testing

### Comprehensive Test Suite

**Single unified test file**: `tests/test_all_mcp_tools.py`

Tests all 7 tools with:
- Performance timing
- Success/failure tracking
- Detailed reporting

**Run tests**:

```bash
uv run python -u tests/test_all_mcp_tools.py
```

**Expected output**:

```
Total Tests: 9
✓ Passed: 9
✗ Failed: 0
Success Rate: 100.0%
Total Duration: 6.58s
```

### Test Coverage

| Tool | Test Case | Expected |
|------|-----------|----------|
| `list_accounts` | List all orgs | 94+ accounts, <1s |
| `list_products` | Published only | Via HTTP API |
| `list_products_from_s3` | All products | Includes unpublished |
| `get_product_details` | With README | Auto-included |
| `list_product_files` | File listing | S3 + HTTP URLs |
| `get_file_metadata` | HEAD request | No download |
| `search_products` | Exact match | Relevance scoring |
| `search_products` | Fuzzy match | Typo handling |

---

## Code Quality

### Formatting and Linting

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

**Smart Partition Detection**:
- Automatically detects Hive-style partitioning patterns (e.g., `year=2020`, `format=ixi`)
- Summarizes partitions instead of listing all values
- Example: `year={2020,2021,2022,...+5 more}/` instead of 8 separate directories
- Provides schema overview while showing actual structure
- Additional token savings for heavily partitioned datasets (10-50% more savings)

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
3. **Make** changes
4. **Test**: `uv run python -u tests/test_all_mcp_tools.py`
5. **Lint**: `uv run ruff check --fix .`
6. **Commit**: Descriptive commit messages
7. **Push**: `git push origin feature/my-feature`
8. **PR**: Create pull request

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
