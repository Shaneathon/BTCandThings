-- PROPOSED ONLY: do not run until Supabase migration review.
-- Independent multi-asset tables; existing btc_markets/btc_predictions untouched.
-- RLS is enabled with NO public policies by default. Collector requires
-- an appropriately scoped backend credential, never exposed in Streamlit UI.

CREATE TABLE IF NOT EXISTS public.asset_market_windows (
  market_slug TEXT PRIMARY KEY,
  asset TEXT NOT NULL CHECK (asset IN ('BTC','ETH','XRP','SOL','GOLD','SILVER')),
  duration_seconds SMALLINT NOT NULL CHECK (duration_seconds IN (300,900)),
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  contract_slug TEXT,
  market_type TEXT,
  official_price_to_beat NUMERIC,
  reference_source TEXT,
  settlement_status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (settlement_status IN ('PENDING','VERIFIED','UNAVAILABLE')),
  official_winner TEXT CHECK (official_winner IN ('UP','DOWN')),
  settlement_evidence TEXT,
  settled_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (window_end = window_start + duration_seconds * interval '1 second'),
  CHECK (official_price_to_beat IS NULL OR official_price_to_beat > 0),
  CHECK (settlement_status <> 'VERIFIED' OR (official_winner IS NOT NULL AND settlement_evidence IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS asset_windows_lookup
  ON public.asset_market_windows (asset, duration_seconds, window_start DESC);
CREATE INDEX IF NOT EXISTS asset_windows_pending
  ON public.asset_market_windows (window_end) WHERE settlement_status = 'PENDING';

CREATE TABLE IF NOT EXISTS public.asset_proxy_candles (
  asset TEXT NOT NULL CHECK (asset IN ('BTC','ETH','XRP','SOL','GOLD','SILVER')),
  source_name TEXT NOT NULL,
  source_symbol TEXT NOT NULL,
  interval_seconds SMALLINT NOT NULL CHECK (interval_seconds IN (60,300)),
  candle_open TIMESTAMPTZ NOT NULL,
  open_price NUMERIC NOT NULL CHECK (open_price > 0),
  high_price NUMERIC NOT NULL CHECK (high_price > 0),
  low_price NUMERIC NOT NULL CHECK (low_price > 0),
  close_price NUMERIC NOT NULL CHECK (close_price > 0),
  volume NUMERIC,
  completed BOOLEAN NOT NULL DEFAULT TRUE,
  is_official_settlement_feed BOOLEAN NOT NULL DEFAULT FALSE,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (asset, source_name, interval_seconds, candle_open),
  CHECK (high_price >= greatest(open_price, close_price, low_price)),
  CHECK (low_price <= least(open_price, close_price, high_price))
);

CREATE TABLE IF NOT EXISTS public.asset_market_predictions (
  market_slug TEXT NOT NULL REFERENCES public.asset_market_windows(market_slug),
  recorded_at TIMESTAMPTZ NOT NULL,
  model_version TEXT NOT NULL,
  model_role TEXT NOT NULL CHECK (model_role IN ('CHAMPION','CHALLENGER','RESEARCH')),
  predicted_up_probability DOUBLE PRECISION
    CHECK (predicted_up_probability BETWEEN 0 AND 1),
  lean_direction TEXT CHECK (lean_direction IN ('UP','DOWN','NEUTRAL')),
  feature_snapshot JSONB,
  prediction_horizon_seconds SMALLINT CHECK (prediction_horizon_seconds IN (60,180,300,900)),
  source_timestamp TIMESTAMPTZ,
  PRIMARY KEY (market_slug, recorded_at, model_version)
);

CREATE INDEX IF NOT EXISTS asset_predictions_model_time
  ON public.asset_market_predictions (model_version, recorded_at DESC);

CREATE TABLE IF NOT EXISTS public.asset_market_quotes (
  market_slug TEXT NOT NULL REFERENCES public.asset_market_windows(market_slug),
  captured_at TIMESTAMPTZ NOT NULL,
  contract_slug TEXT NOT NULL,
  up_bid NUMERIC CHECK (up_bid BETWEEN 0 AND 1),
  up_ask NUMERIC CHECK (up_ask BETWEEN 0 AND 1),
  down_bid NUMERIC CHECK (down_bid BETWEEN 0 AND 1),
  down_ask NUMERIC CHECK (down_ask BETWEEN 0 AND 1),
  source_name TEXT NOT NULL,
  PRIMARY KEY (market_slug, captured_at, contract_slug)
);

CREATE TABLE IF NOT EXISTS public.asset_paper_trades (
  paper_trade_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_slug TEXT NOT NULL REFERENCES public.asset_market_windows(market_slug),
  model_version TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('UP','DOWN')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  entry_at TIMESTAMPTZ,
  exit_at TIMESTAMPTZ,
  entry_price NUMERIC CHECK (entry_price BETWEEN 0 AND 1),
  exit_price NUMERIC CHECK (exit_price BETWEEN 0 AND 1),
  quantity NUMERIC CHECK (quantity > 0),
  estimated_fees NUMERIC CHECK (estimated_fees >= 0),
  estimated_slippage NUMERIC CHECK (estimated_slippage >= 0),
  realized_pnl NUMERIC,
  state TEXT NOT NULL DEFAULT 'PROPOSED'
    CHECK (state IN ('PROPOSED','SIMULATED_OPEN','SIMULATED_CLOSED','SKIPPED')),
  simulated_only BOOLEAN NOT NULL DEFAULT TRUE CHECK (simulated_only),
  notes TEXT
);

-- Security: no SELECT/INSERT/UPDATE/DELETE policies are created here.
-- Review dedicated server roles and explicit read-only dashboard policies
-- before enabling ingestion or exposing data to a public Streamlit app.
ALTER TABLE public.asset_market_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.asset_proxy_candles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.asset_market_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.asset_market_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.asset_paper_trades ENABLE ROW LEVEL SECURITY;
