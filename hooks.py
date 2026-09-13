#!/usr/bin/env python
# -*- coding:utf-8 -*-


import json
import os
import re
import subprocess
import threading
import urllib.parse
import urllib.request

from utilities import errorHandler


# dispatched hook targets run in threads; the registry lets the main process
# wait for them to finish before it exits (otherwise daemon threads are killed)
_active_threads = []
_active_lock = threading.Lock()


# Events:
#   serverstart    - fired when a --server process becomes ready, before any account is checked (status payload, account is None)
#   accountstart  - fired when starting to check an account              (status payload)
#   accountdone   - fired when an account has been processed             (status payload + account new mail directories)
#   newmail       - fired for every single processed mail                (big payload, 1 item)
#   newmails/done - fired after the whole run, both are handled equally  (status payload, account is None)
#   error         - fired on any failure                                 (big payload, success=False, error info)
#   all           - wildcard, fired on any event above


def parse_hook_entry(entry):
    """Validate and split a --hook "event,\"target\"" entry, returns (event, target)."""
    event, sep, target = entry.partition(',')
    if not sep:
        raise ValueError('expected "event,\\"command\\""')
    return event.strip(), target.strip().strip('"').strip("'")


def split_hook_entries(value):
    """Split a comma-separated list of hook entries into `event,"target"` entries.
    Newlines are handled too, so a value spanning several indented (continued)
    config lines works as well."""
    tokens = []
    current = ''
    quote = None
    for char in value:
        if char in ('"', "'"):
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            current += char
        elif char in (',', '\n') and quote is None:
            if current.strip():
                tokens.append(current.strip())
            current = ''
        else:
            current += char
    if current.strip():
        tokens.append(current.strip())

    entries = []
    for i in range(0, len(tokens), 2):
        event = tokens[i]
        target = tokens[i + 1] if i + 1 < len(tokens) else ''
        entries.append(event + (',' + target if target else ''))
    return entries


def account_info(account):
    """Account data for the payload: same fields as if configured separately, without password or DSN."""
    info = {}
    for key in ('name', 'host', 'port', 'username', 'remote_folder', 'exclude_folder', 'ssl'):
        if account and key in account:
            info[key] = account[key]
    return info


def make_mail_item(event, account, directory, metadata, success=True, error=None):
    """Big payload item (newmail/error): metadata + account + directory."""
    item = {
        'event': event,
        'success': success,
        'error': error or {},
        'directory': directory,
        'account': account_info(account),
    }
    if metadata is not None:
        item['metadata'] = metadata
    return item


def make_status_item(event, account, path, directories, success=True, error=None):
    """Status payload: account + path + only ever new mail directories."""
    return {
        'event': event,
        'success': success,
        'error': error or {},
        'account': account_info(account) if account else None,
        'path': path,
        'directories': directories,
    }


def append_buffer(hookbuffer, account_name, directory):
    hookbuffer.append((account_name, directory))


def account_directories(hookbuffer, account_name):
    return [directory for name, directory in hookbuffer if name == account_name]


def all_directories(hookbuffer):
    return [directory for _, directory in hookbuffer]


def dispatch(hooks, event, payload):
    """Fire the hooks registered for `event` (and 'all') with `payload`, async/parallel."""
    _dispatch_targets(hooks, [event], payload)


def dispatch_status(hooks, event_names, payload):
    """Fire hooks registered under any of `event_names` (equally handled) and 'all'."""
    _dispatch_targets(hooks, event_names, payload)


def _dispatch_targets(hooks, event_names, payload):
    targets = []
    seen = set()
    for event_name in event_names:
        for target in hooks.get(event_name, []):
            if target not in seen:
                seen.add(target)
                targets.append(target)
    for target in hooks.get('all', []):
        if target not in seen:
            seen.add(target)
            targets.append(target)

    if not targets:
        return

    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    for target in targets:
        thread = threading.Thread(target=_run_target, args=(target, data, payload), daemon=True)
        thread.start()
        with _active_lock:
            _active_threads.append(thread)


def join_hooks():
    """Block until every dispatched hook thread has finished running."""
    while True:
        with _active_lock:
            if not _active_threads:
                break
            thread = _active_threads.pop(0)
        thread.join()


def _split_method(target):
    """Split an optional HTTP method prefix from a webhook URL (get+/post+/put+/delete+). Defaults to POST."""
    if target.startswith(('get+https://', 'get+http://')):
        return 'GET', target[4:]
    if target.startswith(('put+https://', 'put+http://')):
        return 'PUT', target[4:]
    if target.startswith(('delete+https://', 'delete+http://')):
        return 'DELETE', target[7:]
    if target.startswith(('post+https://', 'post+http://')):
        return 'POST', target[5:]
    return 'POST', target


_placeholder_re = re.compile(r'\$\{([A-Za-z0-9_.-]+(?:\[-?\d+\])*)\}')


def _resolve_placeholder(payload, name):
    """Resolve a dotted ${...} path against the payload dict (case-insensitive keys), with [i] list indexing. `id` aliases `metadata.id`."""
    if name == 'id':
        name = 'metadata.id'
    current = payload
    for part in name.split('.'):
        match = re.match(r'^(.*?)((?:\[-?\d+\])*)$', part)
        key, indexes = match.group(1), match.group(2)
        if key:
            if not isinstance(current, dict):
                return None
            found = next((candidate for candidate in current if str(candidate).lower() == key.lower()), None)
            if found is None:
                return None
            current = current[found]
        for index in re.finditer(r'\[(-?\d+)\]', indexes):
            if not isinstance(current, (list, tuple)):
                return None
            i = int(index.group(1))
            if i < -len(current) or i >= len(current):
                return None
            current = current[i]
    return current


def _render_url(url, payload):
    """Substitute ${...} placeholders in a webhook URL from the payload. Values are URL-encoded
    (slashes preserved); unresolved placeholders are left as-is."""
    def replace(match):
        value = _resolve_placeholder(payload, match.group(1))
        if value is None:
            return match.group(0)
        return urllib.parse.quote(str(value), safe='/')

    return _placeholder_re.sub(replace, url)


def _run_target(target, data, payload):
    """Run a single hook target: URL (get+/post+/put+/delete+ with optional ${...} placeholders) -> HTTP, else executable with JSON piped to stdin."""
    method, url = _split_method(target)
    if url.startswith('http://') or url.startswith('https://'):
        url = _render_url(url, payload)
        try:
            request = urllib.request.Request(url,
                                             data=None if method == 'GET' else data,
                                             headers={'Content-Type': 'application/json'},
                                             method=method)
            urllib.request.urlopen(request, timeout=30)
        except Exception as e:
            errorHandler(None, f'Hook {method} to {url} failed: {e}', exitCode=None)
    else:
        try:
            if not os.access(target, os.X_OK):
                errorHandler(None, f'Hook target is not executable: {target}', exitCode=None)
                return
            subprocess.run([target], input=data,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False)
        except Exception as e:
            errorHandler(None, f'Hook failed: {target}: {e}', exitCode=None)