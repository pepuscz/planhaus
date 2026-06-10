---
name: setup
description: Install catalog search dependencies (core deps are auto-installed)
disable-model-invocation: true
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
   pip install -r "${CLAUDE_PLUGIN_ROOT}/scripts/requirements.txt"
   ```
   On PEP 668 "externally managed environment" errors, fall back to
   `pip install --user`, then `pip install --break-system-packages`, or use a venv
   (`python3 -m venv .venv && .venv/bin/pip install -r ...`).

3. **Catalog search** — install chromadb for `/planhaus:search`:
   ```bash
   pip install -r "${CLAUDE_PLUGIN_ROOT}/scripts/catalog/requirements.txt"
   ```
   Same PEP 668 fallbacks apply.

## Notes

- Core deps are auto-installed by the SessionStart hook — this skill is mainly for catalog deps.
- Catalog deps (chromadb, ~200MB) are only needed for catalog search.
- On Cowork VM (Ubuntu 22.04), matplotlib is pre-installed.
