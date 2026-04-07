---
name: Sentinel
description: Advanced API protection and logic auditing.
---
# Sentinel: Safety and Security Protocol

This skill ensures that all trading and API code remains secure.

## Core Instructions

1. **Secret Masking**: If using `view_file` on a `.env` or `config.py`, never print secrets directly.
2. **Logic Auditing**: Before `pushing` strategy changes, perform a "Reverse Logic Check" (what if the price goes the other way?).
3. **Environment Isolation**: Always distinguish between `BYBIT_DEMO=True` and `Production` mode.
4. **Leak Prevention**: Search for hardcoded keys in `scripts/` or `tests/` before committing.

### Example
Searching for any `api_key` or `secret` string before pushing the new V6.1 update to GitHub.
