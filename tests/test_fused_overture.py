"""Test README integration with fused/overture product"""

import asyncio
import httpx
import obstore as obs
from obstore.store import S3Store

BUCKET = "us-west-2.opendata.source.coop"
API_BASE = "https://source.coop/api/v1"
DATA_PROXY = "https://data.source.coop"


async def get_product_details_with_readme(
    account_id: str, product_id: str, include_readme: bool = False
):
    """Get product details with optional README content"""

    store = S3Store(BUCKET, region="us-west-2", skip_signature=True)
    http_client = httpx.AsyncClient(timeout=30.0)

    try:
        print(f"Fetching product details: {account_id}/{product_id}")
        print(f"Include README: {include_readme}")
        print("-" * 80)

        # Get product details from API
        resp = await http_client.get(f"{API_BASE}/products/{account_id}/{product_id}")
        resp.raise_for_status()

        product_data = resp.json()

        print(f"\n✓ Product Title: {product_data.get('title', 'N/A')}")
        print(f"✓ Description: {product_data.get('description', 'N/A')[:100]}...")
        print(f"✓ Created: {product_data.get('created_at', 'N/A')}")
        print(f"✓ Visibility: {product_data.get('visibility', 'N/A')}")

        # Optionally fetch README content
        if include_readme:
            print("\n" + "=" * 80)
            print("FETCHING README CONTENT")
            print("=" * 80)

            try:
                path_prefix = f"{account_id}/{product_id}/"

                # List files in product root only (non-recursive)
                result = obs.list_with_delimiter(store, prefix=path_prefix)
                objects = result.get("objects", [])

                print(f"\nFiles in product root: {len(objects)}")
                for obj in objects[:5]:
                    print(f"  - {obj.get('path', '').split('/')[-1]}")

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
                        print(f"\n✓ Found README: {filename}")
                        print(f"  Path: {location}")
                        print(f"  Size: {readme_file['size']} bytes")
                        print(f"  Last Modified: {readme_file['last_modified']}")
                        break

                if readme_file:
                    # Fetch README content
                    readme_url = f"{DATA_PROXY}/{readme_file['path']}"
                    print(f"\nFetching from: {readme_url}")

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

                        print("\n✓ README fetched successfully!")
                        print(f"  Content length: {len(content)} characters")
                        print(f"  Lines: {content.count(chr(10)) + 1}")

                        # Show preview
                        print("\n" + "=" * 80)
                        print("README CONTENT PREVIEW (first 500 characters)")
                        print("=" * 80)
                        print(content[:500])
                        print("...")

                        # Show last part
                        print("\n" + "=" * 80)
                        print("README CONTENT PREVIEW (last 300 characters)")
                        print("=" * 80)
                        print("...")
                        print(content[-300:])

                    else:
                        product_data["readme"] = {
                            "found": True,
                            "content": None,
                            "error": f"HTTP {readme_resp.status_code}",
                            "path": readme_file["path"],
                        }
                        print(f"\n✗ Error fetching README: HTTP {readme_resp.status_code}")
                else:
                    product_data["readme"] = {"found": False, "content": None}
                    print("\n✗ No README found in product root")

            except Exception as readme_error:
                print(f"\n✗ Error: {readme_error}")
                product_data["readme"] = {"found": False, "error": str(readme_error)}

        return product_data

    finally:
        await http_client.aclose()


async def main():
    print("=" * 80)
    print("TEST: fused/overture - README Integration")
    print("=" * 80)

    # Test 1: Without README
    print("\n### Test 1: Get product details WITHOUT README")
    result1 = await get_product_details_with_readme("fused", "overture", include_readme=False)
    print(f"\n✓ Response has 'readme' field: {'readme' in result1}")

    # Test 2: With README
    print("\n\n### Test 2: Get product details WITH README")
    result2 = await get_product_details_with_readme("fused", "overture", include_readme=True)
    print(f"\n✓ Response has 'readme' field: {'readme' in result2}")

    if "readme" in result2 and result2["readme"]["found"]:
        readme_info = result2["readme"]
        print(f"✓ README found: {readme_info['filename']}")
        print(f"✓ README size: {readme_info['size']} bytes")
        print(f"✓ README content length: {len(readme_info['content'])} characters")
        print(f"✓ README URL: {readme_info['url']}")

        # Check content
        assert "Overture" in readme_info["content"], "Expected 'Overture' in README"
        assert "Fused" in readme_info["content"], "Expected 'Fused' in README"
        print("\n✓ All assertions passed!")

    print("\n" + "=" * 80)
    print("TEST COMPLETE - SUCCESS!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
