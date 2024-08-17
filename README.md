![IMAPBOX](logo.png)

> [!NOTE]
> **Why a fork?**
> 
> This is a modified version, to include functions that I believe are helpful as CLI tool and a Docker service.
> I use it together with ImapSync.

Dump IMAP inbox to a local folder in a regular backupable format: HTML, PDF, JSON and attachments.

This program aims to save a mailbox for archive using files in indexable or searchable formats. The produced files should be readable without external software, for example, to find an email in backups using only the terminal.

For each email in an IMAP mailbox, a folder is created with the following files:

File              | Description
------------------|------------------
__message.html__  | If an html part exists for the message body. the `message.html` will always be in UTF-8, the embedded images links are modified to refer to the attachments subfolder.
__message.pdf__   | This file is optionally created from `message.html` when the `wkhtmltopdf` option is set in the config file.
__attachments__   | The attachments folder contains the attached files and the embeded images.
__message.txt__   | This file contain the body text if available in the original email, always converted in UTF-8.
__metadata.json__ | Various informations in JSON format, date, recipients, body text, etc... This file can be used from external applications or a search engine like [Elasticsearch](http://www.elasticsearch.com/).
__raw.eml.gz__    | A gziped version of the email in `.eml` format.

Imapbox was designed to archive multiple mailboxes in one common directory tree,
copies of the same message spread knew several account will be archived once using the Message-Id property, if possible (ID not missing, ID not to long for filesystem).

## Use cases

* I use the script to merge all my mail accounts in one searchable directory on my NAS server.
* Report on a website the content of an email address, like a mailing list.
* Sharing address of several employees to perform cross-searches on a common database.
* Archiving an IMAP account because of mailbox size restrictions, or to restrain the used disk space on the IMAP server.
* Archiving emails to PDF format.

## Config file

Use `./config.cfg` `~/.config/imapbox/config.cfg` or `/etc/imapbox/config.cfg`

Alternatively specifiy the shell argument `-c` to provide the path to a config file. E.g. `-c ./config.client1.cfg`

Example:
```ini
[imapbox]
local_folder=/var/imapbox
days=6
wkhtmltopdf=/opt/bin/wkhtmltopdf
specific_folders=True

[account1]
host=mail.autistici.org
username=username@domain
password=secret
ssl=True

[account2]
host=imap.googlemail.com
username=username@gmail.com
password=secret
remote_folder=INBOX
port=993
```

### The imapbox section

Possibles parameters for the imapbox section:

Parameter       | Description
----------------|----------------------
local_folder    | The full path to the folder where the emails should be stored. If the local_folder is not set, imapbox will download the emails in the current directory. This can be overwritten with the shell argument `-l`.
days            | Number of days back to get in the IMAP account, this should be set greater and equals to the cronjob frequency. If this parameter is not set, imapbox will get all the emails from the IMAP account. This can be overwritten with the shell argument `-d`.
wkhtmltopdf     | (optional) The location of the `wkhtmltopdf` binary. By default `pdfkit` will attempt to locate this using `which` (on UNIX type systems) or `where` (on Windows). This can be overwritten with the shell argument `-w`.
specific_folders| (optional) Backup into specific account subfolders. By default all accounts will be combined into one account folder. This can be overwritten with the shell argument `-f`.
test_only       | (optional) Only a connection and folder retrival test will be performed. This can be overwritten with the shell argument `-t`.

### Other sections

You can have has many configured account as you want, one per section. Sections names may contains the account name.

Possibles parameters for an account section:

Parameter       | Description
----------------|----------------------
host            | IMAP server hostname
username        | Login id for the IMAP server.
password        | (optional) The password will be saved in cleartext, for security reasons, you have to run the imapbox script in userspace and set `chmod 700` on your `~/.config/mailbox/config.cfg` file. The user will prompted for a password if this parameter is missing.
remote_folder   | (optional) IMAP folder name (multiple folder name is not supported for the moment). Default value is `INBOX`. You can use `__ALL__` to fetch all folders.
port            | (optional) Default value is `993`.
ssl            | (optional) Default value is `False`. Set to `True` to enable SSL
dsn             | (optinoal) Use a specific DSN to set account paramaters. All other parameters in the account section will overwrite these. This can be used with the shell argument `-n <dsn>`. Example: `imaps://username:password@imap.server.tld:993/__ALL__`

## Metadata file

Property        | Description
----------------|----------------------
Subject         | Email subject
Body            | A text version of the message
From            | Name and email of the sender
To              | An array of recipients
Cc              | An array of recipients
Attachments     | An array of files names
Date            | Message date with the timezone included, in the `RFC 2822` format
Utc             | Message date converted in UTC, in the `ISO 8601` format. This can be used to sort emails or filter emails by date
WithHtml        | Boolean, if the `message.html` file exists or not
WithText        | Boolean, if the `message.txt` file exists or not

## Elasticsearch

The `metadata.json` file contain the necessary informations for a search engine like [Elasticsearch](http://www.elasticsearch.com/).
Populate an Elasticsearch index with the emails metadata can be done with a simple script.

Create an index:

```bash
curl -XPUT 'localhost:9200/imapbox?pretty'
```

Add all emails to index:

```bash
#!/bin/bash
cd emails/
for ID in */ ; do
    curl -XPUT "localhost:9200/imapbox/message/${ID}?pretty" --data-binary "@${ID}/metadata.json"
done
```

A front-end can be used to search in email archives:

* [Calaca](https://github.com/polo2ro/Calaca) is a beautiful, easy to use, search UI for Elasticsearch.
* [Facetview](https://github.com/okfn/facetview)

## Search in emails without indexation process

[jq](http://stedolan.github.io/jq/) is a lightweight and flexible command-line JSON processor.

Example command to browse emails:

```bash
find . -name "*.json" | xargs cat | jq '[.Date, .Id, .Subject, " ✉ "] + .From | join(" ")'
```

Example with a filter on UTC date:

```bash
find . -name "*.json" | xargs cat | jq 'select(.Utc > "20150221T130000Z")'
```

## Local install

This script requires Python 3.4 for `master` branch and the following libraries:
* [six](https://pypi.org/project/six)
* [chardet](https://pypi.python.org/pypi/chardet) – required for character encoding detection.
* [pdfkit](https://pypi.python.org/pypi/pdfkit) – optionally required for archiving emails to PDF.

### Installation

Python 3.x must be installed allready

```bash
git clone https://github.com/polo2ro/imapbox.git ./imapbox

cd imapbox 

python3 -m venv ./
source ./bin/activate

pip install --no-cache-dir -r requirements.txt

cd ..
```

```bash
# usage
# a config.cfg is expected as described above
python ./imapbox/imapbox.py
```

## Usage with Docker compose

```
version: '3'
services:

  imapbox:
    image: bananaacid/imapbox
    container_name: imapbox
    volumes:
      # use a docker volume, as backup location
      - imapbox_data:/var/imapbox

      # if you want to specify a specific folder as backup folder
      #- ./tmp/backup/:/var/imapbox/

      # change the path './tmp/config.cfg' to the config
      - ./tmp/config.cfg:/etc/imapbox/config.cfg

volumes:
  imapbox_data:
```

`docker compose run --rm imapbox`

## Build an executable

Within the same Py-Env, do:
```bash
pip install --no-cache-dir  pyinstaller

pyinstaller --onefile ./imapbox/imapbox.py  
```

The resulting executable will be generated into the ./dist folder.

## Test with the Dockerfile

Use the test file to check if everything works as expected:

```bash
docker compose -f ./docker-compose.local-test.yml  up
```
Note, the following must exist:
```
./tmp/backup/       -- folder to backup to
./tmp/config.cfg    -- config to use
```

If you run this multiple times, remove the previously generated images and containers.

## Build own docker image and deploy to dockerhub

1. Create a new repository at Docker Hub
2. `docker login`
3. `docker build -t imapbox:latest .`
4. `docker tag imapbox:latest [USERNAME]/imapbox:latest`
5. `docker push [USERNAME]/imapbox:latest`


## Similar projects

[NoPriv](https://github.com/RaymiiOrg/NoPriv) is a python script to backup any IMAP capable email account to a browsable HTML archive and a Maildir folder.

## License

The MIT License (MIT)
