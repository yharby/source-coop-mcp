#!/bin/bash
# Automated Release Script for source-coop-mcp
# Usage: ./scripts/release.sh [major|minor|patch]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get current version from pyproject.toml
CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')

echo -e "${GREEN}Current version: ${CURRENT_VERSION}${NC}"

# Parse version
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Determine bump type
BUMP_TYPE=${1:-patch}

case $BUMP_TYPE in
  major)
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
    ;;
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    ;;
  patch)
    PATCH=$((PATCH + 1))
    ;;
  *)
    echo -e "${RED}Invalid bump type. Use: major, minor, or patch${NC}"
    exit 1
    ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"

echo -e "${YELLOW}Bumping version: ${CURRENT_VERSION} → ${NEW_VERSION} (${BUMP_TYPE})${NC}"

# Confirm
read -p "Proceed with release v${NEW_VERSION}? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}Release cancelled${NC}"
    exit 1
fi

# Update version in pyproject.toml
echo -e "${GREEN}Updating pyproject.toml...${NC}"
sed -i.bak "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" pyproject.toml
rm pyproject.toml.bak

# Run tests
echo -e "${GREEN}Running tests...${NC}"
uv run python -u tests/test_all_mcp_tools.py

# Commit version bump
echo -e "${GREEN}Committing version bump...${NC}"
git add pyproject.toml
git commit -m "chore: bump version to ${NEW_VERSION}" || true

# Push changes
echo -e "${GREEN}Pushing to main...${NC}"
git push origin main

# Create and push tag
echo -e "${GREEN}Creating tag v${NEW_VERSION}...${NC}"
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"
git push origin "v${NEW_VERSION}"

# Create GitHub release with auto-generated notes
echo -e "${GREEN}Creating GitHub release...${NC}"
gh release create "v${NEW_VERSION}" \
  --title "v${NEW_VERSION}" \
  --generate-notes

echo -e "${GREEN}✅ Release v${NEW_VERSION} complete!${NC}"
echo -e "${YELLOW}📦 PyPI publish will start automatically${NC}"
echo -e "${YELLOW}🔗 Release: https://github.com/yharby/source-coop-mcp/releases/tag/v${NEW_VERSION}${NC}"
echo -e "${YELLOW}🔗 PyPI: https://pypi.org/project/source-coop-mcp/${NEW_VERSION}/${NC}"
