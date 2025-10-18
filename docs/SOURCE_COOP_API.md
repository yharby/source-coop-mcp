# Source Cooperative API Reference

**Version**: v1
**Base URL**: `https://source.coop/api/v1`
**Data Proxy**: `https://data.source.coop`
**S3 Bucket**: `s3://us-west-2.opendata.source.coop` (us-west-2)

## Overview

Source Cooperative provides two parallel access methods:

1. **HTTP API** - Rich metadata, published products only
2. **S3 Direct** - Complete file access, all products (published + unpublished)

All endpoints are **public** and require **no authentication**.

## HTTP API Endpoints

### 1. List Products by Account

Get all published products for a specific account.

**Endpoint**:
```
GET /api/v1/products/{account_id}
```

**Request**:
```bash
curl -s 'https://source.coop/api/v1/products/youssef-harby'
```

**Response** (200 OK):
```json
{
  "products": [
    {
      "product_id": "egms-copernicus",
      "title": "European Ground Motion Cloud Native Data",
      "description": "This repository contains data converted from the original Copernicus European Ground Motion Service datasets...",
      "account_id": "youssef-harby",
      "visibility": "public",
      "data_mode": "open",
      "featured": 0,
      "disabled": false,
      "created_at": "2025-02-28T14:26:48.789Z",
      "updated_at": "2025-08-21T16:39:55.569Z",
      "metadata": {
        "primary_mirror": "aws-opendata-us-west-2",
        "mirrors": {
          "aws-opendata-us-west-2": {
            "storage_type": "s3",
            "is_primary": true,
            "connection_id": "aws-opendata-us-west-2",
            "config": {
              "region": "us-west-2",
              "bucket": "aws-opendata-us-west-2"
            },
            "prefix": "youssef-harby/egms-copernicus/"
          }
        },
        "tags": [],
        "roles": {
          "youssef-harby": {
            "account_id": "youssef-harby",
            "role": "admin",
            "granted_by": "youssef-harby",
            "granted_at": "2025-08-21T16:39:55.569Z"
          }
        }
      }
    }
  ]
}
```

**Response Schema**:
```typescript
interface ProductsResponse {
  products: Product[]
}

interface Product {
  product_id: string              // Unique product identifier
  title: string                   // Human-readable title
  description: string             // Markdown description
  account_id: string              // Owner account
  visibility: "public" | "private"
  data_mode: "open" | "restricted"
  featured: 0 | 1                 // 1 = curated/featured dataset
  disabled: boolean
  created_at: string              // ISO 8601 timestamp
  updated_at: string              // ISO 8601 timestamp
  metadata: ProductMetadata
}

interface ProductMetadata {
  primary_mirror: string
  mirrors: {
    [mirror_id: string]: Mirror
  }
  tags: string[]                  // Currently unused
  roles: {
    [account_id: string]: Role
  }
}

interface Mirror {
  storage_type: "s3"
  is_primary: boolean
  connection_id: string
  config: {
    region: string
    bucket: string
  }
  prefix: string                  // S3 prefix path
}

interface Role {
  account_id: string
  role: "admin" | "read" | "write"
  granted_by: string
  granted_at: string
}
```

**Response Headers**:
```
HTTP/2 200
content-type: application/json
cache-control: public, max-age=0, must-revalidate
server: Vercel
```

**Error Responses**:

```bash
# Account not found
curl -s 'https://source.coop/api/v1/products/nonexistent-account'
```

```json
{
  "products": []
}
```

Note: Returns empty array, not 404.

---

### 2. Get Product Details

Get detailed metadata for a specific product.

**Endpoint**:
```
GET /api/v1/products/{account_id}/{product_id}
```

**Request**:
```bash
curl -s 'https://source.coop/api/v1/products/harvard-lil/gov-data'
```

