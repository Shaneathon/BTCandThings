"""PBot observation mode: research inputs, separate ledger, no paper entries."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
from trading_bot.core import Config, PaperBot
from trading_bot.runner import inputs


def export(source, destination, group=None):
    markets, predictions = inputs(source)
    data = dict(exported_at=time.time(), markets=markets, predictions=predictions)
    destination = Path(destination)
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix='.input-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        if group is not None:
            os.chown(temporary, 0, group)
            os.chmod(temporary, 0o640)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def observe(bot, path, now):
    markets, predictions, state = [], [], 'WAITING_FOR_RESEARCH_EXPORT'
    try:
        data = json.loads(Path(path).read_text())
        if not isinstance(data['markets'], list) or not isinstance(data['predictions'], list):
            raise ValueError('Invalid research export')
        if 0 <= now - data['exported_at'] <= 180:
            markets, predictions = data['markets'], data['predictions']
            state = 'FRESH'
        else:
            state = 'STALE_RESEARCH_EXPORT'
    except (OSError, ValueError, KeyError, TypeError):
        state = 'RESEARCH_EXPORT_UNAVAILABLE'
    # Hard-coded observation mode cannot be activated by removing a file.
    report = bot.cycle(markets, predictions, [], now, kill_switch=True)
    report.update(operation_mode='OBSERVE_ONLY', paper_entries_enabled=False,
                  input_status=state, input_markets=len(markets),
                  input_predictions=len(predictions),
                  blocked_reason='Quote mapping and execution inputs not verified')
    with bot.db:
        bot.db.execute('UPDATE bot_snapshot SET payload=? WHERE id=1',
                       (json.dumps(report, allow_nan=False),))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    ex = sub.add_parser('export')
    ex.add_argument('--source', type=Path, required=True)
    ex.add_argument('--output', type=Path, required=True)
    ex.add_argument('--group', type=int)
    watch = sub.add_parser('watch')
    watch.add_argument('--input', type=Path, required=True)
    watch.add_argument('--ledger', type=Path, required=True)
    watch.add_argument('--loop', action='store_true')
    args = parser.parse_args()
    if args.command == 'export':
        export(args.source, args.output, args.group)
        print('Research snapshot exported; source opened read-only.')
        return
    if args.input.resolve() == args.ledger.resolve():
        parser.error('Input and paper ledger must be separate')
    bot = PaperBot(args.ledger, Config())
    try:
        while True:
            report = observe(bot, args.input, time.time())
            print(json.dumps({k: report[k] for k in ('operation_mode', 'input_status',
                                                     'input_markets', 'paper_entries_enabled')}), flush=True)
            if not args.loop:
                break
            time.sleep(10)
    finally:
        bot.close()


if __name__ == '__main__':
    main()
