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
import asyncio
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


async def _internal_list_accounts() -> List[str]:
    """
    Internal helper to list accounts (used by other functions).
    Uses S3 direct listing for reliability (API can return invalid JSON).
    """
    try:
        logger.info("Listing accounts from S3 (more reliable than API)")

        # Use S3 direct listing (same as list_accounts() tool)
        result = await obs.list_with_delimiter_async(default_store, prefix="")
        common_prefixes = result.get("common_prefixes", [])

        accounts = sorted([prefix.rstrip("/") for prefix in common_prefixes])
        logger.info(f"Discovered {len(accounts)} accounts from S3")
        return accounts
    except Exception as e:
        logger.error(f"Error listing accounts from S3: {e}")
        raise


async def _internal_list_products(
    account_id: Optional[str] = None,
    featured_only: bool = False,
    include_unpublished: bool = True,
    include_file_count: bool = True,
) -> List[Dict]:
    """
    Internal helper to list products (used by other functions).
    Hybrid approach: uses S3 by default (includes unpublished), API when include_unpublished=False.
    """
    # Use S3 direct listing by default (faster, includes unpublished)
    if include_unpublished:
        if not account_id:
            raise ValueError(
                "account_id is required when include_unpublished=True. "
                "Scanning all accounts in S3 would be too slow."
            )

        try:
            logger.info(f"Listing ALL products (including unpublished) for {account_id} from S3")

            # List all directories under account_id/ using delimiter
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
                        file_result = await obs.list_with_delimiter_async(
                            default_store, prefix=prefix
                        )
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

    # Default: Use API (published products only)
    if http_client is None:
        raise RuntimeError("HTTP client not initialized.")

    try:
        if account_id:
            # Query single account
            logger.info(f"Fetching products for account: {account_id}")
            resp = await http_client.get(f"{API_BASE}/products/{account_id}")

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    products = data.get("products", [])

                    if featured_only:
                        products = [p for p in products if p.get("featured") == 1]

                    logger.info(f"Found {len(products)} products for {account_id}")
                    return products
                except ValueError:
                    logger.error(
                        f"Invalid JSON response for account {account_id}: "
                        f"{resp.text[:200] if resp.text else '(empty response)'}"
                    )
                    raise ValueError(
                        f"API returned invalid JSON for account {account_id}. "
                        f"Response: {resp.text[:200] if resp.text else '(empty)'}"
                    )
            else:
                logger.warning(f"HTTP {resp.status_code} for account {account_id}")
                return []

        else:
            # Discover all products across all accounts
            logger.info("Discovering products from all accounts")
            accounts = await _internal_list_accounts()
            all_products = []

            for acc in accounts:
                try:
                    resp = await http_client.get(f"{API_BASE}/products/{acc}")
                    if resp.status_code == 200:
                        try:
                            products = resp.json().get("products", [])

                            if featured_only:
                                products = [p for p in products if p.get("featured") == 1]

                            all_products.extend(products)
                        except ValueError:
                            # JSON decode error - API returned non-JSON content
                            logger.warning(
                                f"Skipping account {acc}: Invalid JSON response "
                                f"(status {resp.status_code}, content: {resp.text[:100]}...)"
                            )
                            continue
                    else:
                        logger.debug(f"Skipping account {acc}: HTTP {resp.status_code}")
                except Exception as e:
                    logger.warning(f"Skipping account {acc}: {e}")
                    continue

            logger.info(f"Total products discovered: {len(all_products)}")
            return all_products

    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise


