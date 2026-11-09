"""Independent pbot.shaneathon.com frontend. Read-only; no order submission."""
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from trading_bot.core import STREAMS
from trading_bot.status_client import read_status,read_trades

st.set_page_config(page_title='PBot · Paper Trading',page_icon='◈',layout='wide')
st.html('''<style>
.stApp{background:#09121e;color:#e5edf7}.block-container{max-width:1500px;padding-top:1.5rem}
h1,h2,h3{letter-spacing:-.03em}.hero{padding:25px;border:1px solid #29445a;border-radius:18px;background:linear-gradient(120deg,#123342,#111d31);margin-bottom:20px}
.kicker{font-size:12px;color:#67e8c0;letter-spacing:2px;font-weight:800}.title{font-size:38px;font-weight:800;color:#f4f9ff}
.subtitle{color:#9cb4c7;font-size:14px;margin-top:6px}.badge{float:right;padding:6px 12px;border:1px solid #4bbf9b;border-radius:20px;color:#8af2c9;font-size:12px}
[data-testid=stMetric]{background:#132235;padding:18px;border:1px solid #29445a;border-radius:14px}[data-testid=stMetricValue]{color:#f2f8ff}
[data-testid=stTabs] button{font-weight:700}

/* Compact desktop and mobile layout; retain readable controls and all content. */
[data-testid="stAppViewContainer"] .block-container{padding-top:1rem;padding-bottom:1.5rem}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li{font-size:.875rem;line-height:1.4}
h1{font-size:1.65rem!important}h2{font-size:1.3rem!important}h3{font-size:1.1rem!important}
[data-testid="stVerticalBlock"]{gap:.65rem}
.hero{padding:14px 18px;border-radius:12px;margin-bottom:12px}
.hero .title{font-size:26px;line-height:1.2}.hero .subtitle,.hero .sub{font-size:13px;margin-top:4px}
[data-testid="stMetric"]{padding:10px 12px;border-radius:10px}
[data-testid="stMetricValue"]{font-size:1.5rem}
[data-testid="stMetricLabel"] p{font-size:.8rem}
[data-testid="stTabs"] button{font-size:.85rem;padding:6px 10px}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{font-size:.82rem}
@media(max-width:640px){.hero .title{font-size:22px}.hero{padding:12px}[data-testid="stMetricValue"]{font-size:1.3rem}}
</style>''')
st.html('<div class="hero"><span class="badge">PAPER ONLY</span><div class="kicker">PBOT · INDEPENDENT TRADING TERMINAL</div><div class="title">Eight crypto markets. Independent wallets.</div><div class="subtitle">BTC · ETH · XRP · SOL — separate from the BTCandThings tracker</div></div>')
with st.sidebar:
    st.markdown('### PBot control room')
    st.caption('Target hostname: pbot.shaneathon.com')
    st.success('Paper trading mode')
    st.warning('Live submission is disabled in this release.')
    st.caption('This dashboard is read-only. Strategy and risk configuration live on the paper engine server.')
    refresh=st.toggle('Refresh status every 10 seconds',value=True)
    if st.button('Refresh now'):
        st.rerun()


def setting(name):
    try:
        value=st.secrets.get(name,'')
    except Exception:
        value=''
    return str(value or os.environ.get(name,''))


@st.cache_data(ttl=5,show_spinner=False)
def status(url,token):
    return read_status(url,token)


@st.cache_data(ttl=10,show_spinner=False)
def history(url,token,wallet,page,as_of):
    return read_trades(url,token,wallet,page,as_of)


