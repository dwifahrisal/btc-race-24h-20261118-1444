# btc-race-24h-20261118 — session log

## 2026-11-18 14:44-16:09 UTC

### Goal
Write an agent that trades the CBBTC / USDC pool for 24h and ranks on net PnL,
paying the top 10. The entry has to clear a dev-window gate (PnL > 0) before it
can race.

### Approach
1. Read the kit: rules, the agent-fun/bars-replay/v1 contract, the six house
   baselines, and the harness parameters in competition.yaml (fee 4 bps/side,
   slippage 2 bps/side, max_weight_bps 10000, max_open_positions 1,
   max_orders_per_bar 4, max_drawdown 25%).
2. Loaded the dev window (1440 1-minute bars) and computed the cost model:
   round trip ~26 bps, mean absolute one-minute move ~4 bps. Conclusion:
   a rule that trades often loses to costs, so stay in cash unless the slow
   trend is up.
3. Built an exact local simulator (sim.py) reproducing the fill model from
   contracts/bars-protocol.ts and sim/bars/engine.ts.
4. Tested the six house baselines plus 17 strategy definitions from the
   Sami001-OG/Crypto-Backtester-and-Strategy-Optimizer registry (pure-Python
   Pine ports) on the dev window. golden_cross (SMA 50/200) was the only
   strategy with a positive dev PnL: +10.45 USDC at full stake, 4 trades.
5. Hardened it against noise with a block-bootstrap stress test (400 resampled
   windows built from the dev window's own minute returns, 30-minute blocks):
   buy-and-hold loses -135 USDC on average, the strategy loses less on 79% of
   windows. Measured fixed stakes 0.4/0.5/0.6 and trend-strength scaling;
   half-stake won on the dev PnL / drawdown trade-off. Hard stops and trailing
   stops were both measured and both lose, because every extra fill pays 26 bps
   again.
6. Rewrote the bot against the real SDK surface (run(on_batch, on_hello,
   on_done) with BarsState: state.cash, state.positions, state.hello["caps"]).
7. Verified with the kit's own grader:
   makefun grade-local --kit . --bot . --driver docker --worktree
   -> net PnL 5.074418 USDC, guardrails met, L1 regrade reproduced byte for
      byte across two executions.
