"""
Source Cooperative MCP Server
Auto-discovery and data exploration for source.coop using obstore
"""

from fastmcp import FastMCP
import obstore as obs
from obstore.store import S3Store
import httpx
from typing import Optional, List, Dict
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import logging
import os
from importlib.metadata import version, PackageNotFoundError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration Constants
DEFAULT_BUCKET = "us-west-2.opendata.source.coop"
DEFAULT_REGION = "us-west-2"
API_BASE = "https://source.coop/api/v1"
DATA_PROXY = "https://data.source.coop"

# Environment variable configuration
# Set SOURCE_COOP_INCLUDE_README=true in MCP server config to always include README
INCLUDE_README_DEFAULT = os.getenv("SOURCE_COOP_INCLUDE_README", "false").lower() in [
    "true",
    "1",
    "yes",
]

# Initialize default obstore S3 client (public, no credentials)
# Note: This is for the primary bucket. Individual products may have different mirrors/regions.
default_store = S3Store(DEFAULT_BUCKET, region=DEFAULT_REGION, skip_signature=True)

# Store cache for different buckets/regions (if products use different mirrors)
_store_cache: Dict[str, S3Store] = {}

# HTTP client (initialized on startup, closed on shutdown)
http_client: Optional[httpx.AsyncClient] = None


# ============================================================================
# Lifecycle Management
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[None]:
    """Manage server lifecycle - initialize and cleanup resources"""
    global http_client

    # Startup
    try:
        pkg_version = version("source-coop-mcp")
        logger.info(f"Starting Source Cooperative MCP Server v{pkg_version}")
    except PackageNotFoundError:
        logger.info("Starting Source Cooperative MCP Server")
    
    logger.info("Initializing Source Cooperative MCP Server")
    http_client = httpx.AsyncClient(timeout=30.0)
    logger.info("HTTP client initialized")

    yield

    # Shutdown
    logger.info("Shutting down Source Cooperative MCP Server")
    if http_client:
        await http_client.aclose()
        logger.info("HTTP client closed")


# Initialize FastMCP server with lifespan
mcp = FastMCP("source-coop", lifespan=lifespan)


# ============================================================================
# MCP Tools
# ============================================================================


@mcp.tool()
async def list_accounts() -> List[str]:
    """
    Discover all organizations/accounts in Source Cooperative.

    Returns:
        List of account IDs (e.g., ['clarkcga', 'harvard-lil', 'youssef-harby'])

    Example:
        >>> await list_accounts()
        ['addresscloud', 'clarkcga', 'harvard-lil', ...]
    """
    try:
        logger.info("Listing all accounts from S3 using obstore")

        # Use obstore list to enumerate objects and extract account prefixes
        stream = obs.list(default_store, chunk_size=1000)

        accounts = set()
        async for batch in stream:
            for obj_meta in batch:
                # obj_meta is a dict with 'path' key
                location = obj_meta.get("path", "")
                if "/" in location:
                    account = location.split("/")[0]
                    accounts.add(account)

        accounts_list = sorted(list(accounts))
        logger.info(f"Found {len(accounts_list)} accounts")
        return accounts_list

    except Exception as e:
        logger.error(f"Error listing accounts: {e}")
        raise


@mcp.tool()
async def list_products(
    account_id: Optional[str] = None, featured_only: bool = False
) -> List[Dict]:
    """
    List products (datasets) in Source Cooperative.

    Args:
        account_id: Filter by specific account. If None, lists from all accounts.
        featured_only: Only return featured/curated products.

    Returns:
        List of products with metadata (title, description, dates, featured status)

    Examples:
        >>> await list_products(account_id="clarkcga")
        [{"product_id": "hls-multi-temporal-cloud-gap-imputation", ...}]

        >>> await list_products(featured_only=True)
        [{"product_id": "gov-data", "featured": 1, ...}]
    """
    if http_client is None:
        raise RuntimeError("HTTP client not initialized. Server may not have started properly.")

    try:
        if account_id:
            # Query single account
            logger.info(f"Fetching products for account: {account_id}")
            resp = await http_client.get(f"{API_BASE}/products/{account_id}")

            if resp.status_code == 200:
                data = resp.json()
                products = data.get("products", [])

                if featured_only:
                    products = [p for p in products if p.get("featured") == 1]

                logger.info(f"Found {len(products)} products for {account_id}")
                return products
            else:
                logger.warning(f"HTTP {resp.status_code} for account {account_id}")
                return []

        else:
            # Discover all products across all accounts
            logger.info("Discovering products from all accounts")
            accounts = await list_accounts()
            all_products = []

            for acc in accounts:
                try:
                    resp = await http_client.get(f"{API_BASE}/products/{acc}")
                    if resp.status_code == 200:
                        products = resp.json().get("products", [])

                        if featured_only:
                            products = [p for p in products if p.get("featured") == 1]

                        all_products.extend(products)
                except Exception as e:
                    logger.warning(f"Skipping account {acc}: {e}")
                    continue

            logger.info(f"Total products discovered: {len(all_products)}")
            return all_products

    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise


