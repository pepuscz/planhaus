---
name: setup
description: Install Python dependencies for planhaus spatial tools and optionally catalog search
---

# Setup

Install the required Python dependencies.

## Steps

1. Install core dependencies (pyyaml + matplotlib):
   ```bash
   pip install -r ${CLAUDE_PLUGIN_ROOT}/scripts/requirements.txt
   ```

2. Verify installation:
   ```bash
   python3 -c "import yaml, matplotlib; print('Core dependencies OK')"
   ```

3. **Optional** — if the user wants catalog search, also install chromadb:
   ```bash
   pip install -r ${CLAUDE_PLUGIN_ROOT}/scripts/catalog/requirements.txt
   ```

## Notes

- Core deps (~20MB) are needed for all spatial tools: render, validate, position.
- Catalog deps (chromadb, ~200MB) are only needed for `/planhaus:search`.
- On Cowork VM (Ubuntu 22.04), matplotlib is pre-installed — this should be fast.
