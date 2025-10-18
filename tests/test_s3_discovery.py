"""Direct test of S3-based product discovery"""

import asyncio
import obstore as obs
from obstore.store import S3Store

BUCKET = "us-west-2.opendata.source.coop"


async def list_products_from_s3(account_id: str, include_file_count: bool = False):
    """List ALL products for an account by scanning S3 directly"""
    store = S3Store(BUCKET, region="us-west-2", skip_signature=True)

    print(f"Listing products for {account_id} from S3...")

    # List all directories under account_id/
    result = obs.list_with_delimiter(store, prefix=f"{account_id}/")

    # Extract common prefixes (product directories)
    common_prefixes = result.get("common_prefixes", [])

    products = []
    for prefix in common_prefixes:
        # prefix looks like: 'youssef-harby/product-name/'
        product_id = prefix.rstrip("/").split("/")[-1]

        product_info = {
            "product_id": product_id,
            "account_id": account_id,
            "source": "s3",
            "s3_prefix": f"s3://{BUCKET}/{prefix}",
        }

        # Optionally count files
        if include_file_count:
            file_result = obs.list_with_delimiter(store, prefix=prefix)
            file_count = len(
                [
                    obj
                    for obj in file_result.get("objects", [])
                    if not obj.get("path", "").endswith("/")
                ]
            )
            product_info["file_count"] = file_count

        products.append(product_info)

    return sorted(products, key=lambda x: x["product_id"])


async def main():
    account_id = "youssef-harby"

    print("=" * 80)
    print("S3-BASED PRODUCT DISCOVERY TEST")
    print("=" * 80)

    products = await list_products_from_s3(account_id, include_file_count=True)

    print(f"\nFound {len(products)} products in S3:\n")
    for product in products:
        file_info = f"({product.get('file_count', '?')} files)" if "file_count" in product else ""
        print(f"  {product['product_id']:<40} {file_info}")
        print(f"     {product['s3_prefix']}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
