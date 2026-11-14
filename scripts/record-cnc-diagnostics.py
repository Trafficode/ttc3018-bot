"""Persist read-only service diagnostics; never import or access CNC control."""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.request import ProxyHandler, build_opener


def redact(value):
    """Never retain credentials, even if a later status adds nested fields."""
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()
                if not any(word in key.lower() for word in
                           ('token', 'secret', 'password', 'authorization'))}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def diagnostic_status(status):
    """Allowlist machine observations; exclude the operator token and images."""
    cnc = status.get('cnc', {})
    camera = status.get('camera', {})
    return redact({
        'cnc': {key: cnc[key] for key in (
            'connected', 'fresh', 'state', 'reason', 'position', 'info',
            'job', 'probe_triggered', 'probe_tested', 'probe_inverted',
            'z_probe', 'surface_map', 'calibration', 'project_cycle', 'project_datum') if key in cnc},
        'camera': {key: camera[key] for key in ('ok', 'error', 'reason')
                   if key in camera},
        'cam_preparing': status.get('cam_preparing'),
    })


def open_log(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    logger = logging.getLogger('cnc-readonly-diagnostics')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(directory / 'cnc-diagnostics.jsonl',
                                  maxBytes=10 * 1024 * 1024, backupCount=5,
                                  encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    return logger


def emit(logger, event, **data):
    logger.info(json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                           'event': event, **data}, ensure_ascii=False))


def follow_journal(process, logger):
    """Mirror only the existing monitor unit's journal, without changing it."""
    for line in process.stdout:
        try:
            entry = json.loads(line)
            emit(logger, 'service_log', message=entry.get('MESSAGE'),
                 journalTime=entry.get('__REALTIME_TIMESTAMP'),
                 priority=entry.get('PRIORITY'))
        except (ValueError, TypeError):
            continue


def main():
    os.umask(0o077)
    directory = Path.home() / '.local/share/bark-beetle/diagnostics'
    logger = open_log(directory)
    stop = threading.Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: stop.set())
    emit(logger, 'recorder_started', intervalSeconds=2)
    journal = subprocess.Popen([
        'journalctl', '_SYSTEMD_USER_UNIT=ttc-monitor.service',
        '--follow', '--lines=30', '--output=json', '--no-pager'],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    threading.Thread(target=follow_journal, args=(journal, logger),
                     daemon=True).start()
    opener = build_opener(ProxyHandler({}))
    previous, last = None, 0
    try:
        while not stop.is_set():
            try:
                with opener.open('http://127.0.0.1:8766/api/status',
                                 timeout=3) as response:
                    current = diagnostic_status(json.load(response))
                if current != previous or time.monotonic() - last >= 60:
                    emit(logger, 'status', **current)
                    previous, last = current, time.monotonic()
            except Exception as error:
                # Do not log HTTP bodies, request headers or credential values.
                current = {'errorType': type(error).__name__}
                if current != previous or time.monotonic() - last >= 60:
                    emit(logger, 'status_unavailable', **current)
                    previous, last = current, time.monotonic()
            stop.wait(2)
    finally:
        journal.terminate()
        try:
            journal.wait(timeout=3)
        except subprocess.TimeoutExpired:
            journal.kill()
        emit(logger, 'recorder_stopped')


if __name__ == '__main__':
    main()
