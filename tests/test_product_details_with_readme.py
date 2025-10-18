"""Test get_product_details with include_readme parameter"""

import asyncio
import httpx
import obstore as obs
from obstore.store import S3Store

BUCKET = "us-west-2.opendata.source.coop"
API_BASE = "https://source.coop/api/v1"
DATA_PROXY = "https://data.source.coop"


async def get_product_details(account_id: str, product_id: str, include_readme: bool = False):
    """Get product details with optional README content"""

    store = S3Store(BUCKET, region="us-west-2", skip_signature=True)
    http_client = httpx.AsyncClient(timeout=30.0)

    try:
        print(f"Fetching product details for {account_id}/{product_id}")
        resp = await http_client.get(f"{API_BASE}/products/{account_id}/{product_id}")
        resp.raise_for_status()

        product_data = resp.json()
        print(f"  ✓ Got product details: {product_data.get('title', 'N/A')}")

        # Optionally fetch README content
        if include_readme:
            print("  → Fetching README content...")
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
                        print(f"    ✓ Found README: {filename} ({readme_file['size']} bytes)")
                        break

                if readme_file:
                    # Fetch README content
                    readme_url = f"{DATA_PROXY}/{readme_file['path']}"
                    readme_resp = await http_client.get(readme_url)

                    if readme_resp.status_code == 200:
                        content = readme_resp.text
                        product_data["readme"] = {
                            "found": True,
                            "content": content,
                            "size": readme_file["size"],
                            "path": readme_file["path"],
                            "filename": readme_file["filename"],
                            "last_modified": readme_file["last_modified"],
                            "url": readme_url,
                        }
                        print(f"    ✓ README content: {len(content)} characters")
                    else:
                        product_data["readme"] = {
                            "found": True,
                            "content": None,
                            "error": f"HTTP {readme_resp.status_code}",
                            "path": readme_file["path"],
                        }
                        print(f"    ✗ Error fetching README: HTTP {readme_resp.status_code}")
                else:
                    product_data["readme"] = {"found": False, "content": None}
                    print("    ✗ No README found in product root")

            except Exception as readme_error:
                print(f"    ✗ Error: {readme_error}")
                product_data["readme"] = {"found": False, "error": str(readme_error)}

        return product_data

    finally:
        await http_client.aclose()


async def main():
    print("=" * 80)
    print("TEST: get_product_details with include_readme parameter")
    print("=" * 80)

    # Test 1: Without README (default behavior)
    print("\n### Test 1: maxar/maxar-opendata (include_readme=False)")
    result1 = await get_product_details("maxar", "maxar-opendata", include_readme=False)
    print(f"\nFields returned: {list(result1.keys())}")
    print(f"Has 'readme' field: {'readme' in result1}")

    # Test 2: With README
    print("\n\n### Test 2: maxar/maxar-opendata (include_readme=True)")
    result2 = await get_product_details("maxar", "maxar-opendata", include_readme=True)
    print(f"\nFields returned: {list(result2.keys())}")
    print(f"Has 'readme' field: {'readme' in result2}")
    if "readme" in result2 and result2["readme"]["found"]:
        print("\nREADME Preview:")
        print(result2["readme"]["content"][:200])
        print("...")

    # Test 3: Product without README
    print("\n\n### Test 3: youssef-harby/exiobase-3 (include_readme=True)")
    result3 = await get_product_details("youssef-harby", "exiobase-3", include_readme=True)
    print(f"\nFields returned: {list(result3.keys())}")
    print(f"Has 'readme' field: {'readme' in result3}")
    if "readme" in result3:
        print(f"README found: {result3['readme']['found']}")

    # Test 4: Another product with README
    print("\n\n### Test 4: planet/eu-field-boundaries (include_readme=True)")
    result4 = await get_product_details("planet", "eu-field-boundaries", include_readme=True)
    print(f"\nFields returned: {list(result4.keys())}")
    print(f"Has 'readme' field: {'readme' in result4}")
    if "readme" in result4 and result4["readme"]["found"]:
        print("\nREADME Preview:")
        print(result4["readme"]["content"][:200])
        print("...")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