**Response** (200 OK):
```json
{
  "product_id": "gov-data",
  "title": "Archive of data.gov",
  "description": "This collection includes BagIt archives of every entry on data.gov, including API metadata for each dataset.",
  "account_id": "harvard-lil",
  "visibility": "public",
  "data_mode": "open",
  "featured": 1,
  "disabled": false,
  "created_at": "2024-12-13T20:32:55.681Z",
  "updated_at": "2025-08-21T16:39:55.567Z",
  "metadata": {
    "primary_mirror": "aws-opendata-us-west-2",
    "mirrors": {
      "aws-opendata-us-west-2": {
        "storage_type": "s3",
        "is_primary": true,
        "connection_id": "aws-opendata-us-west-2",
        "config": {
          "region": "us-west-2",
          "bucket": "aws-opendata-us-west-2"
        },
        "prefix": "harvard-lil/gov-data/"
      }
    },
    "tags": [],
    "roles": {
      "harvard-lil": {
        "account_id": "harvard-lil",
        "role": "admin",
        "granted_by": "harvard-lil",
        "granted_at": "2025-08-21T16:39:55.567Z"
      }
    }
  },
  "account": {
    "account_id": "harvard-lil",
    "name": "Harvard Library Innovation Lab",
    "type": "organization",
    "disabled": false,
    "identity_id": "N/A",
    "emails": [],
    "flags": ["create_organizations", "create_repositories"],
    "created_at": "2025-08-23T06:12:35.933Z",
    "updated_at": "2025-08-23T06:12:35.933Z",
    "metadata_public": {
      "bio": "The Harvard Library Innovation Lab is a team of librarians, software developers, designers, and lawyers growing knowledge and community by bringing library principles to technological frontiers.",
      "location": "United States",
      "domains": []
    },
    "metadata_private": {}
  }
}
```

**Response Schema**:
```typescript
interface ProductDetailsResponse extends Product {
  account: Account  // Additional account information
}

interface Account {
  account_id: string
  name: string
  type: "organization" | "user"
  disabled: boolean
  identity_id: string
  emails: string[]
  flags: string[]
  created_at: string
  updated_at: string
  metadata_public: {
    bio?: string
    location?: string
    domains?: string[]
  }
  metadata_private: Record<string, any>
}
```

**Error Responses**:

```bash
# Product not found (unpublished or doesn't exist)
curl -s 'https://source.coop/api/v1/products/youssef-harby/exiobase-3'
```

```json
{
  "error": "Product not found",
  "message": "Product exiobase-3 not found in account youssef-harby"
}
```

Note: HTTP 404 for unpublished products.

---

## Data Proxy (File Access)

### 3. Get File Contents

Access individual files via HTTP.

**Endpoint**:
```
GET https://data.source.coop/{account_id}/{product_id}/{file_path}
```

**Request**:
```bash
curl -s 'https://data.source.coop/youssef-harby/exiobase-3/goose-agent.yaml'
```

**Response** (200 OK):
```yaml
name: exiobase-3-global-trade-environmental-impact-analyzer
filename: exiobase-3-global-trade-environmental-impact-analyzer
author:
  contact: me@youssefharby.com
recipe:
  version: "1.0.0"
  title: EXIOBASE-3 Global Trade & Environmental Impact Analyzer
  description: An intelligent agent for exploring and analyzing global economic and environmental data from EXIOBASE-3 (1995-2022)...
```

**Response Headers**:
```
HTTP/2 200
content-type: application/octet-stream
content-length: 7391
etag: "925939d8082a406231730fde73b524b0"
last-modified: Fri, 11 Oct 2025 21:39:48 GMT
```

**Common File Patterns**:
```
# Product README (standard location)
https://data.source.coop/{account_id}/{product_id}/README.md

# Nested files
https://data.source.coop/harvard-lil/gov-data/metadata/metadata.jsonl.zip

# STAC catalogs
https://data.source.coop/{account_id}/{product_id}/catalog.json
```

**Works for ALL products** (published + unpublished):
```bash
# This works even though exiobase-3 returns 404 from API
curl -s 'https://data.source.coop/youssef-harby/exiobase-3/goose-agent.yaml'
# ✅ Returns file contents
```

---

## S3 Direct Access

### 4. List Account Directories

Discover all accounts (organizations).

**Request**:
```bash
aws s3 ls s3://us-west-2.opendata.source.coop/ \
  --no-sign-request \
  --region us-west-2
```

**Response**:
```
                           PRE addresscloud/
                           PRE clarkcga/
                           PRE cloud-native-geospatial/
                           PRE cyfi/
                           PRE earth-genome/
                           PRE esa/
                           PRE fema/
                           PRE harvard-lil/
                           PRE life/
                           PRE maxar/
                           PRE planet/
                           PRE radiantearth/
                           PRE vida/
                           PRE youssef-harby/
                           ... (92+ accounts)
```

**With curl** (list objects API):
```bash
curl -s 'https://us-west-2.opendata.source.coop/?delimiter=/&prefix='
```

Returns XML with CommonPrefixes (directories).

---

### 5. List Product Directories

Discover all products under an account.

