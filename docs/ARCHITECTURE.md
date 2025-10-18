# Source Cooperative MCP Server - Architecture

**Version**: 0.1.0
**Last Updated**: October 18, 2025

## Overview

This MCP server provides AI agents with complete discovery and access to Source Cooperative's 800TB+ geospatial data repository. It uses a hybrid architecture combining S3 direct access (via obstore) with HTTP API calls for optimal performance and complete data discovery.

## Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Client (Claude)                       │
└────────────────────────┬────────────────────────────────────┘
                         │ JSON-RPC
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Source Cooperative MCP Server                   │
│                                                              │
│  ┌──────────────┐           ┌────────────────────┐          │
│  │  Lifecycle   │           │    8 MCP Tools     │          │
│  │  Management  │◄─────────►│                    │          │
│  │  (@lifespan) │           │  - list_accounts() │          │
│  └──────────────┘           │  - list_products() │          │
│                             │  - list_files()    │          │
│                             │  - search()        │          │
│                             │  - etc.            │          │
│                             └────────────────────┘          │
│                                                              │
│  ┌──────────────────────┐      ┌─────────────────────┐     │
│  │   HTTP Client        │      │   obstore (Rust)    │     │
│  │   (httpx)            │      │   S3 Store          │     │
│  │                      │      │                     │     │
│  │  For: API metadata   │      │  For: S3 discovery  │     │
│  └──────────┬───────────┘      └──────────┬──────────┘     │
└─────────────┼──────────────────────────────┼────────────────┘
              │                              │
              │                              │
     ┌────────▼────────┐            ┌────────▼────────┐
     │   HTTP API      │            │   S3 Bucket     │
     │ source.coop/api │            │ (Public, NoAuth)│
     │                 │            │                 │
     │ Returns:        │            │ Contains:       │
     │ - Metadata      │            │ - All files     │
     │ - Titles        │            │ - All products  │
     │ - Published     │            │ - Directories   │
     │   products only │            │ - Everything    │
     └─────────────────┘            └─────────────────┘
```

## The Hybrid Approach

### Why Two Data Sources?

Source Cooperative exposes data through two parallel channels:

1. **HTTP API** (`https://source.coop/api/v1`)
   - Returns rich metadata (titles, descriptions, dates)
   - **Only shows published products**
   - Fast for getting detailed information
   - Rate limited

2. **S3 Bucket** (`s3://us-west-2.opendata.source.coop`)
   - Direct access to all files and directories
   - **Shows everything (published + unpublished)**
   - Unlimited concurrent access
   - No metadata beyond file properties

### The Discovery Gap

```
HTTP API View:                 S3 Bucket Reality:
┌─────────────────┐           ┌─────────────────┐
│ youssef-harby/  │           │ youssef-harby/  │
│                 │           │                 │
│ ✓ egms-...      │           │ ✓ cloud-nat...  │ ← UNPUBLISHED
│ ✓ overture-...  │           │ ✓ egms-...      │
│ ✓ weather-...   │           │ ✓ exiobase-3    │ ← UNPUBLISHED
│                 │           │ ✓ overture-...  │
│ 3 products      │           │ ✓ weather-...   │
└─────────────────┘           │                 │
                              │ 5 products      │
                              └─────────────────┘
```

This is why we provide **two discovery tools**:
- `list_products()` - Uses HTTP API (published only)
- `list_products_from_s3()` - Scans S3 directly (everything)

## Technology Stack

### Core Libraries

```python
fastmcp >= 2.12.5      # MCP server framework with lifecycle management
obstore >= 0.8.2       # Rust-backed S3 client (9x faster than fsspec)
httpx >= 0.28.1        # Async HTTP client for API calls
```

### Why obstore?

| Feature | boto3 | obstore | Improvement |
|---------|-------|---------|-------------|
| Concurrent throughput | 1x | **9x** | 900% faster |
| Memory usage | Baseline | **60%** | 40% reduction |
| Dependencies | 4+ packages | **1 package** | Simpler |
| List 1000 files | ~2-3s | **~0.5-1s** | 2-6x faster |

obstore uses Rust internally with Apache Arrow format for memory efficiency and speed.

## MCP Tools (8 Total)

### Discovery Tools

```python
# Discover all organizations
accounts = await list_accounts()
# Returns: ['clarkcga', 'harvard-lil', 'youssef-harby', ...]

# List published products (HTTP API)
products = await list_products(account_id="youssef-harby")
# Returns: 3 products with metadata

# List ALL products (S3 direct) - Including unpublished
all_products = await list_products_from_s3(
    account_id="youssef-harby",
    include_file_count=True
)
# Returns: 5 products with file counts
```

