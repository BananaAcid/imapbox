# implementation notes


## https://discuss.python.org/t/support-for-oauth2-in-poplib-imaplib/19747

### Support for OAuth2 in poplib/imaplib

Microsoft and Google are (or already have) dropped basic auth (username + password) support in their POP and IMAP servers.

Instead you are now supposed to use OAuth2 which authenticates in a base64 encoded auth token.

This is described in more detail here :

O365 : Authenticate an IMAP, POP or SMTP connection using OAuth | Microsoft Learn

Gmail: OAuth 2.0 Mechanism  |  IMAP for Gmail  |  Google Developers

For e.g. POP all we would need in poplib.py is something like:

```python
def oauth(self, token):
    """Send oauth2 authentication token, return response

    """
    return self._shortcmd('AUTH XOAUTH2 %s' % token)
```
It looks like we need two different implementations unfortunately. Google expects it on a single line, e.g.:

```
> AUTH XOAUTH2 <token>
```
While Microsoft expects it on 2 lines, e.g.


```
> AUTH XOAUTH2
< +
> <token>
```
Is this something we could add tot poplib and imaplib ?

Thanks,
Geert



## https://stackoverflow.com/a/13467538/1644202

```python
# Source - https://stackoverflow.com/a/13467538
# Posted by David Dehghan, modified by community. See post 'Timeline' for change history
# Retrieved 2026-05-14, License - CC BY-SA 4.0

'scope': 'https://mail.google.com/'
'access_type': 'offline'


import base64
import imaplib

my_email = "xyz@gmail.com"
access_token = ""    #Oauth2 access token

auth_string = GenerateOAuth2String(my_email, access_token, base64_encode=False)
TestImapAuthentication(my_email, auth_string)


def TestImapAuthentication(user, auth_string):
  """Authenticates to IMAP with the given auth_string.

  Prints a debug trace of the attempted IMAP connection.

  Args:
    user: The Gmail username (full email address)
    auth_string: A valid OAuth2 string, as returned by GenerateOAuth2String.
        Must not be base64-encoded, since imaplib does its own base64-encoding.
  """
  print
  imap_conn = imaplib.IMAP4_SSL('imap.gmail.com')
  imap_conn.debug = 4
  imap_conn.authenticate('XOAUTH2', lambda x: auth_string)
  imap_conn.select('INBOX')


def GenerateOAuth2String(username, access_token, base64_encode=True):
  """Generates an IMAP OAuth2 authentication string.

  See https://developers.google.com/google-apps/gmail/oauth2_overview

  Args:
    username: the username (email address) of the account to authenticate
    access_token: An OAuth2 access token.
    base64_encode: Whether to base64-encode the output.

  Returns:
    The SASL argument for the OAuth2 mechanism.
  """
  auth_string = 'user=%s\1auth=Bearer %s\1\1' % (username, access_token)
  if base64_encode:
    auth_string = base64.b64encode(auth_string)
  return auth_string
```


## https://github.com/aler9/howto-gmail-imap-oauth2

Sample code of the Gmail-IMAP-Oauth2 authentication procedure, in Python and Go. Allows to perform automated operations on emails without toggling the "less secure apps" switch on the Google account page. Code is as simple as possible and is working as of 2019.

```python
from urllib.parse import urlencode
from urllib.request import urlopen, Request
import json
from imaplib import IMAP4_SSL

# create a Google app here https://console.developers.google.com
# then fill the following variables
GMAIL_CLIENT_ID = ""
GMAIL_CLIENT_SECRET = ""

# generate and print authorization link
url = "https://accounts.google.com/o/oauth2/auth?" + urlencode({
    "client_id": GMAIL_CLIENT_ID,
    "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
    "scope": "https://mail.google.com/ email",
    "response_type": "code",
})
print("visit\n%s\n" % url)

# read response code
code = input("paste reponse code: ")
print("")

# exchange code with access token
with urlopen(Request("https://accounts.google.com/o/oauth2/token", data=urlencode({
        "client_id": GMAIL_CLIENT_ID,
        "client_secret": GMAIL_CLIENT_SECRET,
        "code": code,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        "grant_type": "authorization_code",
    }).encode())) as res:
    eres = json.loads(res.read())

# request user email
with urlopen(Request("https://www.googleapis.com/oauth2/v2/userinfo", headers={
        "Authorization": "Bearer %s" % eres["access_token"],
    })) as res:
    ures = json.loads(res.read())

# connect to imap
imap = IMAP4_SSL("imap.gmail.com", 993)

# authenticate the gmail way
imap.authenticate("XOAUTH2", lambda x:
    "user=%s\1auth=Bearer %s\1\1" % (ures["email"], eres["access_token"]))

# the following is just an example that shows available folders
# you can use any function provided by imaplib
# https://docs.python.org/3/library/imaplib.html

print("available folders:")
res,data = imap.list('""', "*")
for mbox in data:
    print(mbox.decode())

print("")
```