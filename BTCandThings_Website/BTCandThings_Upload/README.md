# Shane's BTC Tracker — Website Starter

This folder is ready to upload to a GitHub repository and deploy on Streamlit Community Cloud.

## No-Terminal deployment
1. Sign in to https://github.com and create a **private** repository named `shanes-btc-tracker` (a private repo may be supported depending on your Streamlit Community Cloud account settings; if not, use a public repo after reviewing the code).
2. In that repo, choose **Add file → Upload files** and upload `app.py`, `requirements.txt`, and the `.streamlit/config.toml` file, keeping `.streamlit` as a folder. GitHub's web uploader may not preserve hidden folders; you can omit config.toml entirely and the app will still work.
3. Visit https://share.streamlit.io/ and sign in with GitHub.
4. Choose **Create app / Deploy an app**, select your repository, main branch, and `app.py` as the main file. Click Deploy.
5. Once deployment completes, open the provided website URL.

## Important limitations
- The app currently saves accuracy snapshots to a local SQLite file. Streamlit Community Cloud storage is **ephemeral**: history can disappear on restart/redeploy. The website package does **not** include any previous Mac history database.
- Auto-refresh happens only while the website is open. It is NOT a 24/7 background collector.
- Free hosting may sleep when unused and external APIs may be rate-limited or unavailable.
- The Chainlink reference-price problem is not fully resolved; any Kraken fallback is a research-only estimate, not a verified official price to beat.
- Probabilities and lean/swing signals are unvalidated and not betting recommendations.

For reliable long-term historical tracking, add a hosted database and independent scheduled collector in a subsequent version.


## Hybrid forecasts update
Primary forecast display: five 3-minute windows. Broader comparison: three 5-minute windows. Existing 5-minute historical signal records remain unchanged. No paper-trading execution is included in this update.
