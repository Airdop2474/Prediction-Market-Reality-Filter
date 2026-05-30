# Codex Change Log

## 2026-05-28 - Trade journal NO orders and file-write protection

- Modified files:
  - `app/services/trade_journal_service.py`
  - `app/utils/file_store.py`
  - `app/memory/agent_memory.py`
  - `app/memory/market_memory.py`
  - `app/services/analysis_audit_service.py`
  - `app/api/routes/scanner.py`
  - `tests/test_trade_journal_service.py`
  - `.editorconfig`
- Reason:
  - Fix NO-side trade PnL calculation.
  - Remove scanner dead code that could confuse future agents.
  - Add lightweight in-process file locks and atomic JSON writes for local JSON persistence.
  - Add a minimal test directory and regression tests.
  - Declare UTF-8 as the project editor charset going forward.
- Key behavior:
  - `entry_price` and `exit_price` remain YES prices.
  - YES trades value shares at `yes_price`.
  - NO trades value shares at `1 - yes_price`.
  - New trade records include `position_price`; closed trades include `exit_value_price`.
- Verification:
  - `python -m unittest discover -s tests`
  - `python -m compileall app tests`
- Notes for ClaudeCode:
  - The project root is treated as `E:\Github\Prediction Market Reality Filter`; `trade_journal.json` remains outside `backend`.
  - Existing runtime files and `.env` were not moved or cleaned.
  - Existing `.pyc` files were left untouched.