@mcp.tool()
async def list_products_from_s3(account_id: str, include_file_count: bool = False) -> List[Dict]:
    """
    List ALL products for an account by scanning S3 directly with obstore.
    This discovers both published AND unpublished products.

    Unlike list_products() which uses the HTTP API (only published products),
    this tool scans the S3 bucket directly to find all product directories.

    Args:
        account_id: Account ID (e.g., "youssef-harby")
        include_file_count: If True, count files in each product (slower)

    Returns:
        List of product dicts with product_id and optional file_count

    Example:
        >>> await list_products_from_s3("youssef-harby")
        [
            {"product_id": "exiobase-3", "source": "s3"},
            {"product_id": "egms-copernicus", "source": "s3"},
            ...
        ]
    """
    try:
        logger.info(f"Listing products for {account_id} from S3 using obstore")

        # List all directories under account_id/ using delimiter
        # Use async version for better performance
        result = await obs.list_with_delimiter_async(default_store, prefix=f"{account_id}/")

        # Extract common prefixes (these are product directories)
        common_prefixes = result.get("common_prefixes", [])

        products = []
        for prefix in common_prefixes:
            # prefix looks like: 'youssef-harby/product-name/'
            product_id = prefix.rstrip("/").split("/")[-1]

            product_info = {
                "product_id": product_id,
                "account_id": account_id,
                "source": "s3",
                "s3_prefix": f"s3://{DEFAULT_BUCKET}/{prefix}",
            }

            # Optionally count files
            if include_file_count:
                try:
                    # Use async version for better performance
                    file_result = await obs.list_with_delimiter_async(default_store, prefix=prefix)
                    file_count = len(
                        [
                            obj
                            for obj in file_result.get("objects", [])
                            if not obj.get("path", "").endswith("/")
                        ]
                    )
                    product_info["file_count"] = file_count
                except Exception as e:
                    logger.warning(f"Could not count files for {product_id}: {e}")
                    product_info["file_count"] = None

            products.append(product_info)

        logger.info(f"Found {len(products)} products in S3 for {account_id}")
        return sorted(products, key=lambda x: x["product_id"])

    except Exception as e:
        logger.error(f"Error listing products from S3: {e}")
        raise


