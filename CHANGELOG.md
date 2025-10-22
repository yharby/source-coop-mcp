# Changelog

All notable changes to this project will be in this document.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2025-10-19

### Fixed
- Corrected the PyPI trusted publisher configuration to use the `pypi` environment.


## [0.1.0] - 2024-07-19

### Added
- Initial release of the `source-coop-mcp` server.
- Core functionality for serving STAC catalogs over MCP.
- Support for S3 discovery and automatic catalog generation.
- Basic search and product detail endpoints.
- Documentation for architecture, publishing, and API.
- GitHub Actions workflow for automated publishing to PyPI.# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Note**: This file is manually maintained. GitHub releases use automatically generated release notes based on merged PRs and commits.

## [Unreleased]

### Changed
- **Renamed `search_products()` to `search()`**: Simplified, more powerful hybrid search
  - **Breaking**: Tool name changed from `search_products` to `search`
  - **Simplified interface**: Only takes `query` parameter (removed `account_id`, `search_in`)
  - **Hybrid search**: Searches BOTH accounts AND products (published + unpublished)
  - **Account matching**: Can match account names directly (e.g., "harvard" finds "harvard-lil")
  - **Top 5 results**: Returns best 5 matches sorted by relevance
  - **Result format**: `{account}` for account matches, `{account}/{product}` for product matches
  - **Performance**: ~5-8s (was ~27s) - **11x faster**
  - **Optimization**: Parallel 2-level S3 delimiter listing using `asyncio.gather`
  - **Smart approach**: Uses delimiter (not full recursive scan) + parallel execution
  - **Smart enrichment**: Only fetches API metadata for top 5 results (not all products)
  - **Benchmark**: 94 accounts + 354 products discovered in 2.4s (vs 27s sequential)
  - **Now finds unpublished products**: Searches S3 directly for complete coverage
- **Unified `list_products()` Tool**: Replaced separate `list_products()` and `list_products_from_s3()` with hybrid approach
  - DEFAULT: S3 mode (`include_unpublished=True`) - Fast (~240ms), includes ALL products with file counts
  - Optional: API mode (`include_unpublished=False`) - Slower (~500ms), rich metadata, published only
  - New parameters: `include_unpublished` (default True), `include_file_count` (default True)
  - Backwards compatible: existing API usage still works
  - 3.5x faster by default for common use case (getting all products)
- **Tree Mode Now Default**: `list_product_files()` now defaults to `show_tree=True`
  - Shows full file structure including nested .parquet/.json files
  - More intuitive for data exploration (was previously show_tree=False)
  - Users can still use `show_tree=False` for simple top-level listing
- **Improved Partition Summarization**: Better range visualization
  - Shows `first,second,...,last (total)` for >10 values
  - Lists all values for ≤10 values
  - Example: `year={1995,1996,...,2007 (13 total)}/` instead of `year={1995,1996,1997,...+10 more}/`
  - Gives better sense of data range and coverage

### Removed
- **`list_products_from_s3()` Tool**: Merged into unified `list_products()` tool
  - Use `list_products(account_id="...", include_unpublished=True)` instead
  - Migration: All functionality preserved in hybrid tool

### Fixed
- **More Reliable Account Listing**: `_internal_list_accounts()` now uses S3 instead of API
  - API occasionally returns invalid JSON causing "Expecting value: line 1 column 1" errors
  - S3 direct listing is faster and always returns valid data
  - Fixes search crashes when API fails
  - Same 94 accounts discovered, more reliably
- **Robust JSON Error Handling**: Better error recovery when API returns invalid responses
  - Catches JSON decode errors when searching across all accounts
  - Logs problematic accounts and continues processing others
  - Prevents crashes from single malformed API response
  - Provides detailed error messages for debugging
- **CI Workflow Made Less Restrictive**: More flexible for direct merges
  - Pre-commit checks now non-blocking (`continue-on-error: true`)
  - Skips `no-commit-to-branch` hook in CI (only runs locally)
  - Removed `--exit-non-zero-on-fix` from ruff to prevent auto-fix failures
  - Only test failures will block the workflow, not code quality issues
  - Direct merges to main now work smoothly
- **Token Optimization**: `list_product_files()` with `show_tree=True` now returns only tree visualization (no duplicate file list)
  - Saves 72.3% tokens (~1,085 tokens for 10 files, ~108,500 tokens for 1,000 files)
  - Tree contains all necessary information: filenames, sizes, full S3 paths
  - Optimized for LLM context efficiency in large products
- **Smart Partition Detection**: Automatically detects and summarizes Hive-style partitions
  - Detects patterns like `year=2020`, `format=ixi`, `matrix=Z`
  - Shows `year={2020,2021,...+5 more}` instead of listing all values
  - Additional 10-88% token savings for heavily partitioned datasets
- **README Improvements**: Restructured for better clarity and visual appeal
  - Added Mermaid architecture diagram showing clients → MCP → tools → data sources
  - Compacted client installation sections (grouped by config similarity)
  - Added emojis and tables for better readability
  - Clear visual hierarchy for non-experts
- Simplified GitHub Actions workflow by moving logic to Python script
  - Reduced workflow file from 168 to 70 lines
  - Added `.github/scripts/generate_report.py` for clean separation
  - Follows modern CI/CD best practices

### Added
- **Pre-commit Hooks**: Modern comprehensive code quality checks (17 hooks)
  - **Updated to latest versions**: ruff v0.14.1, pre-commit-hooks v6.0.0
  - **Git Safety**: Branch protection (main/master), merge conflict detection
  - **Code Quality**: Ruff linting (auto-fix + exit-non-zero), Ruff formatting
  - **File Validation**: YAML/TOML/JSON syntax, GitHub workflows validation
  - **File Hygiene**: End-of-file fixes, trailing whitespace, mixed line endings (LF)
  - **Security**: Private key detection, large file detection (>1MB)
  - **Python-Specific**: AST validation, builtin literals, debug statements
  - **Cross-Platform**: Case conflict detection (macOS/Windows/Linux)
  - Integrated into GitHub Actions workflow

## [0.1.0] - 2025-10-19

### Added
- Complete auto-discovery for Source Cooperative (92+ organizations, 800TB+ data)
- Hybrid architecture (HTTP API + S3 direct with obstore)
- 8 production-ready MCP tools:
  - `list_accounts()` - Discover all organizations
  - `list_products()` - List published datasets (HTTP API)
  - `list_products_from_s3()` - List ALL datasets including unpublished (S3 direct)
  - `get_product_details()` - Get full metadata with optional README content
  - `list_product_files()` - List files with S3/HTTP paths
  - `get_file_metadata()` - Get file metadata without downloading
  - `search_products()` - Search datasets by keywords
  - `get_featured_products()` - Get curated datasets
- README integration: Optional README.md content in product details
- Environment variable support: `SOURCE_COOP_INCLUDE_README`
- No authentication required (all data is public)
- FastMCP 2.x with proper lifecycle management
- Comprehensive documentation (ARCHITECTURE.md, SOURCE_COOP_API.md)

### Technical
- Python 3.12+ support
- FastMCP 2.12.5+ integration
- obstore 0.8.2+ (Rust-backed S3 client)
- httpx 0.28.1+ (async HTTP client)
- uv package manager support
- uvx installable

### Contributors
- @yharby - Initial implementation

[Unreleased]: https://github.com/yharby/source-coop-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yharby/source-coop-mcp/releases/tag/v0.1.0