### Product Information

```python
# Get full product metadata
details = await get_product_details(
    account_id="harvard-lil",
    product_id="gov-data"
)
# Returns: {title, description, created_at, mirrors, ...}

# Get product details with README content from product root
details_with_readme = await get_product_details(
    account_id="harvard-lil",
    product_id="gov-data",
    include_readme=True
)
# Returns: {title, description, ..., readme: {found, content, size, path, ...}}

# Or set SOURCE_COOP_INCLUDE_README=true to always include README
```

### File Operations

```python
# List files with full S3 paths
files = await list_product_files(
    account_id="youssef-harby",
    product_id="exiobase-3",
    max_files=100
)
# Returns: [{key, s3_uri, http_url, size, last_modified, etag}, ...]

# Get file metadata without downloading
metadata = await get_file_metadata(
    path="youssef-harby/exiobase-3/goose-agent.yaml"
)
# Returns: {size, etag, last_modified, content_type, ...}
```

### Search Tools

```python
# Search products by query (FAST - searches single account)
results = await search_products(
    query="climate",
    account_id="harvard-lil",  # RECOMMENDED for performance
    search_in=["title", "description"]
)
# Returns: Products sorted by relevance score (~200-500ms)

# Search all accounts (SLOW - 30-60s for all 92 accounts)
results = await search_products(query="climate")
# Not recommended unless needed

# Get curated datasets
featured = await get_featured_products()
# Returns: Featured products only
```

## Lifecycle Management

The server uses FastMCP lifecycle management with `@asynccontextmanager`:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[None]:
    global http_client

    # Startup - Initialize resources
    logger.info("Initializing Source Cooperative MCP Server")
    http_client = httpx.AsyncClient(timeout=30.0)

    yield  # Server runs here

    # Shutdown - Cleanup resources
    logger.info("Shutting down Source Cooperative MCP Server")
    if http_client:
        await http_client.aclose()

# Initialize FastMCP server with lifespan
mcp = FastMCP("source-coop", lifespan=lifespan)
```

This ensures:
- HTTP client is properly initialized on startup
- Resources are cleaned up on shutdown
- No resource leaks in long-running servers
- Compatible with FastMCP 2.12.5+

## Data Flow Diagrams

### Account Discovery Flow

```
┌──────────┐
│  Client  │
└────┬─────┘
     │ list_accounts()
     ▼
┌────────────────────────────┐
│  MCP Server                │
│                            │
│  obs.list(default_store)   │◄─── Streams S3 objects
│  Extract account prefixes  │     in batches
│  Return sorted list        │
└────┬───────────────────────┘
     │
     ▼
┌──────────────────────┐
│  S3 Bucket           │
│  Scan root level     │
│  Return directories  │
└──────────────────────┘
```

### Product Discovery Flow (Hybrid)

```
Option 1: list_products()           Option 2: list_products_from_s3()
┌──────────────────────┐             ┌──────────────────────┐
│ HTTP API             │             │ S3 Direct            │
│ GET /products/acc    │             │ list_with_delimiter  │
│                      │             │                      │
│ Returns:             │             │ Returns:             │
│ - Published only     │             │ - ALL products       │
│ - Rich metadata      │             │ - Product IDs only   │
│ - Fast (200-500ms)   │             │ - File counts        │
└──────────────────────┘             └──────────────────────┘
```

### File Listing Flow

```
┌──────────┐
│  Client  │
└────┬─────┘
     │ list_product_files(account, product)
     ▼
┌────────────────────────────────────────┐
│  MCP Server                            │
│                                        │
│  obs.list_with_delimiter(              │
│    default_store,                      │
│    prefix="account/product/"           │
│  )                                     │
│                                        │
│  Transform to:                         │
│  {                                     │
│    key: "...",                         │
│    s3_uri: "s3://...",                 │
│    http_url: "https://data.source...", │
│    size: 12345,                        │
│    last_modified: "...",               │
│    etag: "..."                         │
│  }                                     │
└────┬───────────────────────────────────┘
     │
     ▼
