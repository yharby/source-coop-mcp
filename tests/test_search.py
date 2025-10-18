"""Test search_products functionality"""

import asyncio
import httpx

API_BASE = "https://source.coop/api/v1"


async def list_products(account_id=None):
    """List products from HTTP API"""
    http_client = httpx.AsyncClient(timeout=30.0)

    try:
        if account_id:
            url = f"{API_BASE}/products/{account_id}"
        else:
            # Get from a few sample accounts
            all_products = []
            sample_accounts = ["harvard-lil", "youssef-harby", "fused"]

            for acc in sample_accounts:
                try:
                    resp = await http_client.get(f"{API_BASE}/products/{acc}")
                    resp.raise_for_status()
                    data = resp.json()
                    all_products.extend(data.get("products", []))
                except Exception as e:
                    print(f"Warning: Could not fetch products for {acc}: {e}")

            return all_products

        resp = await http_client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("products", [])

    finally:
        await http_client.aclose()


async def search_products(query, account_id=None, search_in=None):
    """Search for products (mimics the MCP tool)"""
    # Set default search fields if not provided
    if search_in is None:
        search_in = ["title", "description", "product_id"]

    print(f"Searching for: '{query}' in {search_in}")
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
    print(f"Found {len(results)} matching products")

    return results


async def main():
    print("=" * 80)
    print("TEST: search_products() functionality")
    print("=" * 80)

    # Test 1: Search for "climate" across all fields
    print("\n### Test 1: Search for 'climate'")
    results1 = await search_products("climate")
    if results1:
        print(f"✓ Found {len(results1)} results")
        print(f"✓ Top result: {results1[0]['title']}")
        print(f"  - Score: {results1[0]['search_score']}")
        print(f"  - Matched: {results1[0]['matched_fields']}")
    else:
        print("✗ No results found")

    # Test 2: Search for "overture" (should find product_id match)
    print("\n### Test 2: Search for 'overture'")
    results2 = await search_products("overture")
    if results2:
        print(f"✓ Found {len(results2)} results")
        print(f"✓ Top result: {results2[0]['product_id']}")
        print(f"  - Score: {results2[0]['search_score']}")
        print(f"  - Matched: {results2[0]['matched_fields']}")
    else:
        print("✗ No results found")

    # Test 3: Search in specific account
    print("\n### Test 3: Search for 'data' in youssef-harby account")
    results3 = await search_products("data", account_id="youssef-harby")
    print(f"✓ Found {len(results3)} results in youssef-harby account")
    for result in results3:
        print(f"  - {result['product_id']} (score: {result['search_score']})")

    # Test 4: Search only in titles
    print("\n### Test 4: Search for 'maps' only in titles")
    results4 = await search_products("maps", search_in=["title"])
    if results4:
        print(f"✓ Found {len(results4)} results")
        for result in results4[:3]:
            print(f"  - {result['title']} (score: {result['search_score']})")
    else:
        print("  No results (expected if no products have 'maps' in title)")

    print("\n" + "=" * 80)
    print("SEARCH TESTS COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
