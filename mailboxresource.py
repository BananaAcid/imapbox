#!/usr/bin/env python
# -*- coding:utf-8 -*-

from __future__ import print_function

import imaplib, email
import re
import os
from message import Message
import datetime
from utilities import errorHandler, imaputf7encode, createReliableFoldername, createReliableMessageId, hasTTY
from hooks import dispatch, make_mail_item, append_buffer

MAX_RETRIES = 5

class MailboxClient:
    """Operations on a mailbox"""

    def __init__(self, host, port, username, password, remote_folder, ssl):

        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.remote_folder = remote_folder
        self.ssl = ssl
        self.selected_folder = False

        self.connect_to_imap()

    def connect_to_imap(self):
        retries = 0
        while retries < MAX_RETRIES:
            try:
                if not self.ssl:
                    self.mailbox = imaplib.IMAP4(self.host, self.port)
                else:
                    self.mailbox = imaplib.IMAP4_SSL(self.host, self.port)
                self.mailbox.login(self.username, self.password)
                typ, data = self.mailbox.select(self.remote_folder, readonly=True)
                if typ != 'OK':
                    # Handle case where Exchange/Outlook uses '.' path separator when
                    # reporting subfolders. Adjust to use '/' on remote.
                    adjust_remote_folder = re.sub(r'\.', '/', self.remote_folder)
                    typ, data = self.mailbox.select(adjust_remote_folder, readonly=True)
                    if typ != 'OK':
                        errorHandler(self.remote_folder, 'MailboxClient: Could not select remote folder', exitCode=None)
                        self.selected_folder = False
                    else:
                        self.selected_folder = True   
                else:
                    self.selected_folder = True
                break
            except ConnectionResetError as e:
                errorHandler(None, f"MailboxClient: Connection error: {e}. Will retry ...", exitCode=None)
                retries += 1
            except Exception as e:
                errorHandler(None, f"MailboxClient: The following error happened: {e}. Will NOT retry.")

        if retries == MAX_RETRIES:
            errorHandler(None, 'MailboxClient: Maximum retries reached. Exiting.')

    def search_emails(self, criterion, batch_size=5000):
        all_uids = []
        last_num = 0
        loop = True

        while loop:
            typ, data = self.mailbox.search(None, criterion, f'{last_num+1}:{last_num + batch_size}')
            if typ != 'OK':
                # fallback if range is not supported
                errorHandler(None, f"Warning: Batch range might not be supported by IMAP server. Retrying without ...", exitCode=None)
                loop = False
                typ, data = self.mailbox.search(None, criterion)

                if typ != 'OK':
                    raise imaplib.IMAP4.error(f"Error on searching emails ({criterion}: \"{typ}\" => {data}).")

            if data and len(data) > 0 and data[0]: 
                batch_uids = data[0].split()
            else:
                batch_uids = []

            if not batch_uids:
                break

            all_uids.extend(batch_uids)
            last_num = last_num + batch_size

        return all_uids
    
    def copy_emails(self, days, local_folder, wkhtmltopdf, hooks=None):

        n_saved = 0
        n_exists = 0

        self.local_folder = local_folder
        self.wkhtmltopdf = wkhtmltopdf
        self.hooks = hooks or {}
        criterion = 'ALL'

        if days:
            date = (datetime.date.today() - datetime.timedelta(days)).strftime("%d-%b-%Y")
            criterion = '(SENTSINCE {date})'.format(date=date)

        uids = self.search_emails(criterion)
        if uids is not None and uids is not []:
            print("- Copying emails ...")
            total = len(uids)
            for idx, num in enumerate(uids):
                fetch_retries = 0
                while fetch_retries < MAX_RETRIES:
                    try:
                        typ, data = self.mailbox.fetch(num, '(BODY.PEEK[])')

                        if hasTTY():
                            print('\r{0:.2f}% '.format(idx*100/total), end='')

                        new_directory = self.saveEmail(data)
                        if new_directory:
                            n_saved += 1
                            dispatch(self.hooks, 'newmail', make_mail_item('newmail', self.account, new_directory, self.last_metadata))
                            append_buffer(self.hookbuffer, self.account_name, new_directory)
                        elif self.last_error:
                            dispatch(self.hooks, 'error', make_mail_item('error', self.account, self.last_directory, self.last_metadata, success=False, error={'error': self.last_error}))
                        else:
                            n_exists += 1
                        break
                    except ConnectionResetError as e:
                        errorHandler(None, f"Connection error while fetching email: {e}. Retrying ...", exitCode=None)
                        self.connect_to_imap()
                        fetch_retries += 1
                    except imaplib.IMAP4.abort as e:
                        errorHandler(None, f"Abort error while fetching email: {e}. Skipping ...", exitCode=None)
                        self.connect_to_imap()
                        break
                    except Exception as e:
                        errorHandler(None, f"Error while fetching email: {e}. Skipping ...", exitCode=None)
                        break
                if fetch_retries == MAX_RETRIES:
                    errorHandler(None, '\nMaximum retries reached. Exiting.', 1)
                    
            # print("\r- ... done")
        return (n_saved, n_exists)

    def cleanup(self):
        self.mailbox.close()
        self.mailbox.logout()


    def getEmailFolder(self, msg, data):
        # 255is the max filename length on all systems
        foldername = createReliableFoldername(msg['Message-Id'], data)

        year = 'None'
        if msg['Date']:
            match = re.search(r'\d{1,2}\s\w{3}\s(\d{4})', msg['Date'])
            if match:
                year = match.group(1)

        return os.path.join(self.local_folder, year, foldername)


    def saveEmail(self, data):
        new_directory = None
        self.last_error = None
        self.last_directory = None
        self.last_metadata = None
        for response_part in data:
            if isinstance(response_part, tuple):
                msg = ""
                # Handle Python version differences:
                # Python 2 imaplib returns bytearray, Python 3 imaplib
                # returns str.
                if isinstance(response_part[1], str):
                    msg = email.message_from_string(response_part[1])
                else:
                    try:
                        msg = email.message_from_string(response_part[1].decode("utf-8"))
                    except:
                        # print("couldn't decode message with utf-8 - trying 'ISO-8859-1'")
                        msg = email.message_from_string(response_part[1].decode("ISO-8859-1"))
                
                msg['Message-Id'] = message_id = createReliableMessageId(msg['Message-Id'], data)
                directory = self.getEmailFolder(msg, data[0][1])

                # we might retrying it, so check if directory exists and continue
                if not os.path.exists(directory):
                    os.makedirs(directory)

                try:
                    message = Message(directory, msg, message_id)
                    if message.checkIfExists(): continue
                    message.createRawFile(data[0][1])
                    message.createMetaFile()
                    self.last_metadata = message.metadata
                    message.extractAttachments()

                    if self.wkhtmltopdf:
                        message.createPdfFile(self.wkhtmltopdf)

                    new_directory = directory

                except Exception as e:
                    # ex: Unsupported charset on decode
                    self.last_error = str(e)
                    self.last_directory = directory
                    errorHandler(e, f'\rError: MailboxClient.saveEmail() failed for {directory}', exitCode=None)

        return new_directory


