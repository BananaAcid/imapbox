#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""Post imapbox hook payloads to a Discord webhook as an embed. Self-contained, standard library only.

Usage:
    cat file.json | ./hook-notifyOnDiscord.py <webhook-url> ["title text" ["description text"...]]
    as hook:
        newmail,"./hook-notifyOnDiscord.py","https://discord.com/api/webhooks/<webhook-id>/<webhook-token>","extra text"


The payload is read from stdin as JSON (imapbox pipes it there). The webhook URL is
taken from the first argument (fall back to the DISCORD_WEBHOOK_URL environment
variable). The first extra argument, when given, becomes the embed title (otherwise a
sensible one is derived from the event); any further arguments are joined into the
embed description.
"""

import json
import os
import sys
import urllib.request

EVENT_COLORS = {
    'newmail': 3447003,   # vivid blue
    'error': 15158332,    # red
    'done': 3066993,      # green
    'newmails': 3066993,
    'serverstart': 3447003,
    'accountstart': 3447003,
    'accountdone': 3447003,
}


def read_payload():
    """Read the JSON hook payload from stdin. Returns a dict (or {} when missing)."""
    raw = sys.stdin.buffer.read()
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode('utf-8'))
    except ValueError as e:
        print(f'hook-notifyOnDiscord: invalid JSON on stdin: {e}', file=sys.stderr)
        return {}
    # 'newmail' and 'error' events arrive as a single-item list
    if isinstance(data, list):
        return data[0] if data else {}
    if isinstance(data, dict):
        return data
    return {}


def _truncate(value, limit=64):
    value = str(value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + '...'


def _field(payload, *keys):
    return _pick(payload, *keys)


def _pick(mapping, *names):
    """Look up a key in a dict ignoring case (real metadata uses Id, Subject, From, ... while
    the hook payload also accepts lowercase names)."""
    if not isinstance(mapping, dict):
        return None
    lower = {str(key).lower(): value for key, value in mapping.items()}
    for name in names:
        if name in lower and lower[name] not in (None, ''):
            return lower[name]
    return None


def _flatten(value):
    """Turn a metadata value into a readable string. Handles sender lists like ["a@b.c"]
    and recipient lists like [["a@b.c", "Name"]], and attachment dict entries."""
    if isinstance(value, dict):
        for key in ('filename', 'name', 'error'):
            if value.get(key):
                return str(value[key])
        return str(value)
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            if isinstance(item, (list, tuple)):
                for sub in item:
                    if isinstance(sub, str) and sub.strip():
                        parts.append(sub)
                        break
            elif isinstance(item, dict):
                for key in ('filename', 'name'):
                    if item.get(key):
                        parts.append(str(item[key]))
                        break
            elif isinstance(item, str) and item.strip():
                parts.append(item)
        return ', '.join(dict.fromkeys(parts))
    return ' '.join(str(value).replace('\r', '').split())


def _metadata_rows(metadata, payload):
    rows = []
    date = _pick(metadata, 'date', 'utc')
    if date:
        rows.append(('Date', _flatten(date)))
    sender = _pick(metadata, 'sender', 'from')
    if sender:
        rows.append(('From', _flatten(sender)))
    recipient = _pick(metadata, 'recipient', 'to')
    if recipient:
        rows.append(('To', _flatten(recipient)))
    subject = _pick(metadata, 'subject')
    if subject:
        rows.append(('Subject', _flatten(subject)))
    cc = _pick(metadata, 'cc', 'bcc')
    if cc:
        rows.append(('Cc', _flatten(cc)))
    emailid = _pick(metadata, 'id')
    if emailid:
        rows.append(('Id', _truncate(emailid, 40)))
    folder = _pick(metadata, 'folder')
    if not folder and isinstance(payload.get('account'), dict):
        folder = payload['account'].get('remote_folder')
    if folder:
        rows.append(('Folder', _flatten(folder)))
    attachments = _pick(metadata, 'attachments') or []
    files = _flatten(attachments)
    if files and isinstance(attachments, list) and len(attachments) > 1:
        rows.append((f'Attachments ({len(attachments)})', files))
    elif files:
        rows.append(('Attachments', files))
    body = _pick(metadata, 'body')
    if body:
        rows.append(('Body', _flatten(body)))
    return rows


def _embed_fields(rows):
    """Group the info rows into Discord embed fields: three short values per row as inline
    fields (a 3-column table on desktop), longer values as full-width fields."""
    short = [row for row in rows if len(str(row[1])) <= 50]
    full = [row for row in rows if len(str(row[1])) > 50]
    fields = []
    for i in range(0, len(short), 3):
        for name, value in short[i:i + 3]:
            fields.append({'name': _truncate(str(name), 256),
                           'value': _truncate(str(value), 1024),
                           'inline': True})
    for name, value in full:
        fields.append({'name': _truncate(str(name), 256),
                       'value': _truncate(str(value), 1024),
                       'inline': False})
    return fields


def _event_rows(payload):
    """Relevant (name, value) rows for the payload event."""
    event = payload.get('event')
    if event == 'newmail':
        metadata = payload.get('metadata') or {}
        return _metadata_rows(metadata, payload)

    if event == 'error':
        rows = []
        metadata = payload.get('metadata') or {}
        emailid = _pick(metadata, 'id')
        if emailid:
            rows.append(('Id', _truncate(emailid, 40)))
        subject = _pick(metadata, 'subject')
        if subject:
            rows.append(('Subject', _flatten(subject)))
        error = payload.get('error')
        text = _flatten(error) if error else ''
        if text:
            rows.append(('Error', text))
        account = payload.get('account')
        if account:
            username = _pick(account, 'username')
            if username:
                rows.append(('Account', username))
        directory = _pick(payload, 'directory')
        if directory:
            rows.append(('Directory', directory))
        return rows

    # accountstart: the account archive path (account-specific with specific_folders,
    # the shared root without) is what matters, nothing else
    if event == 'accountstart':
        rows = []
        account = payload.get('account')
        if account:
            username = _pick(account, 'username')
            if username:
                rows.append(('Account', username))
        path = _pick(payload, 'path')
        if path:
            rows.append(('Directories', path))
        return rows

    # status events (serverstart, accountdone, newmails, done, ...)
    rows = []
    path = _pick(payload, 'path')
    if path:
        rows.append(('Path', path))
    account = payload.get('account')
    if account:
        username = _pick(account, 'username')
        if username:
            rows.append(('Account', username))
    directories = payload.get('directories')
    if directories:
        rows.append(('Directories', '\n'.join(str(directory) for directory in directories)))
    return rows


def _default_title(payload):
    """A sensible embed title for the event when no extra title argument was given."""
    event = payload.get('event') or 'event'
    if event == 'newmail':
        subject = _flatten(_pick(payload.get('metadata') or {}, 'subject') or '')
        return f'New email{f": {subject}" if subject else ""}'
    if event == 'error':
        return 'error'
    return event


def build_embed(payload, extras):
    """Build a Discord embed from the payload: the first extra argument (or a sensible
    default) becomes the title, the relevant payload information becomes embed fields."""
    event = payload.get('event') or 'event'
    rows = _event_rows(payload)
    title = f'{extras[0]} - {_default_title(payload)}' if extras else _default_title(payload)

    embed = {
        'title': _truncate(title, 256),
        'color': EVENT_COLORS.get(event, 3447003),
    }
    if rows:
        embed['fields'] = _embed_fields(rows)
    footer_parts = []
    if isinstance(payload.get('account'), dict):
        username = _pick(payload['account'], 'username')
        if username:
            footer_parts.append(username)
    directory = _pick(payload, 'directory')
    if directory:
        footer_parts.append(directory)
    if footer_parts:
        embed['footer'] = {'text': _truncate(' - '.join(footer_parts), 2048)}
    description = '\n'.join(_truncate(arg, 1900) for arg in extras[1:] if arg.strip())
    if description:
        embed['description'] = _truncate(description, 4096)
    return embed


def post(url, embed):
    """Send the embed to the Discord webhook. Native urllib only, no third party package."""
    data = json.dumps({'embeds': [embed]}).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',  # some endpoints reject the default urllib agent
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('DISCORD_WEBHOOK_URL')
    if not url:
        print('hook-notifyOnDiscord: no webhook URL given (use the first argument or set DISCORD_WEBHOOK_URL)', file=sys.stderr)
        return 2
    payload = read_payload()
    embed = build_embed(payload, sys.argv[2:])
    try:
        post(url, embed)
    except Exception as e:
        print(f'hook-notifyOnDiscord: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())