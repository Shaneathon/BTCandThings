# Hourly PBot paper review

User authorized automatic paper-only adjustments and requested checks every 30 or 60 minutes. This release installs a deterministic hourly loss guard, not an unattended ChatGPT session or a self-training prediction model. No exchange/account credentials or network access are needed by the review service.

Each active wallet is scored independently using official-settled observed-price paper positions opened within the latest 24 hours and the current $0.50–$5 entry-policy cohort. Missing/legacy entry-policy tags are excluded, preventing old $10 results from triggering a new-policy action. At least ten eligible closed trades with aggregate net P/L at or below -$20 trigger a six-hour entry pause. Net P/L includes the modeled execution fees; actual live fees/fills remain uncertain. The $20 figure is a review trigger, not a guaranteed loss cap: losses can accrue between reviews or on existing positions.

The engine checks persisted controls when proposing and again under the SQLite write lock before filling. Pending proposals are rejected without a fill/fee when paused. Cash, risk settings, predictions, existing holdings and settlements are not edited by the reviewer. Wallet independence is retained. Daily-loss/drawdown/manual stop protections continue to apply and are never cleared by automatic expiry.

Pause expiry permits new entries under the existing rules. Subsequent review cohorts begin after that expiry, requiring ten new completed trades; the same historic losses cannot perpetually re-trigger a pause. This is a conservative cooldown and does not establish that a strategy has improved. No model/threshold promotion, parameter search, higher limits, guaranteed profitability, or live trading is enabled.

Review reports and each pause's reason/times persist in the existing paper ledger (`automatic_reviews`, `automatic_entry_pauses`). The PBot dashboard shows the latest report, Central pause expiry, and overdue review warning; private health also flags missing/overdue hourly runs. No email/SMS/push channel is configured. `pbot-hourly-review.timer` runs hourly, persistent across restarts. Stale/wrong/live-mode identity fails the job without taking actions; existing engine freshness and risk checks remain active.

Deployment: `bash deploy/install-pbot-hourly-review.sh --apply`, after staging the research branch. Tests run before service changes. Only PBot engine/status/dashboard and health unit code paths change. Initial review runs immediately, then timer runs hourly. Original collectors, Coinbase, input exporter, all ledger balances/history and real-trading interlocks are preserved. Installer rolls back units on failure, never restores an old financial database over subsequent trades. Existing controls/review records are retained.

This feature targets PBot only. CBot baseline/fee-filter experiments and their independent product wallets are unchanged.
