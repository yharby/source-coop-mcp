"""Quick test of obstore with Source Cooperative"""

import asyncio
import obstore as obs
from obstore.store import S3Store

BUCKET = "us-west-2.opendata.source.coop"


async def test_obstore():
    print("Testing obstore with Source Cooperative...")

    # Create S3 store (public, no credentials)
    store = S3Store(BUCKET, region="us-west-2", skip_signature=True)

    # Test 1: List accounts (first 100 objects to find accounts)
    print("\n=== Test 1: Listing accounts ===")
    stream = obs.list(store, chunk_size=100)

    accounts = set()
    async for batch in stream:
        for obj_meta in batch:
            # obj_meta is a dict with 'path' key
            location = obj_meta.get("path", "")
            if "/" in location:
                account = location.split("/")[0]
                accounts.add(account)
        break  # Just first batch for testing

    accounts_list = sorted(list(accounts))
    print(f"Found {len(accounts_list)} accounts")
    print(f"First 10: {accounts_list[:10]}")

    # Test 2: List files in a specific product
    print("\n=== Test 2: Listing files in youssef-harby/exiobase-3 ===")
    prefix = "youssef-harby/exiobase-3/"
    result = obs.list_with_delimiter(store, prefix=prefix)

    # result is a dict with 'objects' and 'common_prefixes'
    objects = result.get("objects", [])
    print(f"Found {len(objects)} objects")

    files = []
    for obj_meta in objects[:10]:  # Limit to 10 files
        location = obj_meta.get("path", "")
        if not location.endswith("/"):
            files.append(
                {
                    "location": location,
                    "size": obj_meta.get("size", 0),
                    "last_modified": str(obj_meta.get("last_modified", "N/A")),
                }
            )

    print("Files:")
    for f in files:
        print(f"  - {f['location']} ({f['size']} bytes)")

    # Test 3: Get file metadata
    print("\n=== Test 3: Get file metadata ===")
    test_key = "youssef-harby/exiobase-3/goose-agent.yaml"
    try:
        obj_meta = await obs.head_async(store, test_key)
        # obj_meta is a dict
        print(f"File: {test_key}")
        print(f"Size: {obj_meta.get('size')} bytes")
        print(f"Last Modified: {obj_meta.get('last_modified')}")
        print(f"ETag: {obj_meta.get('e_tag', 'N/A')}")
    except Exception as e:
        print(f"Error: {e}")

    print("\nobstore tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_obstore())
