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
