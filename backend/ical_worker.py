"""One-shot download or parse worker with no inherited Google credentials.

The parent sends a private URL for fetch jobs, or feed bytes for parse jobs.
Resource limits are a robustness boundary, not an OS security sandbox.
"""
import base64
import json
import sys


def main():
    # Linux production limits. The parent also enforces a wall-clock timeout.
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        # Allow 128 MiB of growth above the interpreter baseline; some
        # instrumented test environments reserve substantial virtual space.
        baseline = 0
        try:
            from pathlib import Path
            for line in Path('/proc/self/status').read_text().splitlines():
                if line.startswith('VmSize:'):
                    baseline = int(line.split()[1])*1024
        except (OSError, ValueError):
            pass
        ceiling = max(256*1024*1024, baseline+128*1024*1024)
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    except (ImportError, ValueError):
        pass  # parent timeout and count limits still apply on other platforms
    from .ical_parser import ICalError, parse_calendar
    try:
        raw = sys.stdin.buffer.read(3*1024*1024 + 1)
        if len(raw) > 3*1024*1024:
            raise ICalError('Parser request exceeds the input limit.')
        body = json.loads(raw)
        if body.get('action') == 'fetch':
            from .feed_http import download
            result = download(body['url'], body.get('etag', ''), body.get('modified', ''))
        else:
            result = parse_calendar(base64.b64decode(body['data'], validate=True), body['start'], body['stop'], body['fallback'], body['zone'])
        encoded = json.dumps(result, ensure_ascii=True)
        if len(encoded) > 12*1024*1024:
            raise ICalError('Expanded feed exceeds the output limit.')
        print(encoded)
    except ICalError as e:
        print(json.dumps({'error':str(e)}))
    except Exception:
        print(json.dumps({'error':'Invalid calendar data; previous data retained.'}))


if __name__ == '__main__':
    main()