**Request**:
```bash
aws s3 ls s3://us-west-2.opendata.source.coop/youssef-harby/ \
  --no-sign-request \
  --region us-west-2
```

**Response**:
```
                           PRE cloud-native-geocoding/
                           PRE egms-copernicus/
                           PRE exiobase-3/
                           PRE overture-maps-stac/
                           PRE weather-station-realtime-parquet/
```

**Key Insight**: Shows 5 products, but API only returns 3.

Missing from API:
- `cloud-native-geocoding` (unpublished)
- `exiobase-3` (unpublished)

---

### 6. List Files in Product

Get all files in a product directory.

**Request**:
```bash
aws s3 ls s3://us-west-2.opendata.source.coop/youssef-harby/exiobase-3/ \
  --recursive \
  --no-sign-request \
  --region us-west-2
```

**Response**:
```
2025-10-11 21:39:48       7391 youssef-harby/exiobase-3/goose-agent.yaml
```

**With delimiter** (directories only):
```bash
aws s3 ls s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/ \
  --no-sign-request \
  --region us-west-2
```

**Response**:
```
                           PRE collections/
                           PRE metadata/
2024-12-13 20:33:05       5344 README.md
```

---

### 7. Get File Metadata

Get file info without downloading.

**Request**:
```bash
aws s3api head-object \
  --bucket us-west-2.opendata.source.coop \
  --key youssef-harby/exiobase-3/goose-agent.yaml \
  --no-sign-request \
  --region us-west-2
```

**Response**:
```json
{
  "AcceptRanges": "bytes",
  "LastModified": "2025-10-11T21:39:48+00:00",
  "ContentLength": 7391,
  "ETag": "\"925939d8082a406231730fde73b524b0\"",
  "VersionId": "yv_5bfTEPYjwXN9JIBKhRJPsQm0WyoJr",
  "ContentType": "application/octet-stream",
  "ServerSideEncryption": "AES256",
  "Metadata": {}
}
```

**Response Schema**:
```typescript
interface S3HeadObjectResponse {
  AcceptRanges: string
  LastModified: string         // ISO 8601
  ContentLength: number         // Bytes
  ETag: string                  // MD5 hash
  VersionId: string
  ContentType: string
  ServerSideEncryption: string
  Metadata: Record<string, string>
}
```

---

## API vs S3 Comparison

### Published Products (Visible in Both)

```bash
# HTTP API - Returns metadata
curl -s 'https://source.coop/api/v1/products/youssef-harby' | jq '.products[].product_id'
"egms-copernicus"
"overture-maps-stac"
"weather-station-realtime-parquet"

# S3 Direct - Returns directories
aws s3 ls s3://us-west-2.opendata.source.coop/youssef-harby/ --no-sign-request
PRE egms-copernicus/
PRE overture-maps-stac/
PRE weather-station-realtime-parquet/
```

✅ Match: These 3 products appear in both.

### Unpublished Products (S3 Only)

```bash
# HTTP API - Product not found
curl -s 'https://source.coop/api/v1/products/youssef-harby/exiobase-3'
# Returns: 404 Not Found

# S3 Direct - Files accessible
aws s3 ls s3://us-west-2.opendata.source.coop/youssef-harby/exiobase-3/ --no-sign-request
2025-10-11 21:39:48       7391 youssef-harby/exiobase-3/goose-agent.yaml

# Data Proxy - File accessible
curl -s 'https://data.source.coop/youssef-harby/exiobase-3/goose-agent.yaml'
# ✅ Returns file contents
```

**Conclusion**: S3/Data Proxy work for ALL products. API only shows published.

---

## Rate Limits & Performance

### HTTP API
- **Rate Limits**: Standard Vercel limits (unknown exact values)
- **Response Time**: 200-500ms per request
- **Caching**: `cache-control: public, max-age=0, must-revalidate`
- **Server**: Vercel CDN

### S3 Direct
- **Rate Limits**: AWS S3 standard (5,500 GET/sec per prefix)
- **Response Time**:
  - List: 100-500ms
  - Head: 50-150ms
  - Get: Varies by file size
- **Concurrent Access**: Virtually unlimited

### Recommendations

**For Discovery**:
- Use S3 direct (complete, no rate limits)

**For Metadata**:
- Use HTTP API when available
- Fallback to S3 for unpublished products

**For Files**:
- Use Data Proxy for HTTP access
- Use S3 direct for programmatic access

---

## Common Patterns

### Pattern 1: Complete Product Discovery

