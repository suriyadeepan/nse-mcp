# Future Development Scope

Priorities: **P0 = Critical | P1 = High | P2 = Medium | P3 = Low**

## P0 — Core User Experience & MCP Foundation

- **Interactive CLI:** Persistent conversational sessions, multi-turn context, streaming, commands (`/help`, `/clear`, `/history`, `/tools`, `/exit`), tool-call visibility and execution timings.

- **Prompt Library:** Reusable prompts for historical investment calculations, stock comparisons, performance, volatility, drawdowns and intraday analysis.

- **MCP Data Discovery:**

    - `list_symbols` — Available symbols, optionally filtered by exchange/index.

    - `get_data_range` — First/last available dates, intervals and record counts per symbol.

    - `get_dataset_info` — Dataset coverage, symbols, intervals, record counts and last update.

    - `get_symbol_info` — Company metadata, exchange, sector, industry and index membership.

    - `get_latest_data` — Latest available candle and data freshness.

    - `check_data_availability` — Validate symbols, intervals and date ranges; identify partial availability and missing sessions.

    - `get_data_quality` — Missing candles, duplicates, invalid OHLCV and data gaps.

    - `get_trading_calendar` — Trading sessions, holidays and valid trading dates.


## P1 — Interface & Analytics

- **Web UI:** ChatGPT-like interface using an existing template; sidebar with recent conversations, chat threads, persistent history, streaming and saved prompts.

- **Visualizations:** Interactive OHLC candlestick, volume, VWAP and SMA/EMA/RSI/ATR overlays; stock comparison charts, returns distributions and drawdowns. Support CSV exports.

- **Expanded Analytics:**

    - `get_returns` — Absolute, percentage and log returns.

    - `get_performance_metrics` — CAGR, total returns, volatility, Sharpe ratio and maximum drawdown.

    - `get_drawdowns` — Drawdown depth, duration and recovery.

    - `get_correlation` — Correlation matrices across symbols.

    - `get_relative_strength` — Performance against NIFTY or other benchmarks.

    - `get_volatility` — Historical/rolling volatility and ATR.

    - `get_support_resistance` — Historical price levels and swing highs/lows.

    - `get_market_breadth` — Advance/decline, stocks above moving averages and participation.

    - `get_sector_performance` — Sector returns, rankings and constituent performance.

    - `get_intraday_patterns` — Hourly returns, opening gaps, volatility and volume patterns.

- **Market Screener:** Filter stocks by technical indicators, price movements, moving averages, unusual volume and volatility. Save and reuse screening criteria.


## P2 — Investment & Research

- **Advanced Analytics:**

    - `screen_stocks` — Configurable technical/fundamental screening (where data is available).

    - `find_volume_anomalies` — Unusual volume against historical averages.

    - `find_price_anomalies` — Unusual price movements and gaps.

    - `get_rolling_statistics` — Rolling returns, means and standard deviations.

    - `compare_periods` — Performance across historical periods.

    - `get_beta` — Beta against a benchmark.

    - `get_stock_rankings` — Rankings by returns, volatility and momentum.

- **Portfolio Simulator:** Virtual portfolios, historical buys/sells, SIP and lump-sum simulations, historical investment valuation (e.g. "What would ₹1 lakh invested in RELIANCE on a given date be worth today?"), portfolio returns, CAGR, drawdowns and NIFTY benchmarking.

- **Research Workspace:** Save queries, results, charts and notes; organize by stock/sector; export to Markdown/PDF; preserve original queries, parameters and data ranges for reproducibility.


## P3 — AI Capabilities

- **Conversation Memory:** Contextual follow-ups and persistent conversation history.

- **Advanced Query Handling:** Decompose complex questions, dynamically select MCP tools and coordinate multi-tool calls.

- **Answer Verification:** Independently cross-check calculations; cite symbols, date ranges, metrics and data sources; distinguish computed facts from AI-generated interpretations.


## Architectural Constraints

- Keep the MCP analytics server independent of the frontend.

- CLI and web UI must share the same client/service layer for MCP discovery and tool invocation.

- Keep conversation management, memory and visualization rendering outside the analytics server.

- All MCP tools must have typed parameters, bounded outputs, predictable errors and explicit data-availability metadata.

- Validate data availability before analytical queries; distinguish unavailable, partially available and complete datasets.
