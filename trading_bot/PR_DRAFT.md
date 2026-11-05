# Add independent TBot paper engine and dashboard

Prepare tbot.shaneathon.com as a separate bot terminal. Add a persistent paper
portfolio for ten market streams, asset/model/stage-specific history gates,
modeled edge after costs, fresh mapped depth-aware quotes, worst-case risk
reservation, settlement-only exits, kill switch, restart idempotence and
transactional decision logging. Add an authenticated read-only status API and
separate Streamlit dashboard with explicit setup/outage states.

Prepare contract-mapped SDK limit-order payloads and an explicit preview
interface; live submit remains unavailable. No paper call path can reach a real
order endpoint. Add example paper configuration, independent deployment/hostname
templates and CI. Production tracker, collector services and databases are not
modified by this increment.

Validation: 16 paper/API/runner tests and 3 Streamlit fixture checks pass. The
runner test reads a synthetic collector-format DB without changing source bytes
and produces ten paper positions. This is fixture validation, not actual model
profitability. No live account, DNS, certificate, deployment or order submission
was performed. Real data/quote mapping, fee rules, server permissions and future
live-order reconciliation remain deployment/development requirements.