@mcp.tool()
async def get_product_details(
    account_id: str, product_id: str, include_readme: Optional[bool] = None
) -> Dict:
    """
    Get comprehensive metadata for a specific product.

    Args:
        account_id: Account ID (e.g., "harvard-lil")
        product_id: Product ID (e.g., "gov-data")
        include_readme: If True, also fetch and include README content from product root.
                       If None, uses SOURCE_COOP_INCLUDE_README env var (default: false)

    Returns:
        Full product metadata including account info, storage config, roles, tags
        If include_readme=True, adds 'readme' field with content and metadata

    Example:
        >>> await get_product_details("harvard-lil", "gov-data")
        {
            "title": "Archive of data.gov",
            "description": "...",
            "account": {"name": "Harvard Library Innovation Lab", ...},
            ...
        }

        >>> await get_product_details("harvard-lil", "gov-data", include_readme=True)
        {
            "title": "Archive of data.gov",
            "description": "...",
            "account": {"name": "Harvard Library Innovation Lab", ...},
            "readme": {
                "found": true,
                "content": "# Archive of data.gov...",
                "size": 5344,
                "path": "harvard-lil/gov-data/README.md"
            },
            ...
        }

    Note:
        Set SOURCE_COOP_INCLUDE_README=true in your MCP server config to always include README
    """
    if http_client is None:
        raise RuntimeError("HTTP client not initialized. Server may not have started properly.")

    # Use environment variable default if not explicitly specified
    if include_readme is None:
        include_readme = INCLUDE_README_DEFAULT

    try:
        logger.info(f"Fetching details for {account_id}/{product_id}")
        resp = await http_client.get(f"{API_BASE}/products/{account_id}/{product_id}")
        resp.raise_for_status()

        product_data = resp.json()

        # Optionally fetch README content
        if include_readme:
            try:
                path_prefix = f"{account_id}/{product_id}/"
                logger.info(f"Fetching README for: {path_prefix}")

                # List files in product root only (non-recursive)
                # Use async version for better performance
                result = await obs.list_with_delimiter_async(default_store, prefix=path_prefix)
                objects = result.get("objects", [])

                # Look for README files (case-insensitive)
                readme_variations = ["readme.md", "readme.markdown", "readme.txt", "readme"]
                readme_file = None

                for obj_meta in objects:
                    location = obj_meta.get("path", "")
                    filename = location.split("/")[-1]

                    if filename.lower() in readme_variations:
                        readme_file = {
                            "path": location,
                            "filename": filename,
                            "size": obj_meta.get("size", 0),
                            "last_modified": str(obj_meta.get("last_modified", "")),
                        }
                        break

                if readme_file:
                    # Fetch README content
                    readme_url = f"{DATA_PROXY}/{readme_file['path']}"
                    readme_resp = await http_client.get(readme_url)

                    if readme_resp.status_code == 200:
                        product_data["readme"] = {
                            "found": True,
                            "content": readme_resp.text,
                            "size": readme_file["size"],
                            "path": readme_file["path"],
                            "filename": readme_file["filename"],
                            "last_modified": readme_file["last_modified"],
                            "url": readme_url,
                        }
                    else:
                        product_data["readme"] = {
                            "found": True,
                            "content": None,
                            "error": f"HTTP {readme_resp.status_code}",
                            "path": readme_file["path"],
                        }
                else:
                    product_data["readme"] = {"found": False, "content": None}

            except Exception as readme_error:
                logger.warning(f"Error fetching README: {readme_error}")
                product_data["readme"] = {"found": False, "error": str(readme_error)}

        return product_data

    except Exception as e:
        logger.error(f"Error fetching product details: {e}")
        raise


