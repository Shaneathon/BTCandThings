# Add independent four-coin Coinbase research tracker

Prepare coin.shaneathon.com with the existing Polymarket tracker's visual
language and Coinbase-specific continuous spot data for BTC/ETH/XRP/SOL USD.
Add component-isolated product/candle/depth/trade collection, durable local
history, first-observed features, data-quality/latency reporting and the separate
read-only API/dashboard. Add optional CBot tracker input without wallet sharing.

Scope is public REST data. Full tick/L2 capture, private account data, actual
fee tiers, cloud upload and historical backfill are not claimed. No orders,
credentials, DNS/TLS changes, deployment or production database changes occur.

Validation: 9 new archive/client/integration tests, existing CBot/PBot regression
suites and 3 Streamlit fixture scenarios including four independent products and
1m/5m/15m chart switches. Live API checks remain policy-blocked. Hosting and
storage configuration are prepared as templates, not activated services.
