#!/usr/bin/env python
#-*- coding:utf-8 -*-

from mailboxresource import save_emails, get_folder_fist, get_account
import argparse
from six.moves import configparser
import os
import sys
import getpass
from utilities import errorHandler


def load_configuration(args):
    config = configparser.ConfigParser(allow_no_value=True)
    if (args.specific_config):
        locations = args.specific_config
    else:
        locations = ['./config.cfg', '/etc/imapbox/config.cfg', os.path.expanduser('~/.config/imapbox/config.cfg')]
    config.read(locations)

    options = {
        'days': None,
        'local_folder': '.',
        'wkhtmltopdf': None,
        'specific_folders': False,
        'test_only': False,
        'accounts': []
    }

    if (config.has_section('imapbox')):
        if config.has_option('imapbox', 'days'):
            options['days'] = config.getint('imapbox', 'days')

        if config.has_option('imapbox', 'local_folder'):
            options['local_folder'] = os.path.expanduser(config.get('imapbox', 'local_folder'))

        if config.has_option('imapbox', 'wkhtmltopdf'):
            options['wkhtmltopdf'] = os.path.expanduser(config.get('imapbox', 'wkhtmltopdf'))

        if config.has_option('imapbox', 'specific_folders'):
            options['specific_folders'] = config.getboolean('imapbox', 'specific_folders')

        if config.has_option('imapbox', 'test_only'):
            options['test_only'] = config.getboolean('imapbox', 'test_only')

    if args.specific_dsn:
        try:
            account = get_account(args.specific_dsn)
            if (None == account['host'] or None == account['username'] or None == account['password']):
                raise ValueError('host / username or password not set')
            
        except Exception as e:
            errorHandler(e, 'Invalid DSN (' + args.specific_dsn + ')')
        
        options['accounts'].append(account)

    else:
        for section in config.sections():

            if ('imapbox' == section):
                continue

            if (args.specific_account and (args.specific_account != section)):
                continue

            account = {
                'name': section,
                'remote_folder': 'INBOX',
                'username': None,
                'password': None,
                'host': None,
                'port': 993,
                'ssl': False
            }

            if config.has_option(section, 'dsn'):
                account = get_account(config.get(section, 'dsn'), account['name'])

            if config.has_option(section, 'host'):
                account['host'] = config.get(section, 'host')

            if config.has_option(section, 'port'):
                account['port'] = config.get(section, 'port')

            if config.has_option(section, 'username'):
                account['username'] = config.get(section, 'username')

            if config.has_option(section, 'password'):
                account['password'] = config.get(section, 'password')
            elif not account['password']:
                prompt=('Password for ' + account['username'] + ':' + account['host'] + ': ')
                account['password'] = getpass.getpass(prompt=prompt)

            if config.has_option(section, 'ssl'):
                if config.get(section, 'ssl').lower() == "true":
                    account['ssl'] = True

            if config.has_option(section, 'remote_folder'):
                account['remote_folder'] = config.get(section, 'remote_folder')

            if (None == account['host'] or None == account['username'] or None == account['password']):
                errorHandler(section, 'Invalid account')
                continue

            options['accounts'].append(account)

    if (args.local_folder):
        options['local_folder'] = args.local_folder

    if (args.days):
        options['days'] = args.days

    if (args.wkhtmltopdf):
        options['wkhtmltopdf'] = args.wkhtmltopdf

    if (args.specific_folders):
        options['specific_folders'] = True

    if (args.test_only):
        options['test_only'] = True

    if (args.show_version):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'VERSION'), 'r') as version_file:
            print('v' + version_file.read())
        sys.exit(0)
    
    return options




def main():
    argparser = argparse.ArgumentParser(description="Dump a IMAP folder into .eml files")
    argparser.add_argument('-l', '--local-folder', dest='local_folder', help="Local folder where to create the email folders")
    argparser.add_argument('-d', '--days', dest='days', help="Number of days back to get in the IMAP account", type=int)
    argparser.add_argument('-n', '--dsn', dest='specific_dsn', help="Use a specific DSN as account")
    argparser.add_argument('-a', '--account', dest='specific_account', help="Select a specific account to backup")
    argparser.add_argument('-f', '--folders', dest='specific_folders', help="Backup into specific account subfolders", action='store_true')
    argparser.add_argument('-w', '--wkhtmltopdf', dest='wkhtmltopdf', help="The location of the wkhtmltopdf binary")
    argparser.add_argument('-t', '--test', dest='test_only', help="Only a connection and folder retrival test will be performed", action='store_true')
    argparser.add_argument('-c', '--config', dest='specific_config', help="Path to a config file to use")
    argparser.add_argument('-v', '--version', dest='show_version', help="Show the current version", action="store_true")
    args = argparser.parse_args()
    options = load_configuration(args)
    rootDir = options['local_folder']

    if not options['accounts']:
        argparser.print_help()

    for account in options['accounts']:

        print('{}/{} (on {})'.format(account['name'], account['remote_folder'], account['host']))

        if options['test_only']:
            try:
                get_folder_fist(account)
                print(' - SUCCESS: Login and folder retrival')
            except:
                errorHandler(None, ' - FAILED: Login and folder retrival', exitCode=None)
            continue

        if options['specific_folders']:
            basedir = os.path.join(rootDir, account['name'])
        else:
            basedir = rootDir

        try:
            if account['remote_folder'] == "__ALL__":
                folders = []
                for folder_entry in get_folder_fist(account):
                    folders.append(folder_entry.decode().replace("/",".").split(' "." ')[1])
                # Remove Gmail parent folder from array otherwise the script fails:
                if '"[Gmail]"' in folders: folders.remove('"[Gmail]"')
                # Remove Gmail "All Mail" folder which just duplicates emails:
                if '"[Gmail].All Mail"' in folders: folders.remove('"[Gmail].All Mail"')
            else:
                folders = str.split(account['remote_folder'], ',')
            for folder_entry in folders:
                print("Saving folder: " + folder_entry) 
                account['remote_folder'] = folder_entry
                options['local_folder'] = os.path.join(basedir, folder_entry.replace('"', ''))
                save_emails(account, options)
        except Exception as e:
            errorHandler(e, ' - FAILED')


if __name__ == '__main__':
    main()