```bash
# Step 1: List all products via S3
aws s3 ls s3://us-west-2.opendata.source.coop/youssef-harby/ --no-sign-request

# Step 2: Try to get metadata from API
for product in egms-copernicus exiobase-3; do
  curl -s "https://source.coop/api/v1/products/youssef-harby/$product" || echo "Unpublished"
done

# Step 3: Access files regardless of publication status
curl -s "https://data.source.coop/youssef-harby/exiobase-3/goose-agent.yaml"
```

### Pattern 2: Featured Products Only

```bash
# Get all products from account
curl -s 'https://source.coop/api/v1/products/harvard-lil' | \
  jq '.products[] | select(.featured == 1) | {product_id, title}'
```

### Pattern 3: File Size Calculation

```bash
# Get all file sizes in a product
aws s3 ls s3://us-west-2.opendata.source.coop/youssef-harby/exiobase-3/ \
  --recursive \
  --no-sign-request \
  --human-readable \
  --summarize
```

---

## Authentication

**None required!**

All Source Cooperative data is public:
- S3 bucket: `--no-sign-request` flag
- HTTP API: No API key needed
- Data Proxy: Public URLs

---

## Error Handling

### HTTP API Errors

```bash
# 404 - Product not found (unpublished)
curl -I 'https://source.coop/api/v1/products/youssef-harby/exiobase-3'
HTTP/2 404

# Empty array for unknown account
curl -s 'https://source.coop/api/v1/products/unknown'
{"products":[]}
```

### S3 Errors

```bash
# Access Denied (wrong region)
aws s3 ls s3://us-west-2.opendata.source.coop/ --region us-east-1
# Error: Access Denied

# Correct region
aws s3 ls s3://us-west-2.opendata.source.coop/ --region us-west-2 --no-sign-request
# ✅ Works
```

**Key**: Always use `--region us-west-2` and `--no-sign-request`.

---

## API Limitations

### What HTTP API Cannot Do

1. ❌ Discover unpublished products
2. ❌ List files in products
3. ❌ Get file metadata (size, etag, modified date)
4. ❌ Enumerate all accounts

### What S3 Direct Cannot Do

1. ❌ Get product titles/descriptions
2. ❌ Get featured flags
3. ❌ Get account bios/locations
4. ❌ Get creation/update timestamps

### Solution: Hybrid Approach

```python
# 1. Discover ALL products via S3
products_s3 = list_via_s3("youssef-harby")  # Returns 5 products

# 2. Enrich with API metadata where available
for product in products_s3:
    try:
        metadata = get_from_api("youssef-harby", product['id'])
        product.update(metadata)  # Add title, description, etc.
    except NotFound:
        product['published'] = False  # Mark as unpublished
```

---

## Testing Checklist

Validate API access with these commands:

```bash
# ✅ List products (HTTP API)
curl -s 'https://source.coop/api/v1/products/youssef-harby' | jq '.products[].product_id'

# ✅ Get product details (HTTP API)
curl -s 'https://source.coop/api/v1/products/harvard-lil/gov-data' | jq '.title'

# ✅ Get file via Data Proxy
curl -s 'https://data.source.coop/youssef-harby/exiobase-3/goose-agent.yaml' | head -5

# ✅ List accounts (S3)
aws s3 ls s3://us-west-2.opendata.source.coop/ --no-sign-request --region us-west-2 | wc -l

# ✅ List products (S3)
aws s3 ls s3://us-west-2.opendata.source.coop/youssef-harby/ --no-sign-request --region us-west-2

# ✅ Get file metadata (S3)
aws s3api head-object \
  --bucket us-west-2.opendata.source.coop \
  --key youssef-harby/exiobase-3/goose-agent.yaml \
  --no-sign-request \
  --region us-west-2 \
  | jq '.ContentLength'
```

All should return valid responses.

---

## Summary

### HTTP API
- **Base**: `https://source.coop/api/v1`
- **Purpose**: Rich metadata
- **Coverage**: Published products only
- **Auth**: None required
- **Format**: JSON

### Data Proxy
- **Base**: `https://data.source.coop`
- **Purpose**: File HTTP access
- **Coverage**: ALL products
- **Auth**: None required
- **Format**: Raw files

### S3 Direct
- **Bucket**: `s3://us-west-2.opendata.source.coop`
- **Purpose**: Complete discovery + files
- **Coverage**: ALL products
- **Auth**: `--no-sign-request`
- **Region**: `us-west-2` (required)

**Best Practice**: Use all three in combination for complete access.
