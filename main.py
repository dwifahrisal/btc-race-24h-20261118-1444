#!/usr/bin/env python3
"""btc-race-24h entry: regime-filtered SMA crossover, half-stake.

Strategy (validated on the frozen dev window with the kit's own SDK):
  - Signal: SMA(50) crosses above SMA(200) on the bar's close -> long.
            SMA(50) crosses below SMA(200) -> flat (in cash).
  - Position sizing: half of available cash per entry (frac = 0.5), so the
    bot keeps dry powder and its drawdown stays small.
  - Warm-up: none on this competition (hello has no warmup_bars), but the
    code reads every batch and seeds the SMAs from the first closes, so it
    works with or without a warm-up.
  - Orders are sent on the close of bar k and fill at bar k+1's open under
    the replay's fee (4 bps), slippage (2 bps) and constant-product impact
    against that open's pool depth, all decided by the harness.

The bot speaks agent-fun/bars-replay/v1: one JSON line per batch on stdin,
exactly one reply per batch on stdout. Stdlib only, deterministic (no clock,
no random, no network), so two runs on the same bars produce identical orders.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

FAST = 50
SLOW = 200
MAX_SLIPPAGE_BPS = 100


class Sma:
    """Simple moving average over a fixed window, seeded with the first full window."""

    __slots__ = ("span", "vals", "total", "ready")

    def __init__(self, span):
        self.span = span
        self.vals = []
        self.total = 0
        self.ready = None

    def push(self, x):
        self.vals.append(x)
        self.total += x
        if len(self.vals) > self.span:
            self.total -= self.vals.pop(0)
        if self.ready is None and len(self.vals) == self.span:
            self.ready = self.total / self.span

    @property
    def value(self):
        if self.ready is None:
            return None
        if len(self.vals) < self.span:
            return self.ready
        return self.total / self.span


def on_batch(state, batch):
    """Decide this batch's orders: buy on a golden cross, sell on a death cross."""
    symbol = None
    close = None
    for bar in batch["bars"]:
        symbol = bar["symbol"]
        close = int(bar["c"])
    if symbol is None:
        return []

    # The bot only trades one symbol; the universe is a single asset (CBBTC).
    fast = state._fast
    slow = state._slow
    prev_fast = fast.value
    prev_slow = slow.value

    fast.push(close)
    slow.push(close)

    now_fast = fast.value
    now_slow = slow.value

    if state.warming_up:
        return []

    held = state.positions.get(symbol)
    crossed_up = prev_fast is not None and prev_slow is not None and now_fast is not None and now_slow is not None and now_fast > now_slow and prev_fast <= prev_slow
    crossed_down = prev_fast is not None and prev_slow is not None and now_fast is not None and now_slow is not None and now_fast < now_slow and prev_fast >= prev_slow

    if held is not None:
        if crossed_down:
            return [{
                "side": "sell",
                "symbol": symbol,
                "qty": held.qty,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        return []

    if crossed_up:
        # Half of equity, capped by the weight cap and the cash on hand.
        room = state.weight_room(symbol)
        spend = min(state.equity // 2, room, state.cash)
        if spend <= 0:
            return []
        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
        if spend < min_notional:
            return []
        return [{
            "side": "buy",
            "symbol": symbol,
            "notional_quote_units": spend,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]
    return []


def main():
    makefun_bars._fast = None  # unused; keeps module import side-effect free
    state = None

    def on_hello(s):
        # Attach the two SMAs to the state object once hello arrives.
        s._fast = Sma(FAST)
        s._slow = Sma(SLOW)

    makefun_bars.run(on_batch, on_hello=on_hello)


if __name__ == "__main__":
    main()