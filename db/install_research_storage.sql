-- Additive collector storage; no changes to existing btc_* tables.
BEGIN;

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

ALTER TABLE public.asset_market_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.asset_proxy_candles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.asset_market_predictions ENABLE ROW LEVEL SECURITY;

-- Backend access only; no anonymous/public RLS policies are added.
GRANT SELECT, INSERT, UPDATE ON public.asset_market_windows,
  public.asset_proxy_candles, public.asset_market_predictions TO service_role;

COMMIT;
NOTIFY pgrst, 'reload schema';

SELECT tablename, rowsecurity AS rls_enabled
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('btc_markets','asset_market_windows',
                   'asset_proxy_candles','asset_market_predictions')
ORDER BY tablename;