@mcp.tool()
async def list_product_files(
    account_id: str,
    product_id: str,
    prefix: str = "",
    max_files: int = 1000,
    show_tree: bool = False
) -> Dict:
    """
    List all files in a product with full S3 paths ready for analysis.
    Optionally show a hierarchical tree visualization with full paths.

    Args:
        account_id: Account ID
        product_id: Product ID
        prefix: Optional prefix to filter files (subdirectory path)
        max_files: Maximum files to return (default 1000)
        show_tree: If True, include tree visualization with full S3 paths (default False)

    Returns:
        Dict with files list, optional tree, directories, and statistics

    Example (List mode):
        >>> result = await list_product_files("harvard-lil", "gov-data", "metadata/")
        >>> print(result["files"][0])
        {
            "key": "harvard-lil/gov-data/metadata/metadata.jsonl.zip",
            "s3_uri": "s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/metadata/metadata.jsonl.zip",
            "http_url": "https://data.source.coop/harvard-lil/gov-data/metadata/metadata.jsonl.zip",
            "size": 1012127330,
            "last_modified": "2025-02-06T16:20:22+00:00",
            "etag": "..."
        }

    Example (Tree mode):
        >>> result = await list_product_files("harvard-lil", "gov-data", show_tree=True)
        >>> print(result["tree"])
        s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/
        ├── README.md (5.2 KB) → s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/README.md
        ├── metadata/
        │   ├── metadata.jsonl.zip (965.4 MB) → s3://.../metadata/metadata.jsonl.zip
        │   └── checksums.txt (1.2 KB)
        └── data/
            └── datasets.parquet (128.5 MB)
    """
    try:
        path_prefix = f"{account_id}/{product_id}/"
        if prefix:
            path_prefix += prefix.lstrip("/")

        logger.info(f"Listing files with prefix: {path_prefix} using obstore")

        if show_tree:
            # Recursive listing for tree view
            stream = obs.list(default_store, prefix=path_prefix, chunk_size=1000)

            all_files = []
            async for batch in stream:
                for obj_meta in batch:
                    location = obj_meta.get("path", "")

                    # Skip directory markers
                    if location.endswith("/"):
                        continue

                    all_files.append({
                        "key": location,
                        "s3_uri": f"s3://{DEFAULT_BUCKET}/{location}",
                        "http_url": f"{DATA_PROXY}/{location}",
                        "size": obj_meta.get("size", 0),
                        "last_modified": str(obj_meta.get("last_modified", "")),
                        "etag": obj_meta.get("e_tag"),
                    })

                    if len(all_files) >= max_files:
                        break

                if len(all_files) >= max_files:
                    break

            # Build tree structure
            tree_dict = {}
            total_size = 0

            for file_info in all_files:
                path = file_info["key"]
                size = file_info["size"]
                total_size += size

                # Split path into parts (remove prefix)
                relative_path = path[len(path_prefix):]
                parts = relative_path.split("/")

                # Build nested dictionary
                current = tree_dict
                for part in parts[:-1]:  # All parts except filename
                    if part not in current:
                        current[part] = {}
                    current = current[part]

                # Add file with metadata
                filename = parts[-1]
                current[filename] = {"size": size, "s3_uri": file_info["s3_uri"]}

            # Helper functions
            def format_size(bytes_size):
                """Convert bytes to human-readable format"""
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if bytes_size < 1024.0:
                        return f"{bytes_size:.1f} {unit}"
                    bytes_size /= 1024.0
                return f"{bytes_size:.1f} PB"

            def build_tree_lines(node, prefix="", current_path=""):
                """Recursively build tree visualization with full S3 paths"""
                lines = []
                items = sorted(node.items())

                for i, (name, value) in enumerate(items):
                    is_last = i == len(items) - 1
                    connector = "└── " if is_last else "├── "
                    extension = "    " if is_last else "│   "

                    item_path = f"{current_path}/{name}" if current_path else name

                    if isinstance(value, dict) and "size" in value:
                        # File
                        size_str = format_size(value["size"])
                        lines.append(f"{prefix}{connector}{name} ({size_str}) → {value['s3_uri']}")
                    else:
                        # Directory
                        dir_s3_path = f"s3://{DEFAULT_BUCKET}/{path_prefix}{item_path}/"
                        lines.append(f"{prefix}{connector}{name}/ → {dir_s3_path}")

                        # Recurse into subdirectory
                        lines.extend(build_tree_lines(value, prefix + extension, item_path))

                return lines

            # Build tree string
            root_path = f"s3://{DEFAULT_BUCKET}/{path_prefix}"
            tree_lines = [root_path]
            tree_lines.extend(build_tree_lines(tree_dict))
            tree_str = "\n".join(tree_lines)

            # Get directory list
            directories = []
            def extract_dirs(node, current_path=""):
                for name, value in node.items():
                    if isinstance(value, dict) and "size" not in value:
                        dir_path = f"{current_path}/{name}" if current_path else name
                        full_s3_path = f"s3://{DEFAULT_BUCKET}/{path_prefix}{dir_path}/"
                        directories.append({
                            "name": name,
                            "path": f"{path_prefix}{dir_path}/",
                            "s3_uri": full_s3_path
                        })
                        extract_dirs(value, dir_path)

            extract_dirs(tree_dict)

            return {
                "files": all_files,
                "directories": directories,
                "tree": tree_str,
                "stats": {
                    "total_files": len(all_files),
                    "total_directories": len(directories),
                    "total_size": total_size,
                    "total_size_human": format_size(total_size),
                    "truncated": len(all_files) >= max_files
                }
            }

        else:
            # Simple list with delimiter (current behavior)
            # Use async version for better performance
            result = await obs.list_with_delimiter_async(default_store, prefix=path_prefix)

            # Extract objects and common_prefixes
            objects = result.get("objects", [])
            common_prefixes = result.get("common_prefixes", [])

            files = []
            for obj_meta in objects[:max_files]:
                location = obj_meta.get("path", "")

                # Skip directory markers
                if location.endswith("/"):
                    continue

                files.append({
                    "key": location,
                    "s3_uri": f"s3://{DEFAULT_BUCKET}/{location}",
                    "http_url": f"{DATA_PROXY}/{location}",
                    "size": obj_meta.get("size", 0),
                    "last_modified": str(obj_meta.get("last_modified", "")),
                    "etag": obj_meta.get("e_tag"),
                })

            # Extract directories from common prefixes
            directories = []
            for prefix_path in common_prefixes:
                dir_name = prefix_path.rstrip("/").split("/")[-1]
                directories.append({
                    "name": dir_name,
                    "path": prefix_path,
                    "s3_uri": f"s3://{DEFAULT_BUCKET}/{prefix_path}"
                })

            logger.info(f"Found {len(files)} files and {len(directories)} directories")

            return {
                "files": files,
                "directories": directories,
                "stats": {
                    "total_files": len(files),
                    "total_directories": len(directories)
                }
            }

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise


