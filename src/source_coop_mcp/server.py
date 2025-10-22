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
from importlib.metadata import version, PackageNotFoundError
from difflib import SequenceMatcher

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration Constants
DEFAULT_BUCKET = "us-west-2.opendata.source.coop"
DEFAULT_REGION = "us-west-2"
API_BASE = "https://source.coop/api/v1"
DATA_PROXY = "https://data.source.coop"

# README is now always included in get_product_details() - no configuration needed!

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

        # Use list_with_delimiter to get top-level directories only (much faster!)
        # This is equivalent to: aws s3 ls s3://bucket/ --no-sign-request
        result = await obs.list_with_delimiter_async(default_store, prefix="")
        common_prefixes = result.get("common_prefixes", [])

        # Extract account names from prefixes (e.g., "harvard-lil/" -> "harvard-lil")
        accounts_list = sorted([prefix.rstrip("/") for prefix in common_prefixes])

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
async def get_product_details(account_id: str, product_id: str) -> Dict:
    """
    Get comprehensive metadata for a specific product.
    Always includes README content if found in the product root directory.

    Args:
        account_id: Account ID (e.g., "harvard-lil")
        product_id: Product ID (e.g., "gov-data")

    Returns:
        Full product metadata including account info, storage config, roles, tags
        Always includes 'readme' field with content and metadata (if README exists)

    Example:
        >>> await get_product_details("harvard-lil", "gov-data")
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
    """
    if http_client is None:
        raise RuntimeError("HTTP client not initialized. Server may not have started properly.")

    try:
        logger.info(f"Fetching details for {account_id}/{product_id}")
        resp = await http_client.get(f"{API_BASE}/products/{account_id}/{product_id}")
        resp.raise_for_status()

        product_data = resp.json()

        # Always fetch README content if it exists
        try:
            path_prefix = f"{account_id}/{product_id}/"
            logger.info(f"Fetching README for: {path_prefix}")

            # List files in product root only (non-recursive)
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
    show_tree: bool = True,
) -> Dict:
    """
    List all files in a product with full S3 paths ready for analysis.
    Optionally show a hierarchical tree visualization (optimized for LLM tokens).

    Args:
        account_id: Account ID
        product_id: Product ID
        prefix: Optional prefix to filter files (subdirectory path)
        max_files: Maximum files to return (default 1000)
        show_tree: If True, return tree visualization only (more token-efficient, default True)

    Returns:
        Dict with either files list OR tree visualization (not both to save tokens)

    Example (List mode - detailed metadata):
        >>> result = await list_product_files("harvard-lil", "gov-data", "metadata/")
        >>> print(result["files"][0])
        {
            "key": "harvard-lil/gov-data/metadata/metadata.jsonl.zip",
            "s3_uri": "s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/metadata/metadata.jsonl.zip",
            "http_url": "https://data.source.coop/harvard-lil/gov-data/metadata/metadata.jsonl.zip",
            "size": 1012127330,
            "last_modified": "2025-02-06T16:20:22+00:00"
        }

    Example (Tree mode - token optimized):
        >>> result = await list_product_files("harvard-lil", "gov-data", show_tree=True)
        >>> print(result["tree"])
        s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/
        ├── README.md (5.2 KB) → s3://...README.md
        ├── metadata/
        │   └── metadata.jsonl.zip (965.4 MB) → s3://...metadata.jsonl.zip
        └── data/
            └── datasets.parquet (128.5 MB) → s3://...datasets.parquet

    Example (Partitioned data - smart summarization):
        >>> result = await list_product_files("account", "product", show_tree=True)
        >>> print(result["tree"])
        s3://us-west-2.opendata.source.coop/account/product/
        ├── year={1995,1996,...,2007 (13 total)}/ [partitioned]
        │   └── format={ixi,pxp}/ [partitioned]
        │       └── matrix={F_impacts,F_satellite,Y,Z}/ [partitioned]
        │           └── data.parquet (5.1 MB)

        Note: Shows first,second,...,last (total) for >10 values; lists all for ≤10
        Tree mode saves ~70% tokens + smart partition detection saves 96%+ more
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

                    all_files.append(
                        {
                            "key": location,
                            "s3_uri": f"s3://{DEFAULT_BUCKET}/{location}",
                            "http_url": f"{DATA_PROXY}/{location}",
                            "size": obj_meta.get("size", 0),
                            "last_modified": str(obj_meta.get("last_modified", "")),
                            "etag": obj_meta.get("e_tag"),
                        }
                    )

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
                relative_path = path[len(path_prefix) :]
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

            def detect_partition_pattern(items_dict):
                """
                Detect partitioned data patterns like year=YYYY, format={value}, etc.
                Returns (is_partitioned, pattern_summary) or (False, None)
                """
                if not items_dict or len(items_dict) < 2:
                    return False, None

                # Check if all keys follow a partition pattern (key=value)
                keys = list(items_dict.keys())

                # Look for common partition key patterns
                partition_patterns = {}
                for key in keys:
                    if "=" in key:
                        parts = key.split("=", 1)
                        if len(parts) == 2:
                            partition_key, partition_value = parts
                            if partition_key not in partition_patterns:
                                partition_patterns[partition_key] = set()
                            partition_patterns[partition_key].add(partition_value)

                # If we found partition patterns and most/all keys follow this pattern
                if partition_patterns and len(partition_patterns) >= 1:
                    # Check if >50% of keys are partitioned
                    partitioned_keys = sum(1 for k in keys if "=" in k)
                    if partitioned_keys / len(keys) > 0.5:
                        # Build pattern summary
                        pattern_str = ""
                        for pkey, pvalues in sorted(partition_patterns.items()):
                            sorted_values = sorted(pvalues)
                            if len(sorted_values) <= 10:
                                # List all values if 10 or fewer
                                values_str = ",".join(sorted_values)
                            else:
                                # Show first, second, ..., last (total count) if more than 10
                                first = sorted_values[0]
                                second = sorted_values[1]
                                last = sorted_values[-1]
                                total = len(sorted_values)
                                values_str = f"{first},{second},...,{last} ({total} total)"
                            pattern_str += f"{pkey}={{{values_str}}}/"
                        return True, pattern_str.rstrip("/")

                return False, None

            def build_tree_lines(node, prefix="", current_path=""):
                """Recursively build tree visualization with partition detection"""
                lines = []
                items = sorted(node.items())

                # Detect if this level has partition patterns
                is_partitioned, pattern_summary = detect_partition_pattern(node)

                if is_partitioned and pattern_summary:
                    # Show summarized partition pattern instead of all values
                    item_path = (
                        f"{current_path}/{pattern_summary}" if current_path else pattern_summary
                    )
                    dir_s3_path = f"s3://{DEFAULT_BUCKET}/{path_prefix}{current_path}/"
                    lines.append(f"{prefix}├── {pattern_summary}/ [partitioned] → {dir_s3_path}")

                    # Get first item to show structure underneath
                    first_key = items[0][0]
                    first_value = items[0][1]
                    if isinstance(first_value, dict) and "size" not in first_value:
                        # Recurse into first partition to show structure
                        lines.extend(
                            build_tree_lines(
                                first_value,
                                prefix + "│   ",
                                f"{current_path}/{first_key}" if current_path else first_key,
                            )
                        )
                    return lines

                # Normal tree building
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
                        directories.append(
                            {
                                "name": name,
                                "path": f"{path_prefix}{dir_path}/",
                                "s3_uri": full_s3_path,
                            }
                        )
                        extract_dirs(value, dir_path)

            extract_dirs(tree_dict)

            # Return ONLY tree to save tokens (tree contains all info: paths, sizes, structure)
            # For 1000 files, this saves ~100,000+ tokens compared to returning both
            return {
                "tree": tree_str,
                "stats": {
                    "total_files": len(all_files),
                    "total_directories": len(directories),
                    "total_size": total_size,
                    "total_size_human": format_size(total_size),
                    "truncated": len(all_files) >= max_files,
                    "note": "Tree mode: file list omitted to save tokens. Parse tree for file paths and sizes.",
                },
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

                files.append(
                    {
                        "key": location,
                        "s3_uri": f"s3://{DEFAULT_BUCKET}/{location}",
                        "http_url": f"{DATA_PROXY}/{location}",
                        "size": obj_meta.get("size", 0),
                        "last_modified": str(obj_meta.get("last_modified", "")),
                        "etag": obj_meta.get("e_tag"),
                    }
                )

            # Extract directories from common prefixes
            directories = []
            for prefix_path in common_prefixes:
                dir_name = prefix_path.rstrip("/").split("/")[-1]
                directories.append(
                    {
                        "name": dir_name,
                        "path": prefix_path,
                        "s3_uri": f"s3://{DEFAULT_BUCKET}/{prefix_path}",
                    }
                )

            logger.info(f"Found {len(files)} files and {len(directories)} directories")

            return {
                "files": files,
                "directories": directories,
                "stats": {"total_files": len(files), "total_directories": len(directories)},
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
    Search for products across Source Cooperative with smart fuzzy matching.
    Handles typos, partial matches, and incomplete words using similarity scoring.

    Args:
        query: Search term (supports typos and partial matches)
        account_id: Optional account filter. RECOMMENDED for performance.
                   Without account_id, searches all 92 accounts (30-60s).
        search_in: Fields to search in (title, description, product_id).
                   Defaults to all fields if not specified.

    Returns:
        Matching products with relevance scoring (sorted by score)

    Performance:
        - With account_id: ~200-500ms
        - Without account_id: ~30-60s (searches all 92 accounts)

    Examples:
        >>> # Exact match
        >>> results = await search_products("climate", account_id="harvard-lil")

        >>> # Fuzzy match (typo)
        >>> results = await search_products("climte", account_id="harvard-lil")

        >>> # Partial match
        >>> results = await search_products("clim", account_id="harvard-lil")

        >>> print(results[0])
        {
            "product_id": "...",
            "title": "Climate Data...",
            "search_score": 5.8,
            "similarity": 0.95,
            "matched_fields": ["title"]
        }
    """
    try:
        # Set default search fields if not provided
        if search_in is None:
            search_in = ["title", "description", "product_id"]

        logger.info(f"Searching for: '{query}' in {search_in}")
        products = await list_products(account_id=account_id)
        query_lower = query.lower()

        # Fuzzy matching threshold (0-1, higher = more strict)
        FUZZY_THRESHOLD = 0.6

        def calculate_similarity(text1: str, text2: str) -> float:
            """Calculate similarity between two strings using SequenceMatcher"""
            return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

        def fuzzy_search_in_text(query: str, text: str) -> tuple[bool, float]:
            """
            Search for query in text using both exact and fuzzy matching.
            Returns (found, similarity_score)
            """
            text_lower = text.lower()

            # Exact substring match (highest score)
            if query in text_lower:
                return True, 1.0

            # Check similarity against individual words in text
            words = text_lower.split()
            best_similarity = 0.0

            for word in words:
                similarity = calculate_similarity(query, word)
                if similarity > best_similarity:
                    best_similarity = similarity

            # Also check similarity against the entire text (for multi-word queries)
            overall_similarity = calculate_similarity(query, text_lower)
            best_similarity = max(best_similarity, overall_similarity)

            # Return true if similarity exceeds threshold
            if best_similarity >= FUZZY_THRESHOLD:
                return True, best_similarity

            return False, best_similarity

        results = []
        for product in products:
            score = 0
            matches = []
            best_similarity = 0.0

            # Search in title
            if "title" in search_in:
                title = product.get("title", "")
                found, similarity = fuzzy_search_in_text(query_lower, title)
                if found:
                    # Exact match: 3 points, Fuzzy match: 1-3 points based on similarity
                    field_score = 3 if similarity == 1.0 else (1 + 2 * similarity)
                    score += field_score
                    matches.append("title")
                    best_similarity = max(best_similarity, similarity)

            # Search in description
            if "description" in search_in:
                description = product.get("description", "")
                found, similarity = fuzzy_search_in_text(query_lower, description)
                if found:
                    # Exact match: 2 points, Fuzzy match: 0.6-2 points based on similarity
                    field_score = 2 if similarity == 1.0 else (0.6 + 1.4 * similarity)
                    score += field_score
                    matches.append("description")
                    best_similarity = max(best_similarity, similarity)

            # Search in product_id
            if "product_id" in search_in:
                product_id = product.get("product_id", "")
                found, similarity = fuzzy_search_in_text(query_lower, product_id)
                if found:
                    # Exact match: 5 points, Fuzzy match: 2-5 points based on similarity
                    field_score = 5 if similarity == 1.0 else (2 + 3 * similarity)
                    score += field_score
                    matches.append("product_id")
                    best_similarity = max(best_similarity, similarity)

            if score > 0:
                results.append(
                    {
                        **product,
                        "search_score": round(score, 2),
                        "similarity": round(best_similarity, 2),
                        "matched_fields": matches,
                    }
                )

        # Sort by relevance (score first, then similarity)
        results.sort(key=lambda x: (x["search_score"], x["similarity"]), reverse=True)
        logger.info(f"Found {len(results)} matching products")

        return results

    except Exception as e:
        logger.error(f"Error searching products: {e}")
        raise


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
