import json
import html
import streamlit.components.v1 as components


def render_chart(candle_frame, reference=None, minute_frame=None):
    """Render an interactive Kraken BTC/USD chart."""
    candles = []
    for timestamp, row in candle_frame.iterrows():
        candles.append({
            "time": int(timestamp.timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })

    if not candles:
        return

    minute_data = []
    if minute_frame is not None:
        for timestamp, row in minute_frame.iterrows():
            minute_data.append({
                "time": int(timestamp.timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })

    minute_json = json.dumps(minute_data)
    chart_data = json.dumps(candles)
    target = float(reference) if reference is not None else None
    target_data = json.dumps(target)

    page = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <script src="https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
      <style>
        body { margin:0; background:#151f32; font-family:Arial,sans-serif; }
        #chart { width:100%; height:290px; }
        #status { color:#94a3b8; font-size:12px; padding:8px; }

        .chart-panel {
          background:linear-gradient(110deg,#17263c,#121e30);
          border:1px solid #334b66;
          border-radius:14px;
          padding:10px;
          overflow:hidden;
          box-shadow:none;
        }
</style>
    </head>
    <body>
      <div class="chart-panel"><div id="chart"></div></div>
      <div id="status">Kraken BTC/USD · Interactive chart</div>
      <script>
        const candles = __CANDLES__;
        const historicalMinutes = __MINUTE_CANDLES__;
        const target = __TARGET__;
        const container = document.getElementById('chart');

        if (!window.LightweightCharts) {
          document.getElementById('status').textContent =
            'Chart library unavailable. Static chart fallback required.';
        } else {
          const chart = LightweightCharts.createChart(container, {
            layout: {
              background: { color:'#151f32' },
              textColor:'#94a3b8'
            },
            grid: {
              vertLines:{color:'#29384e'},
              horzLines:{color:'#29384e'}
            },
            width:container.clientWidth,
            height:290,
            timeScale:{timeVisible:true,secondsVisible:false},
            crosshair:{mode:LightweightCharts.CrosshairMode.Normal}
          });

          const series = chart.addCandlestickSeries({
            upColor:'#22c55e',
            downColor:'#f87171',
            borderVisible:false,
            wickUpColor:'#22c55e',
            wickDownColor:'#f87171'
          });

          series.setData(candles);

          if (target !== null && Number.isFinite(target)) {
            series.createPriceLine({
              price:target,
              color:'#fbbf24',
              lineWidth:2,
              lineStyle:LightweightCharts.LineStyle.Dashed,
              axisLabelVisible:true,
              title:'US target'
            });
          }

          chart.timeScale().fitContent();

          // Live Kraken OHLC data, separate from prediction calculations.
          const status = document.getElementById('status');
          const intervalSeconds = __INTERVAL_SECONDS__;
          let socket = null;
          let reconnectTimer = null;
          let lastLiveTime = 0;
          let pendingCandle = null;
          let lastRenderedTime = candles[candles.length - 1].time;

          // Retain individual minute candles for accurate aggregation.
          const minuteCandles = new Map(
            historicalMinutes.map(candle => [candle.time, candle])
          );
          let currentBucket = null;
          let bucketMinutes = new Map();

          function processOHLC(raw) {
            const minuteTime = Date.parse(raw.interval_begin) / 1000;
            const minute = {
              time: minuteTime,
              open: Number(raw.open),
              high: Number(raw.high),
              low: Number(raw.low),
              close: Number(raw.close)
            };

            if (!Number.isFinite(minuteTime) ||
                ![minute.open, minute.high, minute.low, minute.close]
                  .every(Number.isFinite)) return;

            // Replace the matching historical minute with Kraken's
            // latest official OHLC values.
            minuteCandles.set(minuteTime, minute);

            const bucket = Math.floor(minuteTime / intervalSeconds)
              * intervalSeconds;

            if (bucket < lastRenderedTime) return;

            const rows = [...minuteCandles.values()]
              .filter(x => x.time >= bucket &&
                           x.time < bucket + intervalSeconds)
              .sort((a, b) => a.time - b.time);

            if (!rows.length || rows[0].time !== bucket) {
              status.textContent = 'Waiting for missing candle history...';
              return;
            }

            // Do not aggregate across missing minute boundaries.
            for (let i = 1; i < rows.length; i++) {
              if (rows[i].time - rows[i - 1].time !== 60) {
                status.textContent = 'Candle history gap detected';
                return;
              }
            }

            const first = rows[0];
            const last = rows[rows.length - 1];

            pendingCandle = {
              time: bucket,
              open: first.open,
              high: Math.max(...rows.map(x => x.high)),
              low: Math.min(...rows.map(x => x.low)),
              close: last.close
            };

            lastLiveTime = Date.now();
            status.textContent = '● LIVE · Kraken official OHLC';
          }

          function connectLive() {
            if (reconnectTimer) clearTimeout(reconnectTimer);
            status.textContent = 'Connecting to Kraken OHLC...';

            socket = new WebSocket('wss://ws.kraken.com/v2');

            socket.onopen = () => {
              socket.send(JSON.stringify({
                method: 'subscribe',
                params: {
                  channel: 'ohlc',
                  symbol: ['BTC/USD'],
                  interval: 1
                }
              }));
            };

            socket.onmessage = event => {
              try {
                const message = JSON.parse(event.data);
                if (message.channel !== 'ohlc' ||
                    !Array.isArray(message.data)) return;

                for (const candle of message.data) {
                  processOHLC(candle);
                }
              } catch (error) {
                console.error('Kraken OHLC error:', error);
              }
            };

            socket.onclose = () => {
              status.textContent = 'Reconnecting to Kraken...';
              reconnectTimer = setTimeout(connectLive, 5000);
            };

            socket.onerror = () => {
              status.textContent = 'Kraken connection interrupted';
              socket.close();
            };
          }

          setInterval(() => {
            if (pendingCandle &&
                pendingCandle.time >= lastRenderedTime) {
              series.update(pendingCandle);
              lastRenderedTime = pendingCandle.time;
            }

            if (lastLiveTime &&
                Date.now() - lastLiveTime > 30000) {
              status.textContent = 'Waiting for fresh Kraken candles...';
            }
          }, 10000);

          connectLive();

          new ResizeObserver(() => {
            chart.applyOptions({width:container.clientWidth});
          }).observe(container);
        }
      </script>
    </body>
    </html>
    """

    page = page.replace("__CANDLES__", chart_data)
    page = page.replace("__MINUTE_CANDLES__", minute_json)
    page = page.replace("__TARGET__", target_data)
    interval_seconds = (
        int(candle_frame.index[1].timestamp() - candle_frame.index[0].timestamp())
        if len(candle_frame) > 1 else 60
    )
    page = page.replace("__INTERVAL_SECONDS__", str(interval_seconds))

    components.html(page, height=348, scrolling=False)