@mcp.tool()
async def get_file_metadata(path: str) -> Dict:
    """
    Get metadata for a specific file without downloading it.
    Uses obstore's head operation for efficient metadata retrieval.

    Args:
        path: S3 URI (s3://...) or relative path (account_id/product_id/file)

    Returns:
        File metadata: size, content-type, last-modified, etag, URLs

    Example:
        >>> await get_file_metadata("harvard-lil/gov-data/README.md")
        {
            "key": "harvard-lil/gov-data/README.md",
            "content_type": "binary/octet-stream",
            "content_length": 5344,
            "last_modified": "2025-02-06T16:29:24+00:00",
            ...
        }
    """
    try:
        # Parse S3 path
        if path.startswith("s3://"):
            key = path.replace(f"s3://{DEFAULT_BUCKET}/", "")
        else:
            key = path

        logger.info(f"Fetching metadata for: {key} using obstore")

        # Use default store
        # TODO: Support different buckets if needed based on path analysis
        obj_meta = await obs.head_async(default_store, key)

        return {
            "key": key,
            "s3_uri": f"s3://{DEFAULT_BUCKET}/{key}",
            "http_url": f"{DATA_PROXY}/{key}",
            "size": obj_meta.get("size"),
            "last_modified": str(obj_meta.get("last_modified", "")),
            "etag": obj_meta.get("e_tag"),
            "version": obj_meta.get("version"),
        }

    except Exception as e:
        logger.error(f"Error fetching file metadata: {e}")
        raise


@mcp.tool()
async def search_products(
    query: str, account_id: Optional[str] = None, search_in: Optional[List[str]] = None
) -> List[Dict]:
    """
    Search for products across Source Cooperative.

    Args:
        query: Search term (case-insensitive)
        account_id: Optional account filter. RECOMMENDED for performance.
                   Without account_id, searches all 92 accounts (30-60s).
        search_in: Fields to search in (title, description, product_id).
                   Defaults to all fields if not specified.

    Returns:
        Matching products with relevance scoring

    Performance:
        - With account_id: ~200-500ms
        - Without account_id: ~30-60s (searches all 92 accounts)

    Examples:
        >>> # Fast search (recommended)
        >>> results = await search_products("climate", account_id="harvard-lil")

        >>> # Slow search (searches all accounts)
        >>> results = await search_products("climate")

        >>> print(results[0])
        {
            "product_id": "...",
            "title": "Climate Data...",
            "search_score": 5,
            "matched_fields": ["title", "description"]
        }
    """
    try:
        # Set default search fields if not provided
        if search_in is None:
            search_in = ["title", "description", "product_id"]

        logger.info(f"Searching for: '{query}' in {search_in}")
        products = await list_products(account_id=account_id)
        query_lower = query.lower()

        results = []
        for product in products:
            score = 0
            matches = []

            # Score matches by field
            if "title" in search_in:
                if query_lower in product.get("title", "").lower():
                    score += 3
                    matches.append("title")

            if "description" in search_in:
                if query_lower in product.get("description", "").lower():
                    score += 2
                    matches.append("description")

            if "product_id" in search_in:
                if query_lower in product.get("product_id", "").lower():
                    score += 5
                    matches.append("product_id")

            if score > 0:
                results.append({**product, "search_score": score, "matched_fields": matches})

        # Sort by relevance
        results.sort(key=lambda x: x["search_score"], reverse=True)
        logger.info(f"Found {len(results)} matching products")

        return results

    except Exception as e:
        logger.error(f"Error searching products: {e}")
        raise


@mcp.tool()
async def get_featured_products() -> List[Dict]:
    """
    Discover highlighted/featured datasets in Source Cooperative.
    These are curated, high-quality datasets selected by Source Cooperative.

    Returns:
        List of featured products

    Example:
        >>> featured = await get_featured_products()
        >>> print(f"Found {len(featured)} featured products")
    """
    return await list_products(featured_only=True)


# ============================================================================
# Server Startup
# ============================================================================


def main():
    """Entry point for the MCP server."""
    try:
        pkg_version = version("source-coop-mcp")
        logger.info(f"Starting Source Cooperative MCP Server v{pkg_version}")
    except PackageNotFoundError:
        logger.info("Starting Source Cooperative MCP Server")
    mcp.run()


if __name__ == "__main__":
    main()
