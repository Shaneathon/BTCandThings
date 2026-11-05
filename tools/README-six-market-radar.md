# Six-asset Polymarket US radar

The dashboard now displays **BTC, ETH, XRP, SOL, Gold and Silver** in a
read-only, six-market radar above the existing BTC-only detailed tracker.

For each 15-minute UTC window, it constructs the *documented US event-page
route* and attempts to verify the event and its unique contract through the
existing Polymarket US discovery helper. An official price-to-beat is shown
**only** if a full contract record contains typed asset, market type, and
exact window-start/end metadata. Missing or mismatched metadata shows
`PENDING`, not an invented target.

BTC predictions, charts, calibration, and settlement logic are **unchanged**.
This change does **not** deploy ETH/XRP/SOL/Gold/Silver background collectors
or invent predictions from unrelated Kraken spot feeds. Those will require
verified source/settlement mappings and DigitalOcean deployment access.

## Offline validation
```bash
python3 -m unittest discover -s tools -p 'test_market_board.py' -v
```

## Sources of route patterns
Polymarket US public event pages:
`/event/eth-updown-15m-2026-11-04-1700z`,
`/event/sol-updown-15m-2026-11-04-1700z`,
`/event/xrp-updown-15m-2026-11-04-1700z`,
`/event/gold-updown-15m-2026-11-04-2015z`,
`/event/silver-updown-15m-2026-11-04-2015z`,
and existing BTC event routes.

The app remains a research interface; no orders are placed.
