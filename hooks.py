#!/usr/bin/env python
# -*- coding:utf-8 -*-


import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request

from utilities import errorHandler, is_docker


# dispatched hook targets run in threads; the registry lets the main process
# wait for them to finish before it exits (otherwise daemon threads are killed)
_active_threads = []
_active_lock = threading.Lock()


# event names that can start a new hook entry while splitting a hook value
_KNOWN_EVENTS = frozenset({'serverstart', 'accountstart', 'accountdone', 'newmail', 'newmails', 'done', 'error', 'all'})

# base folders used to resolve relative executable hook targets inside docker:
# the folder the active config.cfg lives in is preferred, then the application folder
_config_dir = None
_app_dir = os.path.dirname(os.path.realpath(sys.argv[0]))


def set_config_dir(path):
    """Register the folder the active config.cfg lives in (used to resolve relative hook executables in docker)."""
    global _config_dir
    _config_dir = path


# Events:
#   serverstart    - fired when a --server process becomes ready, before any account is checked (status payload, account is None)
#   accountstart  - fired when starting to check an account              (status payload)
#   accountdone   - fired when an account has been processed             (status payload + account new mail directories)
#   newmail       - fired for every single processed mail                (big payload, 1 item)
#   newmails/done - fired after the whole run, both are handled equally  (status payload, account is None)
#   error         - fired on any failure                                 (big payload, success=False, error info)
#   all           - wildcard, fired on any event above


def _tokenize(value):
    """Split a hook value into tokens on commas and newlines, honouring double/single quotes.
    Quotes are kept in the returned tokens, surrounding whitespace is stripped."""
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
    return tokens


def _strip_quotes(token):
    token = token.strip()
    if len(token) >= 2 and ((token[0] == token[-1] == '"') or (token[0] == token[-1] == "'")):
        return token[1:-1]
    return token


def parse_hook_entry(entry):
    """Validate and split a `event,"target"[,"arg",...]` entry, returns (event, target, args)."""
    tokens = [_strip_quotes(t) for t in _tokenize(entry)]
    if len(tokens) < 2:
        raise ValueError('expected "event,\\"command\\"[,"arg",...]"')
    return tokens[0], tokens[1], tokens[2:]


def split_hook_entries(value):
    """Split a comma-separated list of hook entries into `event,"target"[,"arg"...]` entries.
    Newlines are handled too, so a value spanning several indented (continued)
    config lines works as well. A token matching a known event name starts a new
    entry once the current entry already has its target set."""
    tokens = _tokenize(value)
    grouped = []
    for token in tokens:
        if token in _KNOWN_EVENTS and grouped and len(grouped[-1]) >= 2:
            grouped.append([token])
        elif grouped:
            grouped[-1].append(token)
        else:
            grouped.append([token])
    return [','.join(group) for group in grouped if group]


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
    entries = []
    seen = set()
    for event_name in event_names:
        for entry in hooks.get(event_name, []):
            if entry not in seen:
                seen.add(entry)
                entries.append(entry)
    for entry in hooks.get('all', []):
        if entry not in seen:
            seen.add(entry)
            entries.append(entry)

    if not entries:
        return

    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    for target, args in entries:
        thread = threading.Thread(target=_run_target, args=(target, args, data, payload), daemon=True)
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


def _resolve_path(target):
    """Resolve a relative executable hook target. Inside docker the folder the active config.cfg
    lives in is checked first, then the application folder; the first file found wins.
    Outside docker (or for absolute targets) the target is used unchanged."""
    if os.path.isabs(target):
        return target
    if is_docker():
        candidates = []
        if _config_dir:
            candidates.append(os.path.join(_config_dir, target))
        candidates.append(os.path.join(_app_dir, target))
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
    return target


def _run_target(target, args, data, payload):
    """Run a single hook target: URL (get+/post+/put+/delete+ with optional ${...} placeholders) -> HTTP,
    else executable (with extra args, JSON piped to stdin)."""
    label = payload.get('event') if isinstance(payload, dict) else None
    item_id = None
    if isinstance(payload, dict) and isinstance(payload.get('metadata'), dict):
        item_id = payload['metadata'].get('id')
    if label or item_id is not None:
        label = (label or '?') + (f'(id={item_id})' if item_id is not None else '')

    method, url = _split_method(target)
    if url.startswith('http://') or url.startswith('https://'):
        url = _render_url(url, payload)
        params = url.split('?', 1)[1] if '?' in url else None
        print(f'Hook {label}: {method} {url}' + (f'  params: {params}' if params else ''))
        try:
            request = urllib.request.Request(url,
                                             data=None if method == 'GET' else data,
                                             headers={'Content-Type': 'application/json'},
                                             method=method)
            urllib.request.urlopen(request, timeout=30)
        except Exception as e:
            errorHandler(None, f'Hook {method} to {url} failed: {e}', exitCode=None)
    else:
        command = _resolve_path(target)
        print(f'Hook {label}: {command}' + (f'  params: {" ".join(args)}' if args else ''))
        try:
            # the user is responsible for a correct shebang line (e.g. #!/usr/bin/env python3)
            # in their hook script; without it the executable bit alone is not enough to run it
            if os.path.isfile(command) and not os.access(command, os.X_OK):
                os.chmod(command, os.stat(command).st_mode | 0o111)  # +x so the shebang works
                print(f'Hook {label}: set executable bit on {command}')
            if os.path.isfile(command) and not os.access(command, os.X_OK):
                errorHandler(None, f'Hook target is not executable: {command}', exitCode=None)
                return
            subprocess.run([command] + list(args), input=data,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False)
        except Exception as e:
            errorHandler(None, f'Hook failed: {command}: {e}', exitCode=None)