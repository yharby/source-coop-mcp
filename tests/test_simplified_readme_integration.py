"""Test simplified README integration with get_product_details only"""

import asyncio
import httpx
import obstore as obs
from obstore.store import S3Store
import os

BUCKET = "us-west-2.opendata.source.coop"
API_BASE = "https://source.coop/api/v1"
DATA_PROXY = "https://data.source.coop"


async def get_product_details(account_id: str, product_id: str, include_readme=None):
    """Get product details with optional README (mimics the actual tool)"""

    # Environment variable configuration
    INCLUDE_README_DEFAULT = os.getenv("SOURCE_COOP_INCLUDE_README", "false").lower() in [
        "true",
        "1",
        "yes",
    ]

    # Use environment variable default if not explicitly specified
    if include_readme is None:
        include_readme = INCLUDE_README_DEFAULT

    store = S3Store(BUCKET, region="us-west-2", skip_signature=True)
    http_client = httpx.AsyncClient(timeout=30.0)

    try:
        # Get product details from API
        resp = await http_client.get(f"{API_BASE}/products/{account_id}/{product_id}")
        resp.raise_for_status()

        product_data = resp.json()

        # Optionally fetch README content
        if include_readme:
            try:
                path_prefix = f"{account_id}/{product_id}/"

                # List files in product root only (non-recursive)
                result = obs.list_with_delimiter(store, prefix=path_prefix)
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
                product_data["readme"] = {"found": False, "error": str(readme_error)}

        return product_data

    finally:
        await http_client.aclose()


async def main():
    print("=" * 80)
    print("TEST: Simplified README Integration (Single Tool)")
    print("=" * 80)

    # Test 1: Default behavior (no README)
    print("\n### Test 1: Default behavior (include_readme not specified)")
    print("Environment: SOURCE_COOP_INCLUDE_README not set")
    os.environ.pop("SOURCE_COOP_INCLUDE_README", None)
    result1 = await get_product_details("fused", "overture")
    has_readme1 = "readme" in result1
    print(f"✓ Title: {result1['title']}")
    print(f"✓ Has 'readme' field: {has_readme1}")
    assert not has_readme1, "README should NOT be included by default"
    print("✓ PASS: README not included (expected)")

    # Test 2: Explicit include_readme=True
    print("\n\n### Test 2: Explicit include_readme=True")
    print("Environment: SOURCE_COOP_INCLUDE_README not set")
    os.environ.pop("SOURCE_COOP_INCLUDE_README", None)
    result2 = await get_product_details("fused", "overture", include_readme=True)
    has_readme2 = "readme" in result2
    print(f"✓ Title: {result2['title']}")
    print(f"✓ Has 'readme' field: {has_readme2}")
    assert has_readme2, "README should be included when explicitly requested"
    assert result2["readme"]["found"], "README should be found"
    assert "Overture" in result2["readme"]["content"], "README content should contain 'Overture'"
    print(f"✓ PASS: README included (size: {result2['readme']['size']} bytes)")
    print(f"✓ Content preview: {result2['readme']['content'][:100]}...")

    # Test 3: With env var set to true
    print("\n\n### Test 3: Environment variable SOURCE_COOP_INCLUDE_README=true")
    print("Environment: SOURCE_COOP_INCLUDE_README=true")
    os.environ["SOURCE_COOP_INCLUDE_README"] = "true"
    result3 = await get_product_details("fused", "overture")  # No explicit parameter
    has_readme3 = "readme" in result3
    print(f"✓ Title: {result3['title']}")
    print(f"✓ Has 'readme' field: {has_readme3}")
    assert has_readme3, "README should be included when env var is true"
    assert result3["readme"]["found"], "README should be found"
    print(
        f"✓ PASS: README automatically included via env var (size: {result3['readme']['size']} bytes)"
    )

    # Test 4: Explicit False overrides env var
    print("\n\n### Test 4: Explicit include_readme=False overrides env var")
    print("Environment: SOURCE_COOP_INCLUDE_README=true")
    os.environ["SOURCE_COOP_INCLUDE_README"] = "true"
    result4 = await get_product_details("fused", "overture", include_readme=False)
    has_readme4 = "readme" in result4
    print(f"✓ Title: {result4['title']}")
    print(f"✓ Has 'readme' field: {has_readme4}")
    assert not has_readme4, "Explicit False should override env var"
    print("✓ PASS: Explicit parameter overrides env var")

    # Test 5: Product without README
    print("\n\n### Test 5: Product without README (youssef-harby/exiobase-3)")
    print("Environment: SOURCE_COOP_INCLUDE_README not set")
    os.environ.pop("SOURCE_COOP_INCLUDE_README", None)
    result5 = await get_product_details("youssef-harby", "exiobase-3", include_readme=True)
    has_readme5 = "readme" in result5
    print(f"✓ Title: {result5['title']}")
    print(f"✓ Has 'readme' field: {has_readme5}")
    if has_readme5:
        print(f"✓ README found: {result5['readme']['found']}")
        assert not result5["readme"]["found"], "README should not be found for exiobase-3"
        print("✓ PASS: Correctly reports README not found")

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED!")
    print("=" * 80)
    print("\nSummary:")
    print("✓ Default behavior: No README (backward compatible)")
    print("✓ Explicit parameter: Works as expected")
    print("✓ Environment variable: Controls default behavior")
    print("✓ Parameter override: Explicit parameter overrides env var")
    print("✓ Missing README: Handled gracefully")


if __name__ == "__main__":
    asyncio.run(main())
