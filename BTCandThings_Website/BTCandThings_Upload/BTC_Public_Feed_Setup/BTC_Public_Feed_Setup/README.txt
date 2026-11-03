BTC AND THINGS — PUBLIC READ-ONLY PREDICTION FEED

This adds a separate GitHub Actions exporter. It does NOT modify your working Streamlit app, Supabase database, or DigitalOcean collector.

1. In GitHub repo Shaneathon/BTCandThings, upload these files at the REPOSITORY ROOT, preserving folders:
   .github/workflows/publish-btc-feed.yml
   scripts/export_feed.py
   (The public folder is created by the workflow.)
2. GitHub repo > Settings > Secrets and variables > Actions > New repository secret:
   SUPABASE_URL = same URL already configured in Streamlit secrets
   SUPABASE_KEY = same server-side key already configured in Streamlit secrets
   NEVER commit the values into code or chat.
3. Repo > Settings > Actions > General > Workflow permissions > Read and write permissions > Save.
4. Repo > Actions > Publish BTC prediction feed > Run workflow. Wait for success.
5. Confirm the public feed exists:
   https://raw.githubusercontent.com/Shaneathon/BTCandThings/HEAD/public/btc_predictions.json

The workflow runs approximately every 5 minutes (GitHub schedule may be delayed). It exports only a whitelist of prediction and outcome fields for the past 24 hours; it never exports credentials, user accounts, quotes, or private data. GitHub repository must be PUBLIC for an anonymous read-only URL. Publishing predictions makes them visible to everyone; do not deploy if you prefer private data.

The data is retrospective, not a real-time streaming endpoint. The GitHub file is updated on each successful scheduled run. Only actual recorded predictions are published; there is no backfilling. GitHub Actions must be enabled. If Supabase row-level permissions block the export, the workflow will fail without publishing anything.

For a fair 3-hour MyDonkeyBrain comparison, collect contemporaneous MyDonkeyBrain signal snapshots as well, before each market resolves. This feed alone does not provide the other site's prediction history.
