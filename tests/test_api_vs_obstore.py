"""
Compare HTTP API results vs obstore (direct S3) results
to demonstrate discrepancies in product listings
"""

import asyncio
import httpx
import obstore as obs
from obstore.store import S3Store

BUCKET = "us-west-2.opendata.source.coop"
API_BASE = "https://source.coop/api/v1"


async def main():
    print("=" * 80)
    print("COMPARISON: HTTP API vs obstore (Direct S3)")
    print("=" * 80)

    # Initialize clients
    store = S3Store(BUCKET, region="us-west-2", skip_signature=True)
    http_client = httpx.AsyncClient(timeout=30.0)

    # Test account
    account_id = "youssef-harby"

    # ========================================================================
    # METHOD 1: HTTP API
    # ========================================================================
    print(f"\nMETHOD 1: HTTP API - GET {API_BASE}/products/{account_id}")
    print("-" * 80)

    try:
        resp = await http_client.get(f"{API_BASE}/products/{account_id}")
        if resp.status_code == 200:
            data = resp.json()
            api_products = data.get("products", [])

            print(f"Status: {resp.status_code}")
            print(f"Found {len(api_products)} products via API")
            print("\nProducts returned by API:")
            for i, product in enumerate(api_products, 1):
                print(f"  {i}. {product['product_id']}")
                print(f"     Title: {product.get('title', 'N/A')}")

            api_product_ids = {p["product_id"] for p in api_products}
        else:
            print(f"HTTP Error: {resp.status_code}")
            api_product_ids = set()
    except Exception as e:
        print(f"Error: {e}")
        api_product_ids = set()

    # ========================================================================
    # METHOD 2: obstore (Direct S3)
    # ========================================================================
    print(f"\nMETHOD 2: obstore - Direct S3 listing of {account_id}/")
    print("-" * 80)

    try:
        # List all objects under youssef-harby/ to find product directories
        result = obs.list_with_delimiter(store, prefix=f"{account_id}/")

        # Extract common prefixes (directories = products)
        common_prefixes = result.get("common_prefixes", [])

        s3_products = []
        for prefix in common_prefixes:
            # prefix looks like: 'youssef-harby/product-name/'
            product_id = prefix.rstrip("/").split("/")[-1]
            s3_products.append(product_id)

        print(f"Found {len(s3_products)} products via S3 (obstore)")
        print("\nProducts found in S3 bucket:")
        for i, product_id in enumerate(sorted(s3_products), 1):
            print(f"  {i}. {product_id}")

        s3_product_ids = set(s3_products)
    except Exception as e:
        print(f"Error: {e}")
        s3_product_ids = set()

    # ========================================================================
    # COMPARISON
    # ========================================================================
    print("\nCOMPARISON RESULTS")
    print("=" * 80)

    print(f"\nAPI Products:    {sorted(api_product_ids)}")
    print(f"S3 Products:     {sorted(s3_product_ids)}")

    # Find missing products
    missing_in_api = s3_product_ids - api_product_ids
    missing_in_s3 = api_product_ids - s3_product_ids

    if missing_in_api:
        print("\nDISCREPANCY FOUND!")
        print(f"Products in S3 but NOT in API: {sorted(missing_in_api)}")
        print("   → These products exist on S3 but the API doesn't return them!")

    if missing_in_s3:
        print("\nDISCREPANCY FOUND!")
        print(f"Products in API but NOT in S3: {sorted(missing_in_s3)}")
        print("   → API returns these but they don't exist on S3!")

    if not missing_in_api and not missing_in_s3:
        print("\nNo discrepancies - API and S3 are in sync!")

    # ========================================================================
    # EXAMINE exiobase-3 (if it exists)
    # ========================================================================
    if "exiobase-3" in s3_product_ids:
        print("\nEXAMINING exiobase-3 (Found in S3)")
        print("=" * 80)

        result = obs.list_with_delimiter(store, prefix=f"{account_id}/exiobase-3/")
        objects = result.get("objects", [])

        print(f"Found {len(objects)} files/objects in exiobase-3:")
        for obj_meta in objects[:20]:  # Limit to 20
            path = obj_meta.get("path", "")
            size = obj_meta.get("size", 0)
            modified = obj_meta.get("last_modified", "N/A")

            filename = path.split("/")[-1]
            size_mb = size / 1024 / 1024
            print(f"  - {filename:<50} {size_mb:>10.2f} MB  {modified}")

        if len(objects) > 20:
            print(f"  ... and {len(objects) - 20} more files")

    await http_client.aclose()
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