┌──────────────────────┐
│  S3 Bucket           │
│  List objects under  │
│  account/product/    │
└──────────────────────┘
```

## Performance Characteristics

### Response Times

| Operation | Latency | Notes |
|-----------|---------|-------|
| Account listing | ~100ms | Full bucket scan |
| Product listing (single account) | 200-500ms | HTTP API |
| Product listing (all accounts) | 30-60s | 92 API calls |
| File listing (1000 files) | 500ms-2s | S3 direct with obstore |
| File metadata (head) | ~150ms | obstore head operation |
| README fetch (with product details) | +200-300ms | HTTP GET via Data Proxy |

### Optimization Tips

**Bad (slow)**:
```python
# Lists all products from all 92 accounts
all_products = await list_products()  # 30-60 seconds
```

**Good (fast)**:
```python
# List from specific account
products = await list_products(account_id="youssef-harby")  # 200-500ms
```

**Better (complete)**:
```python
# Use S3 direct for complete discovery
products = await list_products_from_s3("youssef-harby")  # 1-3 seconds
```

## Common Use Cases

### Use Case 1: Discover Everything in an Account

```python
# Get all products (including unpublished)
products = await list_products_from_s3("youssef-harby", include_file_count=True)

# Enrich with metadata where available
for product in products:
    try:
        details = await get_product_details(
            product['account_id'],
            product['product_id']
        )
        product['title'] = details['title']
        product['published'] = True
    except:
        product['published'] = False
```

### Use Case 2: Find Datasets by Topic

```python
# Fast search within specific account (recommended)
results = await search_products(
    query="climate",
    account_id="harvard-lil",
    search_in=["title", "description"]
)

# Results are sorted by relevance score
for result in results:
    print(f"{result['title']} (score: {result['search_score']})")

# Note: Searching all accounts without account_id is slow (30-60s)
```

### Use Case 3: Access Unpublished Product

```python
# Product not visible in API
products = await list_products("youssef-harby")
# Returns: 3 products (missing exiobase-3)

# But you can still access files directly
files = await list_product_files("youssef-harby", "exiobase-3")
# Returns: Files with full S3 paths

# Download via HTTP
# https://data.source.coop/youssef-harby/exiobase-3/goose-agent.yaml
```

## Error Handling

The server implements safety checks for common issues:

```python
# HTTP client not initialized
if http_client is None:
    raise RuntimeError(
        "HTTP client not initialized. "
        "Server may not have started properly."
    )

# Product not found (404)
try:
    details = await get_product_details(account, product)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        # Product is unpublished or doesn't exist
        return {"error": "Product not found in API", "unpublished": True}
```

## Installation & Configuration

### For End Users

```bash
uvx install git+https://github.com/yharby/source-coop-mcp.git
```

Claude Desktop config:
```json
{
  "mcpServers": {
    "source-coop": {
      "command": "uvx",
      "args": ["source-coop-mcp"],
      "env": {
        "SOURCE_COOP_INCLUDE_README": "true"
      }
    }
  }
}
```

### For Developers

```bash
git clone https://github.com/yharby/source-coop-mcp.git
cd source-coop-mcp
uv sync
```

Claude Desktop config:
```json
{
  "mcpServers": {
    "source-coop": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/source-coop-mcp",
        "run",
        "src/source_coop_mcp/server.py"
      ],
      "env": {
        "SOURCE_COOP_INCLUDE_README": "false"
      }
    }
  }
}
```

## Testing

### Run Tests

```bash
# Test S3 discovery
uv run python tests/test_s3_discovery.py

# Compare API vs S3
uv run python tests/test_api_vs_obstore.py

# Test obstore basics
uv run python tests/test_obstore.py
```

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv run src/source_coop_mcp/server.py
```

Opens a web interface to test all tools interactively.

## Security & Authentication

### Public Access (No Auth Required)

Source Cooperative bucket is fully public:

```python
# obstore configuration
store = S3Store(
    "us-west-2.opendata.source.coop",
    region="us-west-2",
    skip_signature=True  # No AWS credentials needed
)
```

All data is:
- Publicly accessible
- No API keys required
- No rate limits on S3
- Open by design

## Future Enhancements

Potential improvements:

1. **Caching Layer**
   - Accounts: 24h TTL (rarely change)
   - Products: 1h TTL
   - File listings: 15min TTL

2. **Advanced Features**
   - STAC catalog parsing
   - Geospatial bounding box queries
   - Temporal filtering
   - File preview (Parquet head)

3. **MCP Resources**
   - Browsable catalog tree
   - Resource-based file access
   - Streaming downloads

## Summary

This MCP server provides:

- **Complete discovery** of Source Cooperative data
- **Hybrid architecture** for best performance and coverage
- **8 production-ready tools**
- **No authentication** required
- **9x performance** improvement with obstore
- **Discovers unpublished products** via S3 direct access
- **README integration** in product details (optional via parameter or env var)

Key insight: Always use `list_products_from_s3()` for complete discovery, as the HTTP API only shows published products.
