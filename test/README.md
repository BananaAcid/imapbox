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