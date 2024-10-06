#!/usr/bin/env python
#-*- coding:utf-8 -*-


import urllib
from utilities import errorHandler


# DSN:
# defaults to INBOX, path represents a single folder:
#  imap://username:password@imap.gmail.com:993/
#  imap://username:password@imap.gmail.com:993/INBOX
#
# get all folders
#  imap://username:password@imap.gmail.com:993/__ALL__
#
# singe folder with ssl, both are the same:
#  imaps://username:password@imap.gmail.com:993/INBOX
#  imap://username:password@imap.gmail.com:993/INBOX?ssl=true
#
# folder as provided as path or as query param "remote_folder" with comma separated list
#  imap://username:password@imap.gmail.com:993/INBOX.Drafts
#  imap://username:password@imap.gmail.com:993/?remote_folder=INBOX.Drafts
#
# combined list of folders with path and ?remote_folder
#  imap://username:password@imap.gmail.com:993/INBOX.Drafts?remote_folder=INBOX.Sent
#
# with multiple remote_folder:
#  imap://username:password@imap.gmail.com:993/?remote_folder=INBOX.Drafts
#  imap://username:password@imap.gmail.com:993/?remote_folder=INBOX.Drafts,INBOX.Sent
#
# setting other parameters
#  imap://username:password@imap.gmail.com:993/?name=Account1
def get_account(dsn, name=None):
    """
    Parse a DSN string and return a dictionary of account parameters.

    The DSN string should be in the form of:
    "imap[s]://username:password@server.tld:993/INBOX.Drafts,INBOX.Sent?remote_folder=INBOX.Drafts,More.Folders?ssl=true&name=Account1"

    The function will return a dictionary with the following keys:

    - name: The name of the account
    - host: The hostname of the IMAP server
    - port: The port number of the IMAP server
    - username: The username to login with
    - password: The password to login with
    - remote_folder: A string containing a comma separated list of folders to archive
    - ssl: A boolean indicating whether to use SSL or not

    The function will also set the name, either by the name parameter provided or generate one of the username and host.
    """
    account = {
        'name': 'account', # this i different to imapbox.py
        'host': None,
        'port': 993,
        'username': None,
        'password': None,
        'remote_folder': 'INBOX',
        'exclude_folder': None,
        'ssl': False,
    }

    parsed_url = urllib.parse.urlparse(dsn)
    
    if parsed_url.scheme.lower() not in ['imap', 'imaps']:
        raise ValueError('Scheme must be "imap" or "imaps"')
    
    account['ssl'] = parsed_url.scheme.lower() == 'imaps'
    
    if parsed_url.hostname:
        account['host'] = parsed_url.hostname

    if parsed_url.port:
        account['port'] = parsed_url.port
    if parsed_url.username:
        account['username'] = urllib.parse.unquote(parsed_url.username)
    if parsed_url.password:
        account['password'] = urllib.parse.unquote(parsed_url.password)
    
    # prefill account name, if none was provided (by config.cfg) in case of calling it from commandline. can be overwritten by the query param 'name'
    account['name'] = create_account_name(account, name)
    if name:
        account['name'] = name
        
    else:
        if (account['username']):
            account['name'] = account['username']
            
        if (account['host']):
            account['name'] += '@' + account['host']

    if parsed_url.path != '':
        account['remote_folder'] = parsed_url.path.lstrip('/').rstrip('/')

    if parsed_url.query != '':
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # merge query params into account
        for key, value in query_params.items():

            if key == 'remote_folder':
                if account['remote_folder'] is not None:
                    account['remote_folder'] += ',' + value[0]
                else:
                    account['remote_folder'] = value[0]
            
            elif key == 'ssl':
                account['ssl'] = value[0].lower() == 'true'
            
            # merge all others params, to be able to overwrite username, password, ... and future account options
            else:
                account[key] = value[0] if len(value) == 1 else value

    return account


def create_account_name(account, name = None):
    """
    If name is given, return it, otherwise return a name made up
    of the username and host parts of the account.
    """
    
    if name:
        return name
        
    else:
        name = ''

        if (account['username']):
            name = account['username']
            
        if (account['host']):
            name += '@' + account['host']

        return name



def account_to_dsn(account):
    """
    Generate a DSN string from an account
    """

    return 'imap{}://{}:{}@{}:{}/{}'.format('s' if account['ssl'] else '', urllib.parse.quote(account['username']), urllib.parse.quote(account['password']), account['host'], account['port'], urllib.parse.quote(account['remote_folder']))

def input_dsn(options):
    """
    Asks the user to input the account details and print the full DSN.
    If test_only is True, it will test the connection and optionally print the found folders.
    """

    try:
        account = {
            'host': input('Host: ').strip(),
            'port': int(input('Port [993]: ').strip() or '993'),
            'ssl': input('Use SSL? [Y/n]: ').lower() != 'n',
            'username': input('Username: ').strip(),
            'password': input('Password: ').strip(),

            'remote_folder': input('Remote folder (use __ALL__ to fetch all) [INBOX]: ').strip() or 'INBOX',
        }
        account['name'] = create_account_name(account)
        options['accounts'] = [account]

        print('\nDSN:\n {}'.format(account_to_dsn(account)))

    except Exception as e:
        errorHandler(e, 'Input DSN Error')

    return options