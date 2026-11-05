# Give crypto workspaces the BTC-style layout with asset-specific markets

The non-BTC tracker pages had a simpler layout and no final-target estimate.
Use the BTC 15m presentation structure for shared workspaces: countdown/chart,
lean and position cards, preflight, final-target research forecast and matching
tabs. Bind all calculations and targets to the selected asset and duration.

The countdown stays on its selected window until refresh, and target validation
rejects foreign assets, wrong windows and naive timestamps. Final-target
percentages are uncalibrated, asset-local spot research estimates, paused for
missing targets or stale/gapped candles. No BTC strategy/history is copied into
other assets. Existing BTC 15m app.py and production services are unchanged.

Validation: 29 unit tests; twelve Streamlit fixture workspace render/switch cases
and one wrong-asset target rejection case. Live API and browser visual testing
remain outstanding. Permanent cloud storage and database deployment are deferred. Website publication is authorized.

Prepared PR description only; not published to GitHub.
