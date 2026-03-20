---
name: setup
description: Install catalog search dependencies (core deps are auto-installed)
---

# Setup

Install optional dependencies. Core deps (pyyaml + matplotlib) are auto-installed on session start.

## Steps

1. Verify core dependencies are present:
   ```bash
   python3 -c "import yaml, matplotlib; print('Core dependencies OK')"
   ```

2. If core deps are missing (hook failed), install manually:
   ```bash
   pip install -r ${CLAUDE_PLUGIN_ROOT}/scripts/requirements.txt
   ```

3. **Catalog search** — install chromadb for `/planhaus:search`:
   ```bash
   pip install -r ${CLAUDE_PLUGIN_ROOT}/scripts/catalog/requirements.txt
   ```

## Notes

- Core deps are auto-installed by the SessionStart hook — this skill is mainly for catalog deps.
- Catalog deps (chromadb, ~200MB) are only needed for `/planhaus:search`.
- On Cowork VM (Ubuntu 22.04), matplotlib is pre-installed.
