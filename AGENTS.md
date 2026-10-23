# Project rules

## Purpose and safety
- Educational research foundation for Indian NSE/BSE cash-equity swing trading; PAPER TRADING ONLY.
- The only executable broker is the local `PaperBroker`. Never add live submission, broker connections, credential collection, or real orders. Any future live adapter must be absent or explicitly blocked.
- A backtest is not proof of profitability. The starter strategy is an unvalidated research hypothesis, not financial advice.
- Do not claim synthetic data is market data. Demos must run offline and require no credentials.

## Architecture
- Python 3.11+, `src/nse_swing_agent` package. Keep data, indicators/strategy, risk, backtesting, and paper execution separate.
- Use `Decimal` for prices and money and timezone-aware datetimes. Validate inputs at domain boundaries.
- Strategy decisions only use completed bars. Signals after session t close execute no earlier than a later symbol session. Never use future data or shuffled histories.
- Historical inputs are local and validated; preserve source files and cache imports with provenance. The TejHQ keyless daily NSE OHLCV adapter is an explicit research-only data exception; it must save original responses unchanged, normalize through canonical validation, and record provenance. Do not silently repair missing or malformed observations. TejHQ `/v1/ohlcv` is raw/unadjusted and must not be mixed with adjusted series. Preserve raw corporate-action data and state adjustment limitations.
- Backtest execution is a local simulation only. The explicitly invoked TejHQ adapter may retrieve historical daily bars over HTTPS; no broker connectivity or live broker adapter is permitted. Rates and slippage are explicit configuration; never imply stop prices are guaranteed exits.
- Adjusted-close-only series cannot be used as OHLC execution data. Never mix adjusted signals with raw execution prices without an explicit tested conversion and position/cash corporate-action model. Cost-inclusive evaluation requires a sourced, date-effective, verified, nonzero cost profile; defaults remain zero/unverified.

## Engineering standards
- Type public interfaces, use small focused functions, avoid hidden I/O and swallowed exceptions, and keep configuration explicit.
- Add or update pytest coverage for behavior and safety constraints. Keep the demo deterministic and network-free; provider tests must mock HTTP and the default test suite must not need internet access.
- Run `python -m pytest` and `ruff check .` when available; report commands and actual outcomes. Do not fabricate results.
- Keep changes within approved milestones; only the explicit TejHQ historical-data adapter is allowed for remote market-data retrieval. No bulk-by-default downloader, LLM agent, live broker, dashboard, or scheduler.