def save_emails(account, options, local_folder=None):
    mailbox = MailboxClient(account['host'], account['port'], account['username'], account['password'], account['remote_folder'], account['ssl'])
    if mailbox.selected_folder is True:
        if local_folder is None:
            local_folder = options['local_folder']
        mailbox.account = account
        mailbox.account_name = account['name']
        mailbox.hookbuffer = options.get('_hookbuffer', []) or []
        stats = mailbox.copy_emails(options['days'], local_folder, options['wkhtmltopdf'], options.get('hooks'))
        mailbox.cleanup()
        if stats[0] == 0 and stats[1] == 0:
            print('\r- Done. Is empty')
        else:
            print('\r- Done. {} emails created, {} emails already exist'.format(stats[0], stats[1]))


def get_folder_fist(account):
    if not account['ssl']:
        mailbox = imaplib.IMAP4(account['host'], account['port'])
    else:
        mailbox = imaplib.IMAP4_SSL(account['host'], account['port'])
    mailbox.login(account['username'], account['password'])
    folder_list = mailbox.list()[1]
    mailbox.logout()
    return folder_list


def get_folders(account):
    folders = []
    exclude_folder = []

    if account['exclude_folder']: 
        exclude_folder = [imaputf7encode(folder.strip()) for folder in account['exclude_folder'].split(',')]
    
    for folder_entry in get_folder_fist(account):    
        folder_name = folder_entry.decode().replace('/', '.').split(' "." ')[1]
        if folder_name.replace('"', '') not in exclude_folder:
            folders.append(folder_name)
    
    # Remove Gmail parent folder from array otherwise the script fails:
    if '"[Gmail]"' in folders: folders.remove('"[Gmail]"')
    # Remove Gmail "All Mail" folder which just duplicates emails:
    if '"[Gmail].All Mail"' in folders: folders.remove('"[Gmail].All Mail"')
    return folders