@mcp.tool()
async def list_products(
    account_id: Optional[str] = None,
    featured_only: bool = False,
    include_unpublished: bool = True,
    include_file_count: bool = True,
) -> List[Dict]:
    """
    List products (datasets) in Source Cooperative with hybrid S3 + API approach.

    DEFAULT: Uses S3 direct scan (fast, includes ALL products with file counts).
    Set include_unpublished=False for published-only with rich metadata from API.

    Args:
        account_id: Filter by specific account. REQUIRED for S3 mode (default).
                   If None with include_unpublished=False, lists published from all accounts.
        featured_only: Only return featured/curated products (API mode only).
        include_unpublished: If True (default), scan S3 for ALL products including unpublished.
                           If False, use API for published products with rich metadata.
        include_file_count: Count files in each product (default True, only in S3 mode).

    Returns:
        S3 mode (default): Basic info (product_id, s3_prefix, file_count) - fast!
        API mode: Rich metadata (product_id, title, description, dates) - slower

    Performance:
        - S3 mode (default): ~240ms, includes unpublished products + file counts
        - API mode (include_unpublished=False): ~500ms, rich metadata, published only

    Examples:
        >>> # ALL products with file counts (DEFAULT - fast!)
        >>> await list_products(account_id="youssef-harby")
        [
            {"product_id": "exiobase-3", "source": "s3", "file_count": 1000, ...},
            {"product_id": "egms-copernicus", "source": "s3", "file_count": 53, ...},
            ...
        ]

        >>> # Published products with rich metadata (API mode)
        >>> await list_products(account_id="youssef-harby", include_unpublished=False)
        [{"product_id": "egms-copernicus", "title": "...", "description": "...", ...}]

        >>> # Fast mode without file counts
        >>> await list_products(account_id="youssef-harby", include_file_count=False)
        [{"product_id": "exiobase-3", "source": "s3", ...}]

        >>> # Featured products only (requires API mode)
        >>> await list_products(featured_only=True, include_unpublished=False)
        [{"product_id": "gov-data", "featured": 1, ...}]
    """
    return await _internal_list_products(
        account_id=account_id,
        featured_only=featured_only,
        include_unpublished=include_unpublished,
        include_file_count=include_file_count,
    )


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

            def detect_numbered_files(items_dict):
                """
                Detect numbered file patterns like 0.parquet, 1.parquet, ..., 80.parquet
                Returns (is_numbered, pattern_summary, size_range) or (False, None, None)
                """
                if not items_dict or len(items_dict) < 3:
                    return False, None, None

                # Check if items are files (have 'size' key) and follow numbered pattern
                files_info = []
                for name, value in items_dict.items():
                    if isinstance(value, dict) and "size" in value:
                        # Try to extract number from filename
                        base_name = name.rsplit(".", 1)[0] if "." in name else name
                        if base_name.isdigit():
                            files_info.append((int(base_name), name, value["size"]))

                # If we found numbered files and they represent >70% of items
                if files_info and len(files_info) / len(items_dict) > 0.7:
                    files_info.sort(key=lambda x: x[0])
                    numbers = [f[0] for f in files_info]

                    # Check if numbers are sequential or close to sequential
                    min_num = numbers[0]
                    max_num = numbers[-1]
                    expected_count = max_num - min_num + 1

                    # If we have most of the expected sequence
                    if len(numbers) / expected_count > 0.8:
                        # Get file extension from first file
                        extension = (
                            files_info[0][1].split(".")[-1] if "." in files_info[0][1] else ""
                        )

                        # Calculate size range
                        sizes = [f[2] for f in files_info]
                        min_size = min(sizes)
                        max_size = max(sizes)
                        total_size = sum(sizes)

                        pattern = (
                            f"[{min_num}-{max_num}].{extension}"
                            if extension
                            else f"[{min_num}-{max_num}]"
                        )
                        size_range = {
                            "min": min_size,
                            "max": max_size,
                            "total": total_size,
                            "count": len(files_info),
                        }
                        return True, pattern, size_range

                return False, None, None

            def detect_date_directories(items_dict):
                """
                Detect date directory patterns like 2024-11-19/, 2024-12-03/, 2025-01-10/
                Returns (is_date_pattern, dates_summary) or (False, None)
                """
                if not items_dict or len(items_dict) < 2:
                    return False, None

                import re

                date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

                date_dirs = []
                for name, value in items_dict.items():
                    if isinstance(value, dict) and "size" not in value:  # It's a directory
                        if date_pattern.match(name):
                            date_dirs.append(name)

                # If we found date directories and they represent >70% of directories
                if date_dirs and len(date_dirs) / len(items_dict) > 0.7:
                    date_dirs.sort()
                    if len(date_dirs) <= 5:
                        dates_str = ", ".join(date_dirs)
                    else:
                        dates_str = f"{date_dirs[0]}, {date_dirs[1]}, ..., {date_dirs[-1]}"

                    summary = f"{{{dates_str}}} ({len(date_dirs)} temporal snapshots)"
                    return True, summary

                return False, None

            def detect_general_file_pattern(items_dict):
                """
                Dynamically detect ANY repetitive file naming pattern.
                Analyzes common structures without hardcoding specific patterns.
                Returns (is_pattern, pattern_summary, size_range, sample_files) or (False, None, None, None)
                """
                if not items_dict or len(items_dict) < 10:  # Need at least 10 files for pattern
                    return False, None, None, None

                # Collect all files (not directories)
                files = []
                for name, value in items_dict.items():
                    if isinstance(value, dict) and "size" in value:
                        files.append((name, value["size"], value.get("s3_uri", "")))

                if len(files) < 10:
                    return False, None, None, None

                # Group files by extension
                from collections import defaultdict

                by_extension = defaultdict(list)
                for name, size, s3_uri in files:
                    if "." in name:
                        ext = name.rsplit(".", 1)[1]
                        base = name.rsplit(".", 1)[0]
                        by_extension[ext].append((base, size, s3_uri, name))

                # Find the largest group
                largest_group = None
                largest_ext = None
                for ext, group in by_extension.items():
                    if not largest_group or len(group) > len(largest_group):
                        largest_group = group
                        largest_ext = ext

                if not largest_group or len(largest_group) < 10:
                    return False, None, None, None

                # Check if this group represents >60% of all files (more lenient)
                if len(largest_group) / len(files) <= 0.6:
                    return False, None, None, None

                # Analyze the naming pattern in the largest group
                basenames = [item[0] for item in largest_group]

                # Find longest common prefix
                if not basenames:
                    return False, None, None, None

                prefix = basenames[0]
                for name in basenames[1:]:
                    while prefix and not name.startswith(prefix):
                        prefix = prefix[:-1]

                # Find longest common suffix
                suffix = basenames[0][::-1]
                for name in basenames[1:]:
                    reversed_name = name[::-1]
                    while suffix and not reversed_name.startswith(suffix):
                        suffix = suffix[:-1]
                suffix = suffix[::-1]

                # Extract varying parts
                varying_parts = []
                for basename in basenames:
                    varying = basename
                    if prefix:
                        varying = varying[len(prefix) :]
                    if suffix:
                        varying = varying[: -len(suffix)] if suffix else varying
                    varying_parts.append(varying)

                # Check if we have meaningful variation
                unique_parts = set(varying_parts)

                # NEW: More flexible check - even with no common prefix/suffix,
                # if we have many unique variations, it's still a pattern worth summarizing
                if len(unique_parts) < 3:
                    return False, None, None, None

                # Calculate size stats
                sizes = [item[1] for item in largest_group]
                min_size = min(sizes)
                max_size = max(sizes)
                total_size = sum(sizes)

                # Create pattern summary
                if prefix or suffix:
                    # We have common prefix/suffix
                    if len(unique_parts) <= 3:
                        variations = sorted(unique_parts)
                        variations_str = ",".join(variations[:3])
                        pattern_desc = f"{prefix}{{{variations_str}}}{suffix}.{largest_ext}"
                    else:
                        sorted_parts = sorted(unique_parts)
                        pattern_desc = (
                            f"{prefix}{{{sorted_parts[0]},{sorted_parts[1]},...,"
                            f"{sorted_parts[-1]} ({len(unique_parts)} variants)}}{suffix}.{largest_ext}"
                        )
                else:
                    # No common prefix/suffix - show samples and count
                    sorted_parts = sorted(unique_parts)
                    if len(unique_parts) <= 5:
                        samples = ",".join(sorted_parts[:5])
                        pattern_desc = f"{{{samples}}}.{largest_ext}"
                    else:
                        pattern_desc = (
                            f"{{{sorted_parts[0]},{sorted_parts[1]},{sorted_parts[2]},...,"
                            f"{sorted_parts[-1]} ({len(unique_parts)} coordinate tiles)}}.{largest_ext}"
                        )

                size_range = {
                    "min": min_size,
                    "max": max_size,
                    "total": total_size,
                    "count": len(largest_group),
                }

                # Sample files for reference (full S3 URIs)
                sample_files = [item[2] for item in largest_group[:3]]  # Get 3 sample S3 URIs

                return True, pattern_desc, size_range, sample_files

            def build_tree_lines(node, prefix="", current_path=""):
                """
                Recursively build tree visualization with smart pattern detection.
                Detects: numbered files, date directories, general file patterns, and Hive partitions.
                """
                lines = []
                items = sorted(node.items())

                # 1. Check for numbered file patterns (highest priority for files)
                is_numbered, num_pattern, size_range = detect_numbered_files(node)
                if is_numbered and num_pattern and size_range:
                    # Show summarized numbered file pattern
                    min_size_str = format_size(size_range["min"])
                    max_size_str = format_size(size_range["max"])
                    total_size_str = format_size(size_range["total"])
                    count = size_range["count"]

                    full_path = f"{path_prefix}{current_path}".rstrip("/")
                    dir_s3_path = f"s3://{DEFAULT_BUCKET}/{full_path}/"
                    lines.append(
                        f"{prefix}├── {num_pattern} ({count} files, {min_size_str} - {max_size_str}, "
                        f"total: {total_size_str}) → {dir_s3_path}"
                    )

                    # Show any non-numbered files in the same directory
                    for name, value in items:
                        if isinstance(value, dict) and "size" in value:
                            base_name = name.rsplit(".", 1)[0] if "." in name else name
                            if not base_name.isdigit():
                                size_str = format_size(value["size"])
                                lines.append(f"{prefix}├── {name} ({size_str}) → {value['s3_uri']}")
                        elif isinstance(value, dict) and "size" not in value:
                            # Show subdirectories
                            item_path = f"{current_path}/{name}" if current_path else name
                            dir_path = f"s3://{DEFAULT_BUCKET}/{path_prefix}{item_path}/"
                            lines.append(f"{prefix}├── {name}/ → {dir_path}")
                            lines.extend(build_tree_lines(value, prefix + "│   ", item_path))

                    return lines

                # 2. Check for date directory patterns
                is_date_pattern, dates_summary = detect_date_directories(node)
                if is_date_pattern and dates_summary:
                    # Show summarized date directories
                    full_path = f"{path_prefix}{current_path}".rstrip("/")
                    dir_s3_path = f"s3://{DEFAULT_BUCKET}/{full_path}/"
                    lines.append(f"{prefix}├── {dates_summary} → {dir_s3_path}")

                    # Get first date directory to show structure underneath
                    date_dirs = sorted(
                        [
                            name
                            for name, value in items
                            if isinstance(value, dict) and "size" not in value
                        ]
                    )
                    if date_dirs:
                        first_date = date_dirs[0]
                        first_value = node[first_date]
                        item_path = f"{current_path}/{first_date}" if current_path else first_date

                        # Show structure of first date directory
                        lines.append(f"{prefix}│   Example structure from {first_date}/:")
                        lines.extend(build_tree_lines(first_value, prefix + "│   ", item_path))

                    return lines

                # 3. Check for general file patterns (e.g., geo-tiles, coordinates, etc.)
                is_general_pattern, pattern_desc, size_range, sample_files = (
                    detect_general_file_pattern(node)
                )
                if is_general_pattern and pattern_desc and size_range:
                    # Show summarized general file pattern
                    min_size_str = format_size(size_range["min"])
                    max_size_str = format_size(size_range["max"])
                    total_size_str = format_size(size_range["total"])
                    count = size_range["count"]

                    full_path = f"{path_prefix}{current_path}".rstrip("/")
                    dir_s3_path = f"s3://{DEFAULT_BUCKET}/{full_path}/"
                    lines.append(
                        f"{prefix}├── {pattern_desc} ({count} files, {min_size_str} - {max_size_str}, "
                        f"total: {total_size_str}) → {dir_s3_path}"
                    )

                    # Show sample files with full S3 paths for LLM awareness
                    if sample_files:
                        lines.append(f"{prefix}│   Sample files:")
                        for s3_uri in sample_files[:2]:  # Show 2 full examples
                            lines.append(f"{prefix}│     • {s3_uri}")

                    # Show any non-pattern files or subdirectories
                    for name, value in items:
                        if isinstance(value, dict) and "size" not in value:
                            # Show subdirectories
                            item_path = f"{current_path}/{name}" if current_path else name
                            dir_path = f"s3://{DEFAULT_BUCKET}/{path_prefix}{item_path}/"
                            lines.append(f"{prefix}├── {name}/ → {dir_path}")
                            lines.extend(build_tree_lines(value, prefix + "│   ", item_path))

                    return lines

                # 4. Check for Hive-style partition patterns
                is_partitioned, pattern_summary = detect_partition_pattern(node)
                if is_partitioned and pattern_summary:
                    # Show summarized partition pattern instead of all values
                    item_path = (
                        f"{current_path}/{pattern_summary}" if current_path else pattern_summary
                    )
                    full_path = f"{path_prefix}{current_path}".rstrip("/")
                    dir_s3_path = f"s3://{DEFAULT_BUCKET}/{full_path}/"
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

                # 5. Normal tree building (no patterns detected)
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
async def search(query: str) -> List[Dict]:
    """
    Search for products across ALL accounts with smart fuzzy matching.
    Handles typos, partial matches, and incomplete words using 60% similarity threshold.

    **Hybrid Search** - Automatically searches across:
    - All 94+ organizations
    - ALL products (published + unpublished)
    - All fields: title, description, product_id

    Published products: Full metadata (title, description, product_id)
    Unpublished products: product_id only (no title/description available)

    Args:
        query: Search keyword (supports typos and partial matches)

    Returns:
        **Top 5** matching accounts or products (sorted by relevance score)

    Performance:
        ~5-8s (parallel 2-level S3 scan + top 5 API enrichment)

        Performance breakdown:
        - S3 parallel listing: ~2.4s (94 accounts + 354 products)
        - Fuzzy matching: <1s (in-memory processing)
        - API enrichment: ~2-5s (only top 5 results)

        **11x faster** than sequential approach (was ~27s)
        **Uses 2-level delimiter listing** (not full recursive scan)

    Examples:
        >>> # Exact match
        >>> results = await search("climate")

        >>> # Fuzzy match (handles typos)
        >>> results = await search("climte")  # Finds "climate"
        >>> results = await search("exiopase")  # Finds "exiobase-3" (includes unpublished!)

        >>> # Partial match
        >>> results = await search("geo")  # Finds "geospatial", "geocoding", etc.

        >>> # Result formats
        >>> print(results[0])  # Account match
        {
            "type": "account",
            "account_id": "harvard-lil",
            "match_string": "harvard-lil",
            "search_score": 9.5,
            "similarity": 0.95,
            "matched_fields": ["account_id"]
        }

        >>> print(results[1])  # Product match
        {
            "type": "product",
            "account_id": "youssef-harby",
            "product_id": "exiobase-3",
            "match_string": "youssef-harby/exiobase-3",
            "title": "",  # Empty for unpublished products
            "description": "",  # Empty for unpublished products
            "search_score": 8.2,
            "similarity": 0.82,
            "matched_fields": ["product_id"]
        }
    """
    try:
        logger.info(f"Searching for: '{query}' across ALL accounts (published + unpublished)")

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

        # OPTIMIZED: Parallel 2-level delimiter listing (fast, only scans directory structure)
        # Level 1: Get all accounts
        # Level 2: Get products for each account IN PARALLEL
        logger.info("Discovering all accounts and products via parallel 2-level S3 listing...")

        # Get all accounts (Level 1)
        accounts = await _internal_list_accounts()
        logger.info(f"Found {len(accounts)} accounts")

        # Get products for ALL accounts in parallel (Level 2)
        products_by_id = {}  # Key: "account/product", Value: {account_id, product_id}

        # Parallel execution using asyncio.gather
        async def get_account_products(account: str):
            """Get products for a single account"""
            try:
                result = await obs.list_with_delimiter_async(default_store, prefix=f"{account}/")
                prefixes = result.get("common_prefixes", [])

                account_products = []
                for prefix in prefixes:
                    product_id = prefix.rstrip("/").split("/")[-1]
                    account_products.append(
                        {
                            "account_id": account,
                            "product_id": product_id,
                            "title": "",  # No title from S3 (unpublished)
                            "description": "",  # No description from S3
                            "source": "s3_discovered",
                        }
                    )
                return account_products
            except Exception as e:
                logger.warning(f"Failed to list products for {account}: {e}")
                return []

        # Execute all account listings in parallel
        logger.info(f"Listing products for {len(accounts)} accounts in parallel...")
        results = await asyncio.gather(*[get_account_products(acc) for acc in accounts])

        # Flatten results and deduplicate
        for account_products in results:
            for product in account_products:
                key = f"{product['account_id']}/{product['product_id']}"
                products_by_id[key] = product

        all_products = list(products_by_id.values())
        logger.info(f"Discovered {len(all_products)} products from {len(accounts)} accounts")

        # Search account names themselves
        all_results = []  # Will contain both account matches and product matches

        for account in accounts:
            found, similarity = fuzzy_search_in_text(query_lower, account)
            if found:
                all_results.append(
                    {
                        "type": "account",
                        "account_id": account,
                        "match_string": account,
                        "search_score": 10 * similarity,  # High score for account matches
                        "similarity": similarity,
                        "matched_fields": ["account_id"],
                    }
                )

        search_in = ["title", "description", "product_id"]
        logger.info(f"Fuzzy matching {query} against {len(all_products)} products...")

        # Now search through products
        for product in all_products:
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
                all_results.append(
                    {
                        "type": "product",
                        "match_string": f"{product.get('account_id')}/{product.get('product_id')}",
                        **product,
                        "search_score": round(score, 2),
                        "similarity": round(best_similarity, 2),
                        "matched_fields": matches,
                    }
                )

        # Sort by relevance (score first, then similarity)
        all_results.sort(key=lambda x: (x["search_score"], x["similarity"]), reverse=True)

        # Get top 5 results
        top_results = all_results[:5]
        logger.info(f"Found {len(all_results)} total matches, selecting top {len(top_results)}")

        # Enrich top 5 product results with API metadata (if published)
        logger.info("Enriching top 5 results with API metadata...")
        for result in top_results:
            if result.get("type") == "product" and result.get("source") == "s3_discovered":
                try:
                    # Fetch full metadata from API directly
                    account_id = result.get("account_id")
                    product_id = result.get("product_id")

                    resp = await http_client.get(f"{API_BASE}/products/{account_id}/{product_id}")
                    if resp.status_code == 200:
                        details = resp.json()
                        # Update result with rich metadata
                        result["title"] = details.get("title", "")
                        result["description"] = details.get("description", "")
                        result["source"] = "api_enriched"
                    else:
                        # Not published or not found
                        result["source"] = "s3_unpublished"
                except Exception as e:
                    # Product is unpublished or API failed - keep S3 data
                    logger.debug(f"Could not enrich {result.get('match_string')}: {e}")
                    result["source"] = "s3_unpublished"

        logger.info(f"Returning top {len(top_results)} results")
        return top_results

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
