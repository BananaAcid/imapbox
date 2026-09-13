# Mock test environment

Two scripts bring up a fully local, dockerized imapbox test environment (GreenMail as the
IMAP server, the real `imapbox` image, Elasticsearch and the Calaca search UI).

## Order

1. `.\mock-server.ps1` — starts GreenMail as a Docker container, waits for it and seeds
   `alice@example.com` + `bob@example.com` with 10 mock emails each.
2. `.\mock-imapbox.ps1` — writes `cache\` (compose override, config, archive, ES data),
   builds and starts the imapbox stack, runs one immediate backup and checks the
   Elasticsearch index.

Tear down with `.\mock-imapbox.ps1 -Down`.

## Seed extra folders (`mock-seed-folders.ps1`)

Optional helper: SMTP can only deliver into `INBOX`, so this script seeds additional
folders for `alice@example.com` via raw IMAP on `127.0.0.1:3143`:

- creates `Draft`, `Trash` and `INBOX.important projects.someemail`
- appends 6 dummy mails: Draft 2026 ×2, Draft 2024 ×1, Trash 2026 ×2, subfolder 2026 ×1

```powershell
.\mock-seed-folders.ps1
```

Each run generates a fresh `Message-ID`/`UUID`, so rerunning it appends more unique test
mails (archived by imapbox as *new* on the next tick). The `cache\config\config.cfg`
[alice] DSN lists these folders, archived with flat names like
`archive/alice/INBOX.important projects.someemail/2026/<id>`. Note: GreenMail keeps
mailboxes in memory, so seeds are lost if the GreenMail container restarts.

## Test

Open **http://localhost:8088** (Calaca) and search with `*` to see all 20 indexed emails.

Useful URLs while the stack is up:

- Calaca UI:        http://localhost:8088
- Elasticsearch:    http://localhost:9200
- GreenMail UI:     http://localhost:8089

## Hooks used to test elastic search

`mock-imapbox.ps1` configures imapbox with two webhooks (see the generated
`cache\docker-compose.test.yaml`):

- `serverstart,"put+http://elasticsearch:9200/imapbox"` — on server start, creates the
  `imapbox` index (PUT /imapbox).
- `newmail,"put+http://elasticsearch:9200/imapbox/_doc/${metadata.id}"` — for every saved
  email, PUTs the full item payload into Elasticsearch using the mail id as document id
  (`${metadata.id}` is resolved from the item payload).