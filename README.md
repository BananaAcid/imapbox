![IMAPBOX](logo.png)

Dump IMAP inbox to a local folder in a regular backupable format: EML, TXT, HTML, PDF, JSON and attachments.

This program aims to save a mailbox for archive using files in indexable or searchable formats. The produced files should be readable without external software, for example, to find an email in backups using only the terminal.

> [!NOTE]
> **Why a fork?**
> 
> This is a modified version, to include features that I believe are helpful as a CLI tool and a Docker service, as well as extending the readme with helpful infos.
> I use it together with ImapSync.
>
> Some new features:
> - Test only mode (login credentials test), optionally output list of folders
> - Argument to specify a specific config file
> - Argument to show a version
> - Account can be specified as DSN, provided in the config and in CLI
> - Changed error handling to behave like a common CLI tool, errors are logged to error pipe
> - Added email search option
> - Modernized the docker files
> - Added documentation about how to use docker, adding metadata from subfolders to elasticsearch, building binaries and more, info on how to run the python script locally


## Backup email folder

For each email in an IMAP mailbox, a folder is created with the following files:

File              | Description
------------------|------------------
__message.html__  | If an html part exists for the message body. the `message.html` will always be in UTF-8, the embedded images links are modified to refer to the attachments subfolder.
__message.pdf__   | This file is optionally created from `message.html` when the `wkhtmltopdf` option is set in the config file.
__attachments__   | The attachments folder contains the attached files and the embeded images.
__message.txt__   | This file contain the body text if available in the original email, always converted in UTF-8.
__metadata.json__ | Various informations in JSON format, date, recipients, body text, etc... This file can be used from external applications or a search engine like [Elasticsearch](http://www.elasticsearch.com/).
__raw.eml.gz__    | A gziped version of the email in `.eml` format.

Imapbox was designed to archive multiple mailboxes in one common folder tree,
copies of the same message spread knew several account will be archived once using the Message-Id property, if possible (ID not missing, ID not to long for filesystem).

## Use cases

* Merge multiple mail accounts in one searchable folder.
* Archive multiple accounts into different folders.
* Report on a website the content of an email address, like a mailing list.
* Sharing address of several employees to perform cross-searches on a common database.
* Archiving an IMAP account because of mailbox size restrictions, or to restrain the used disk space on the IMAP server.
* Archiving emails to PDF format.

## Config file

Use `./config.cfg` `~/.config/imapbox/config.cfg` or `/etc/imapbox/config.cfg`

Alternatively specifiy the shell argument `-c` (or `--config`) to provide the path to a config file. E.g. `-c ./config.client1.cfg`

Example:
```ini
[imapbox]
local_folder=/var/imapbox
days=6
wkhtmltopdf=/opt/bin/wkhtmltopdf
specific_folders=True
# test_only=True


[accountName1]
host=mail.domain.tld
username=username@domain
password=secret
ssl=True

[username2@gmail.com]
host=imap.googlemail.com
username=username2@gmail.com
password=secret
remote_folder=INBOX
port=993

[username3@domain.tld]
dsn=imaps://username:password@domain.tld/__ALL__

[username4@domain.tld]
username=username4@domain.tld
password=secret
dsn=imaps://domain.tld/__ALL__
```

To run only a single account, the shell argument `-a` or `--account` can be used to specify which to use.

### The imapbox section

Possibles parameters for the imapbox section, all are optional:

Parameter       | Description
----------------|----------------------
local_folder    | The full path to the folder where the emails should be stored. If the local_folder is not set, imapbox will default to download the emails in to the current folder (within docker, it defaults to `/var/imapbox`). This can be overwritten with the shell argument `-l` or `--local-folder`.
days            | Number of days back to get in the IMAP account, this should be set greater and equals to the cronjob frequency. If this parameter is not set, imapbox will get all the emails from the IMAP account. This can be overwritten with the shell argument `-d` or `--days`.
wkhtmltopdf     | The location of the `wkhtmltopdf` binary. By default `pdfkit` will attempt to locate this using `which` (on UNIX type systems) or `where` (on Windows). This can be overwritten with the shell argument `-w` or `--wkhtmltopdf`.
specific_folders| Backup into specific account subfolders. By default all accounts will be combined into one account folder. This can be overwritten with the shell argument `-f` or `--folders`.
test_only       | Only a connection and folder retrival test will be performed, adding the optional "folders" as parameter will also show the found folders. This can be overwritten with the shell argument `-t` or `--test`.

### Other sections

You can have has many configured account as you want, one per section. Sections names may contains the account name.

Possibles parameters for an account section:

Parameter       | Description
----------------|----------------------
host            | (required) IMAP server hostname
username        | (required) Login id for the IMAP server.
password        | (required) The password will be saved in cleartext, for security reasons, you have to run the imapbox script in userspace and set `chmod 700` on your `~/.config/mailbox/config.cfg` file. The user will prompted for a password if this parameter is missing.
remote_folder   | (optional) IMAP folder name (multiple folder name is not supported for the moment). Default value is `INBOX`. You can use `__ALL__` to fetch all folders.
port            | (optional) Default value is `993`.
ssl             | (optional) Default value is `False`. Set to `True` to enable SSL
dsn             | (optinoal) Use a specific DSN to set account paramaters. All other parameters in the account section will overwrite these. To supply a single account only (instead of the config), this can be used with the shell argument `-n <dsn>` and `--dsn <dsn>`. Example: `imaps://username:password@imap.server.tld:993/__ALL__`

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

Add all emails to the index:

```bash
#!/bin/bash
cd emails/

IFS=$'\n'
for METADATAPATH in $(find . -name "metadata.json"); do

    subdir="${LINE%/metadata.json}"
    ID="${subdir##*/}"

    curl -XPUT "localhost:9200/imapbox/message/${ID}?pretty" --data-binary "@${METADATAPATH}"
done
```

A front-end can be used to search in email archives:

* [Calaca](https://github.com/polo2ro/Calaca) is a beautiful, easy to use, search UI for Elasticsearch.
* [Facetview](https://github.com/okfn/facetview)

## Search in emails without indexation process

### Inbuild command

The `-s` and `--search` shell argument with a filter parameter with the syntax of `Keyword,"fnmatch syntax"` can be used to perform simple a simple search in the local_folder for emails. The local_folder is taken from the current configuration or `-l`/`--local-folder` shell argument.

The possible keys (case sensitive) are listed in the `Metadata file` section.

Examples:
```bash
imapbox --search From,"user@domain.*"  # any tld
imapbox --search Body,"*some text*"    # in between text
imapbox --search WithText,True         # check boolean value

imapbox --local-folder ./backups --search From,"user@domain.*"
```

`fnmatch` accepts shell-style wildcards, `*` as any length of characters and `?` as single character as well as `[seq]` for any of the defined characters in the group and `[!seq]` for none of the characters in the group. See: https://docs.python.org/3/library/fnmatch.html


### Shell scripts

[jq](http://stedolan.github.io/jq/) is a lightweight and flexible command-line JSON processor.

Example command to browse emails:

```bash
find . -name "*.json" | xargs cat | jq '[.Date, .Id, .Subject, " ✉ "] + .From | join(" ")'
```

Example with a filter on UTC date:

```bash
find . -name "*.json" | xargs cat | jq 'select(.Utc > "20150221T130000Z")'
```


Powershell examples:

```powershell
gci -r -filter *.json |% { gc $_ | ConvertFrom-Json } |? { $_.Subject -imatch "Welcome" }
gci -r -filter *.json |% { gc $_ | ConvertFrom-Json } |? { $_.From -imatch "Support" }
gci -r -filter *.json |% { gc $_ | ConvertFrom-Json } |? { $_.Date -imatch "13 Aug 2024" }
gci -r -filter *.json |% { gc $_ | ConvertFrom-Json } |? { $_.UTC -gt "20240813T164821Z"  }
```

## Restoring emails

The EML files are the restoreable files. These can be opened with Outlook, Thunderbird, MacOS Mail and most other email software, as well as showing the UTF-8 content on commandline.

The EML files text files, UTF-8 encoded, and compressed by gzip before backuped.

### Using a graphical desktop

The unziped files can be double-clicked on most systems to view the mail, and may be drag-and-dropped into a mail account to be uploaded to that account.

It might help to navigate with a file browser into the specific backup folder, find all `raw.eml.gz` files, unzip them into a temp folder, then drag all EML files from there into your mail softwares account's folder.

### Using the commandline

- If you're using Windows, you can extract GZ files using the `tar -xvzf filename.gz` command in Command Prompt or by installing the 7-Zip program and using `7zip x filename.gz`
  ```
  tar:
  x = eXtract 
  z = filter through gZip
  v = be Verbose (show activity)
  f = filename
  ```
- On a Mac, just double-click the file to extract it, or use the command `gunzip filename.gz` in a Terminal window.
- If you're using Linux, use the `gzip -d filename.gz` to extract the files.


## Local install

This script requires **Python 3.4+** and the following libraries:
* [six](https://pypi.org/project/six) – a Python 2 and 3 compatibility library
* [chardet](https://pypi.python.org/pypi/chardet) – required for character encoding detection.
* [pdfkit](https://pypi.python.org/pypi/pdfkit) – optionally required for archiving emails to PDF.

### Installation

```bash
git clone https://github.com/bananaacid/imapbox.git ./imapbox

cd imapbox 

python -m venv ./
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

```yaml
services:

  imapbox:
    image: bananaacid/imapbox:latest
    container_name: imapbox
    volumes:
      # use a docker volume, as backup location
      - imapbox_data:/var/imapbox

      # if you want to specify a specific folder as backup folder
      #- ./tmp/backup/:/var/imapbox/

      # change the path './config.cfg' to the config
      # mounting files: an absolute path is always required
      #- ${PWD}/tmp/config.cfg:/etc/imapbox/config.cfg
      #
      # relative binding works fine
      - type: bind
        source: ./tmp/config.cfg
        target: /etc/imapbox/config.cfg

volumes:
  imapbox_data:
```

### Note

The docker container defaults `local_folder` internally to `/var/imapbox` to backup emails, if run within docker. 

There is no need to specify `local_folder` within the config or as shell argument.

### Clean up, remove last generated container:

`docker compose rm imapbox`

## Build an executable

Within the same Py-Env, do:
```bash
pip install --no-cache-dir  pyinstaller

pyinstaller --add-data "VERSION:." --onefile ./imapbox.py  
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
4. `docker tag imapbox:latest [USERNAME]/imapbox:$(cat VERSION)`
5. `docker tag imapbox:latest [USERNAME]/imapbox:latest`
6. `docker push [USERNAME]/imapbox:$(cat VERSION)`
7. `docker push [USERNAME]/imapbox:latest`

Pushing to Docker Hub requires the image name ("username/imapbox") to be exactly what the website shows in "Docker commands". 

## Similar projects

[NoPriv](https://github.com/RaymiiOrg/NoPriv) is a python script to backup any IMAP capable email account to a browsable HTML archive and a Maildir folder.

## License

The MIT License (MIT)
