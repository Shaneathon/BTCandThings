-- PREPARATION ONLY. Review in staging after proposed_multi_asset_schema.sql.
-- No user/token creation, no changes to btc_* tables, no anonymous policies.
-- Dedicated Supabase Auth accounts must carry an ADMIN-controlled app_metadata
-- claim btcandthings_role = collector or dashboard. Never use user_metadata.
-- Authentication/refresh-token management for these accounts is not implemented
-- by the key-only transport; use an approved server key in the interim, or
-- implement refreshable scoped JWT auth before choosing this role arrangement.
BEGIN;
GRANT SELECT, INSERT, UPDATE ON public.asset_market_windows,
  public.asset_proxy_candles, public.asset_market_predictions TO authenticated;

CREATE POLICY research_windows_read ON public.asset_market_windows FOR SELECT TO authenticated
  USING ((auth.jwt()->'app_metadata'->>'btcandthings_role') IN ('collector','dashboard'));
CREATE POLICY research_windows_insert ON public.asset_market_windows FOR INSERT TO authenticated
  WITH CHECK ((auth.jwt()->'app_metadata'->>'btcandthings_role') = 'collector');
CREATE POLICY research_windows_update ON public.asset_market_windows FOR UPDATE TO authenticated
  USING ((auth.jwt()->'app_metadata'->>'btcandthings_role') = 'collector')
  WITH CHECK ((auth.jwt()->'app_metadata'->>'btcandthings_role') = 'collector');

CREATE POLICY research_candles_read ON public.asset_proxy_candles FOR SELECT TO authenticated
  USING ((auth.jwt()->'app_metadata'->>'btcandthings_role') IN ('collector','dashboard'));
CREATE POLICY research_candles_insert ON public.asset_proxy_candles FOR INSERT TO authenticated
  WITH CHECK ((auth.jwt()->'app_metadata'->>'btcandthings_role') = 'collector');
CREATE POLICY research_candles_update ON public.asset_proxy_candles FOR UPDATE TO authenticated
  USING ((auth.jwt()->'app_metadata'->>'btcandthings_role') = 'collector')
  WITH CHECK ((auth.jwt()->'app_metadata'->>'btcandthings_role') = 'collector');

CREATE POLICY research_predictions_read ON public.asset_market_predictions FOR SELECT TO authenticated
  USING ((auth.jwt()->'app_metadata'->>'btcandthings_role') IN ('collector','dashboard'));
CREATE POLICY research_predictions_insert ON public.asset_market_predictions FOR INSERT TO authenticated
  WITH CHECK ((auth.jwt()->'app_metadata'->>'btcandthings_role') = 'collector');
-- Immutable predictions: no UPDATE or DELETE policy.
COMMIT;