def content():
    url,token=setting('PBOT_STATUS_URL'),setting('PBOT_READ_TOKEN')
    data={}
    if not url or not token:
        st.info('SETUP · Paper engine not connected yet. No trades or performance results are being invented.')
    else:
        try:
            data=status(url,token)
            age=time.time()-data.get('observed_at',0)
            if not 0<=age<=30:
                st.warning('Paper engine status is stale. Displayed positions may be out of date.')
        except Exception as exc:
            st.error(f'Paper status unavailable ({type(exc).__name__}). No account credentials are displayed.')
    if data.get('operation_mode') == 'OBSERVED_BOOK_PAPER':
        from trading_bot.display_status import central,ago,table_times
        health=data.get('display_health',{})
        labels={'EXIT_ORDER_PENDING':'Exit awaiting delayed bid execution','EXIT_WAITING_FOR_BOOK':'Exit triggered — waiting for executable bids','AUTOMATIC_ENTRY_PAUSE':'Automatic paper loss guard — new entries paused','ENGINE_STALE':'Engine heartbeat stale','INPUT_BLOCKED':'Input unavailable — entries blocked',
                'ENTRIES_PAUSED':'New entries paused','RISK_HALT':'Risk halt',
                'RISK_BUDGET_EXHAUSTED':'Entry risk budget exhausted','ORDER_ALREADY_ATTEMPTED':'Order already attempted — waiting for next window','ORDER_PROCESSING_LATE':'Pending order overdue',
                'ORDER_PENDING':'Order awaiting execution check','AWAITING_OFFICIAL_SETTLEMENT':'Waiting for official settlement',
                'POSITION_OPEN':'Paper position open','NO_CURRENT_MARKET':'Waiting for current market',
                'MARKET_DISABLED_BY_BTC15_SCOPE':'Inactive — BTC 15m only; history retained',
                'WAITING_FOR_ENTRY_WINDOW':'Waiting for entry window','ENTRY_WINDOW_CLOSED':'Waiting for next window',
                'WAITING_FOR_FRESH_SIGNAL':'Waiting for fresh prediction','WAITING_FOR_PAIRED_SIGNAL':'Waiting for both control predictions',
                'EVALUATING_BOOK_AND_EDGE':'Checking quotes and net edge','LATE_REVERSAL_CHECK':'Final two minutes — strong model reversal required','OPENING_WAIT':'Waiting for first 90 seconds to pass','ENTRY_QUOTA_REACHED':'Rolling market entry limit reached','ENTRY_RETRY_WAIT':'Waiting between entry attempts'}
        has_periods=all('performance_periods' in r for r in data.get('portfolios',{}).values())
        band_mode=data.get('configuration',{}).get('entry_strategy')=='MARKET_BAND'
        if band_mode: labels['EVALUATING_BOOK_AND_EDGE']='Checking market percentage and current lean'
        current_title='Current market-band experiment' if band_mode else 'Current trailing-exit experiment'
        period_options=(current_title,'Earlier entries','All history') if has_periods else ('All history',)
        period_choice=st.radio('Performance results',period_options,horizontal=True,key='pbot_performance_period')
        period_key={current_title:'current','Earlier entries':'earlier','All history':'all'}[period_choice]
        st.caption('Performance view: '+period_choice+'. Trades are grouped by the policy used at entry, including partial fills. Wallet cash and activity times always include full history.')
        choices=list(data.get('portfolios',{}))
        if choices:
            chosen=st.radio('Click a market or model',choices,horizontal=True,key='pbot_wallet_choice',
                            format_func=lambda name: 'BTC 15m · '+name if name in ('Champion','Challenger B') else name.replace('_',' · ')+' Research')
            report=data['portfolios'][chosen];account=report['account'];activity=report.get('activity',{})
            state=report.get('display_state',{});description=labels.get(state.get('state'),'Activity status not yet verified')
            st.markdown('### '+chosen)
            (st.error if state.get('severity')=='error' else st.warning if state.get('severity')=='warning' else st.info)(description)
            if state.get('window_end'):
                timing='Wait first 90 seconds; stop entries 3 minutes before 15m closes or 2 minutes before 5m closes.' if band_mode else 'Entries throughout the window; final two minutes require a strong reversal; final 15 seconds block entries.'
                st.caption('Current market closes '+central(state['window_end'])+' · approximately '+str(int(state['seconds_remaining']))+' seconds remaining. '+timing)
            performance=report.get('performance_periods',{}).get(period_key,{})
            values=st.columns(4)
            values[0].metric('Wallet virtual cash · all history',f"${float(account['cash']):,.2f}")
            values[1].metric('Wallet realized paper P/L',f"${float(performance.get('realized_pnl',account['realized_pnl'])):,.2f}")
            values[2].metric('Wallet open cost',f"${float(performance.get('open_cost',account['open_exposure'])):,.2f}")
            values[3].metric('Filled trades',performance.get('filled_trades',activity.get('filled_trade_count','—')))
            st.caption('P/L, open cost and filled-trade count above use '+period_choice+'. Cash is the actual wallet balance; it has not been reset.')
            st.markdown('**Last filled trade:** '+central(activity.get('last_filled_at'))+' · '+ago(activity.get('last_filled_at')))
            st.markdown('**Last settlement processed:** '+central(activity.get('last_settled_at'))+' · '+ago(activity.get('last_settled_at')))
            st.caption('Last order proposed: '+central(activity.get('last_order_proposed_at'))+'. Unfilled proposals are excluded from filled-trade history.')
            last_trade=activity.get('last_trade')
            st.markdown('#### Last trade details')
            if last_trade:
                st.write('**'+str(last_trade['market_slug'])+'** · **'+str(last_trade['side'])+'** · '+str(last_trade['quantity'])+' contracts at average $'+format(float(last_trade['entry_price']),'.4f'))
                net=('$'+str(last_trade['pnl'])) if last_trade.get('pnl') is not None else 'Pending settlement'
                st.caption('Entry policy: '+last_trade.get('entry_policy','Unclassified')+' · Total entry cost including fees: $'+str(last_trade['cost'])+' · Modeled fees: $'+str(last_trade['fees'])+' · Result: '+last_trade['result']+' · Net P/L: '+net)
                if last_trade.get('order_state'): st.caption('Order outcome: '+last_trade['order_state']+' · Requested quantity: '+str(last_trade.get('requested_quantity')))
            else: st.info('No filled trades yet in this wallet.')
            limits=data.get('configuration',{})
            if limits.get('target_trade_cost'):
                st.caption('Entry target and maximum: $'+limits['target_trade_cost']+' including modeled fees, per wallet. Whole-contract sizing, available depth and partial fills can reduce actual cost. No wallet may exceed this cap on a new entry.')
            elif limits.get('min_trade_cost'):
                st.caption('Proposed entry range: $'+limits['min_trade_cost']+'–$'+limits['max_trade_cost']+' including modeled fees, per wallet. Partial fills or price improvement may cost less than the minimum proposed amount.')
            else:
                st.caption('Maximum entry cost: $'+str(limits.get('max_trade_cost','10'))+' including modeled fees, per wallet.')
            st.caption('One open or pending position per wallet; maximum '+str(limits.get('max_entries_per_stream',3))+' filled entries per market stream across wallets in a rolling 15 minutes. Unfilled attempts do not count. Cash, liquidity and risk limits can reduce size or cause a skip.')
            if band_mode:
                st.caption('New entries: Polymarket current mark 54–64%, favored side matches fresh market-local lean. Exit at 2 points below actual entry mark or at 71%; thresholds are fixed, not trailing. Actual orders use bids/asks and modeled fees; fills are not guaranteed.')
            else:
                st.caption('Exit rule: trail the model probability of your held side winning by 5 percentage points from its peak. No fixed profit target. Exits require fresh bids, modeled sell fees and full visible size; immediate fills are not guaranteed.')
            if band_mode:
                with st.expander('Market-percentage exit activity'):
                    st.dataframe([{'Entry':r['entry_key'],'Entry mark':f"{float(r['entry_probability'])*100:.1f}%",'Current mark':f"{float(r['current_probability'])*100:.1f}%",'Fixed stop':f"{float(r['stop_probability'])*100:.1f}%",'Target':'71%','Received (Central)':central(r['observed_at']),'Trigger':r.get('reason')} for r in report.get('market_exit_states',[])],hide_index=True,width='stretch')
                    st.caption('Earlier open positions retain their previous exit rule until closed. Percentages are API current marks, not guaranteed sale prices.')
            with st.expander('Earlier model-based exit activity' if band_mode else 'Probability trail and paper exit activity'):
                st.dataframe([{'Entry':r['entry_key'],'Peak model probability':f"{float(r['peak'])*100:.1f}%",'Latest model probability':f"{float(r['current'])*100:.1f}%",'5-point trailing level':f"{(float(r['peak'])-.05)*100:.1f}%",'Signal (Central)':central(r['signal_at']),'Exit triggered (Central)':central(r['triggered_at'])} for r in report.get('probability_trails',[])],hide_index=True,width='stretch')
                st.write(report.get('exit_order_states',{}))
            if data.get('entry_policy_changed_at'): st.caption('New entry limits applied '+central(data['entry_policy_changed_at'])+'. Older trades retain their original amounts.')
            if st.checkbox('Show complete trade history',key='pbot_show_trade_history'):
                scope=st.radio('Trade history scope',('Selected wallet','All wallets'),horizontal=True,key='pbot_history_scope')
                target=chosen if scope=='Selected wallet' else '*'
                anchor_key='pbot_history_anchor_'+target;page_key='pbot_history_page_'+target
                if anchor_key not in st.session_state: st.session_state[anchor_key]=time.time()
                if st.button('Refresh trade list',key='pbot_history_refresh_'+target):
                    st.session_state[anchor_key]=time.time()
                    if page_key in st.session_state: del st.session_state[page_key]
                anchor=st.session_state[anchor_key]
                try:
                    first=history(url,token,target,1,anchor)
                    st.caption(str(first['total_filled_trades'])+' filled trades across all entry policies (labeled per row) · History membership as of '+central(anchor)+'. Refresh to include newer fills. Unfilled proposals are excluded.')
                    selected_page=st.selectbox('History page',range(1,first['page_count']+1),key=page_key,
                                              format_func=lambda n:'Page '+str(n)+' of '+str(first['page_count']))
                    result=first if selected_page==1 else history(url,token,target,selected_page,anchor)
                    if result['trades']:
                        formatted=[]
                        for trade in result['trades']:
                            formatted.append({'Filled (Central)':central(trade['opened_at']),'Wallet':trade['wallet'],
                                'Entry policy':trade.get('entry_policy','Unclassified'),'Market':trade['market_slug'],'Direction':trade['side'],'Contracts':trade['quantity'],
                                'Average entry ($)':trade['entry_price'],'Fees ($)':trade['fees'],'Total cost ($)':trade['cost'],
                                'Result':trade['result'],'Payout ($)':trade['payout'],'Net P/L ($)':trade['pnl'],
                                'Settlement processed (Central)':central(trade['closed_at']),'Close reason':trade.get('close_reason'),'Exit price':trade.get('exit_price'),'Exit fees':trade.get('exit_fees'),'Order outcome':trade['order_state']})
                        st.dataframe(formatted,hide_index=True,width='stretch')
                    else: st.info('No filled trades in this history selection yet.')
                except Exception as error:
                    st.error('Trade history unavailable ('+type(error).__name__+'). No trades were changed.')
            control=report.get('automatic_entry_pause')
            if control:
                st.warning('Automatic entry pause until '+central(control['paused_until'])+'. Existing positions still settle normally.')
                st.caption(control['reason'])
            if account.get('halted_reason'): st.error(account['halted_reason'])
        st.info('OBSERVED-BOOK PAPER · New forward ledgers. Old fixed-price results are excluded. Real orders remain disabled.')
        st.caption('Input: '+data.get('input_status','UNKNOWN')+' · '+data.get('fee_basis',''))
        if data.get('input_error'): st.error('Execution input rejected: '+data['input_error']+' — new entries are blocked.')
        if data.get('display_health_error'): st.error('Activity details could not be verified: '+data['display_health_error'])
        panels=st.columns(4)
        age=time.time()-health.get('engine_updated_at',data.get('observed_at',0))
        input_age=time.time()-health['input_updated_at'] if health.get('input_updated_at') is not None else None
        input_fresh=input_age is not None and 0<=input_age<=45 and not health.get('input_error')
        panels[0].metric('Engine heartbeat','Active' if 0<=age<=30 else 'STALE')
        panels[0].caption(central(health.get('engine_updated_at',data.get('observed_at'))))
        panels[1].metric('Execution input','Fresh' if input_fresh else 'Blocked' if health else 'Unverified')
        panels[1].caption(central(health['input_updated_at']) if health.get('input_updated_at') is not None else 'Input timestamp unavailable')
        panels[2].metric('Last filled trade · all wallets',ago(health.get('last_filled_at')))
        panels[2].caption(central(health.get('last_filled_at')))
        panels[3].metric('Last settlement processed',ago(health.get('last_settled_at')))
        panels[3].caption(central(health.get('last_settled_at')))
        st.caption('All times use America/Chicago Central time (CST/CDT). A waiting wallet can be healthy; heartbeat and input freshness are separate from trading activity.')
        if health.get('input_error'): st.error('Input check: '+health['input_error'])
        rows=[]
        for name,report in data.get('portfolios',{}).items():
            account=report['account'];activity=report.get('activity',{})
            for row in report.get('performance_periods',{}).get(period_key,{}).get('market_pnl',account.get('market_pnl',[])):
                rows.append(dict(wallet=name,**row,cash=account['cash'],reserved_cash=account['reserved_cash'],
                                 order_states=str(report.get('order_states',{})),
                                 last_trade_central=central(activity.get('last_filled_at')),
                                 current_status=labels.get(report.get('display_state',{}).get('state'),'Unverified')))
        st.markdown('### Paper P/L by market and wallet · '+period_choice)
        st.caption('Each wallet originally started with $1,000 independently. Cash includes all history; performance columns use the selected entry policy. These balances are not pooled.')
        if rows: st.dataframe(rows,hide_index=True,width='stretch')
        if choices:
            report=data['portfolios'][chosen];account=report['account']
            st.markdown('#### Recent positions · '+period_choice)
            from trading_bot.performance_periods import period,label
            st.dataframe(table_times([dict(p,entry_policy=label(p)) for p in account['positions'] if period_key=='all' or period(p,data.get('configuration',{}).get('version'))==period_key]),hide_index=True,width='stretch')
            st.caption('Recent positions are a bounded preview. Full trade history retains both policies, labeled per trade.')
            st.markdown('#### Historical skip reasons and order decisions')
            st.caption('These timestamps show when each distinct market/reason was FIRST recorded. Old rows are not a current alarm; use the live status above.')
            st.dataframe(table_times(report.get('decisions',[])),hide_index=True,width='stretch')
        review=data.get('automatic_review')
        with st.expander('Hourly paper review and automatic entry pauses'):
            if review:
                st.caption('Last review: '+central(review['reviewed_at'])+' · '+ago(review['reviewed_at']))
                if time.time()-review['reviewed_at']>5400: st.warning('Hourly review is overdue; check its service. Existing entry protections remain active.')
                st.caption('Each wallet: pause new entries for 6 hours after at least 10 current-policy closed trades lose $20 or more within 24 hours. After expiry, a new sample is required. Models and limits are never loosened automatically.')
                st.dataframe([dict(wallet=r['wallet'],status=r['status'],closed_trades=r['closed_trades'],net_pnl=r['net_pnl'],
                    paused_until=central((r.get('entry_pause') or {}).get('paused_until'))) for r in review['wallets']],hide_index=True,width='stretch')
            else: st.caption('Hourly automatic review is not installed or has not completed its first run.')
        with st.expander('Execution rules and remaining assumptions'):
            for item in data.get('limitations',[]): st.write(item)
            st.json(data.get('configuration',{}))
            st.code('touch /var/lib/pbot/STOP-OBSERVED',language='bash')
            st.caption('Pauses new entries and queued proposals; verified settlement processing continues.')
        st.caption('Historical fixed-price ledgers are preserved on the server. Their profits are not included above.')
        return
    if data.get('operation_mode') == 'DIRECTIONAL_SANDBOX':
        st.warning('DIRECTIONAL SANDBOX · Hypothetical fixed prices, not executable market fills. Real trading is disabled.')
        st.caption(data.get('price_assumption',''))
        if data.get('new_fixed_price_entries_paused'):
            st.info('New fixed-price entries are paused for the execution realism migration. Existing settlements continue. No replacement engine is active yet.')
        breakdown=[]
        for group in ('portfolios','market_portfolios'):
            for name,report in data.get(group,{}).items():
                for row in report.get('account',{}).get('market_pnl',[]):
                    breakdown.append(dict(wallet=name,**row))
        if breakdown:
            st.markdown('### P/L by market · historical fixed-price experiments')
            st.caption('Complete ledger totals. Wallets have independent virtual bankrolls; do not add them as one funded account. These results are not live-equivalent.')
            st.dataframe(breakdown,hide_index=True,width='stretch')
        st.caption(f"Forward BTC 15m comparison · input {data.get('input_status')} · "
                   f"shared signal markets {data.get('common_signal_markets',0)}. Separate virtual wallets; no historical entries are backfilled.")
        if data.get('feed_errors'): st.warning('Some prediction feeds are unavailable: '+str(data['feed_errors']))
        for column,(name,report) in zip(st.columns(2),data.get('portfolios',{}).items()):
            with column:
                st.markdown('### '+name)
                account=report['account']
                st.metric('Virtual cash',f"${float(account['cash']):,.2f}")
                st.metric('Hypothetical realized P/L',f"${float(account['realized_pnl']):,.2f}")
                positions=account.get('positions',[])
                closed=[p for p in positions if p['state']=='PAPER_CLOSED']
                st.metric('Settled experiments',account.get('settled_experiments_total',len(closed)))
                st.caption(f"Model: {report['configuration']['model_version']}")
                if account.get('halted_reason'): st.error(account['halted_reason'])
                if positions:
                    st.dataframe(positions,hide_index=True,width='stretch')
                    st.caption('Shows the latest 100 entries; the complete history remains in each separate ledger.')
                else: st.info('Waiting for both fresh predictions in the final 90–30 seconds of a BTC 15m window.')
                if report.get('decisions'): st.dataframe(report['decisions'],hide_index=True,width='stretch')
        with st.expander('Experiment rules and limitations'):
            st.write('Each wallet starts with $1,000 virtual cash, at most $10 per entry and one open position. '
                     'Assumed entry: 50¢ plus 1¢ slippage and 1¢ fee per share. '
                     'Each model requires at least 55% confidence under this fixed-cost assumption. '
                     'Both signals must be available for the same market. Only verified official outcomes settle positions. '
                     'This experiment tests directions under artificial prices; it does not demonstrate trading profitability. '
                     'A 10% drawdown halt and $100 daily loss budget apply. New tweaks need a separate experiment version.')
            st.code('touch /var/lib/pbot/STOP-SANDBOX',language='bash')
            st.caption('Pauses new hypothetical entries while verified settlements continue. Executable-quote fills remain disabled.')
        with st.expander('Automatic paper-trade reviews'):
            st.caption('Reviews update as verified settlements arrive. The baseline stays frozen; new tweaks use separate versions. '
                       'This release classifies losses and archives signals; it does not automatically optimize the strategy.')
            st.json(data.get('automatic_reviews',{}))
        if data.get('market_portfolios'):
            st.markdown('### All-market research experiments')
            st.caption('Separate $1,000 virtual wallets use each market’s own research forecast. '
                       'These are additional fixed-price directional experiments, not Champion clones or one combined funded portfolio. '
                       'Missing feeds stay paused. Fees/prices remain hypothetical.')
            rows=[]
            for name,report in data['market_portfolios'].items():
                account=report['account']
                rows.append({'Market':name,'State':report['coverage_status'],
                             'Virtual cash':f"${float(account['cash']):,.2f}",
                             'Hypothetical P/L':f"${float(account['realized_pnl']):,.2f}",
                             'Settled':account.get('settled_experiments_total',0)})
            st.dataframe(rows,hide_index=True,width='stretch')
            selected=st.selectbox('Inspect a research market',list(data['market_portfolios']),key='market_research_review')
            with st.expander(selected+' positions and latest decisions'):
                selected_report=data['market_portfolios'][selected]
                if selected_report['account']['positions']:
                    st.dataframe(selected_report['account']['positions'],hide_index=True,width='stretch')
                if selected_report['decisions']:
                    st.dataframe(selected_report['decisions'],hide_index=True,width='stretch')
                else: st.info(selected_report['coverage_status'])
        return
    account=data.get('account',{})
    if data.get('operation_mode') == 'OBSERVE_ONLY':
        st.warning('OBSERVATION ONLY · Paper entries are paused while quote mapping is verified. Live trading is disabled.')
        st.caption(f"Research input: {data.get('input_status', 'UNKNOWN')} · "
                   f"{data.get('input_markets', 0)} archived markets · "
                   f"{data.get('input_predictions', 0)} prediction snapshots. "
                   "The displayed balance is virtual money.")
    positions=account.get('positions',[])
    opened=[p for p in positions if p['state']=='PAPER_OPEN']
    columns=st.columns(4)
    def money(key):
        return f"${float(account[key]):,.2f}" if key in account else '—'
    columns[0].metric('Virtual cash',money('cash'))
    columns[1].metric('Open capital committed',money('open_exposure'))
    columns[2].metric('Realized paper P/L',money('realized_pnl'))
    columns[3].metric('Open paper positions',len(opened) if data else '—')
    if account.get('halted_reason'):
        st.error('New entries halted: '+account['halted_reason'])
    markets,portfolio,decisions,risk,live=st.tabs(['8 markets','Paper portfolio','Decision journal','Strategy & risk','Live readiness'])
    with markets:
        st.markdown('### Market coverage')
        rows=[]
        latest={(d.get('asset'),d.get('duration_seconds')):d for d in data.get('decisions',[])}
        for asset,seconds in sorted(STREAMS):
            decision=latest.get((asset,seconds),{})
            score=decision.get('history',{})
            rows.append({'Asset':asset,'Market':f'{seconds//60}m',
                'Open positions':sum(p['asset']==asset and p['duration_seconds']==seconds for p in opened),
                'Decision':decision.get('action','WAITING FOR DATA'),'Reason':decision.get('reason','—'),
                'Historical markets':score.get('markets','—')})
        st.dataframe(rows,hide_index=True,width='stretch')
        st.caption('BTC, ETH, XRP and SOL: 5m + 15m.')
    with portfolio:
        st.markdown('### Persistent paper ledger')
        if positions:
            st.dataframe(positions,hide_index=True,width='stretch')
        else:
            st.info('No paper positions yet. Positions open only when data, history, quotes and risk checks pass.')
        st.caption('Equity and drawdown use realized/cost-basis accounting, not live bid marks. Settlements use verified official outcomes.')
    with decisions:
        if data.get('decisions'):
            st.dataframe(data['decisions'],hide_index=True,width='stretch')
        else:
            st.info('Decision records will appear after the engine processes collected data.')
        st.caption('Each entry and skipped opportunity is recorded. The server retains the full decision journal; this panel shows its latest cycle.')
    with risk:
        config=data.get('configuration')
        if config:
            st.json(config)
        else:
            st.info('Risk configuration will appear after the paper engine is connected.')
        st.markdown('Entry checks include per-market historical scores, net modeled edge after costs, fresh mapped quotes, spread, available size, cash and exposure limits.')
        st.caption('Initial example settings are research assumptions, not optimized parameters or a verified fee schedule. Paper success never enables live trading automatically.')
        st.code('touch /var/lib/btcandthings-bot/STOP',language='bash')
        st.caption('With that kill-file path configured on the server, the command pauses new paper entries. Existing paper settlements continue.')
    with live:
        st.warning('LIVE ORDERS DISABLED · No real account is connected.')
        st.markdown('The live module prepares contract-mapped limit-order payloads and an explicit SDK preview interface. Submission is unavailable.')
        st.caption('A later live release needs explicit authorization, authenticated account checks, order/fill reconciliation, duplicate-order protection, exchange limits and live risk controls.')
    st.caption('Paper research only. This app contains no trade buttons and cannot submit orders.')


if refresh:
    st.fragment(run_every='10s')(content)()
else:
    content()
