# Public Coinbase raw recorder

An independent, unauthenticated WebSocket recorder for BTC-USD/ETH-USD/XRP-USD/
SOL-USD heartbeat, trade and Level-2 messages. No trading credentials or order
imports. Actual channel support must be confirmed on the droplet; a rejected
subscription produces an explicit error/backoff, never an invented feed.

Archives are private compressed JSONL segments retaining exact wire JSON,
receipt timestamp, monotonic time and connection ID. Lifecycle/gap events are
retained separately. Status deliberately says `book_ready=false`: this release
does not reconstruct tradable books, establish trade-side semantics or feed
orders. Existing REST collectors and bots remain independent.

`deploy/install-market-capture.sh --prepare` packages/tests only; `--apply`
installs a separate DynamicUser service with persistent private StateDirectory,
15% CPU quota, 256 MiB memory limit and low scheduling priority. It pauses when
free disk falls below 2 GiB or the day's compressed archives reach roughly
512 MiB, checked every ten seconds. The latter is a soft cap that can overshoot
between checks. Restarts preserve the daily budget by measuring existing files.
History is not deleted automatically. Raw data is local only; off-server
storage, retention and replay/book-validation work remain outstanding.

Sequence/channel fields are archived unchanged. This code does not infer gaps
from an undocumented universal sequence-number rule. Disconnects/timeouts and
budget pauses are explicit gaps; a later validated normalizer must rebuild
books from snapshots and follow channel-specific continuity rules. Resource
caps, network outages and server-side sampling can prevent complete coverage.
