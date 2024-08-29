#!/usr/bin/env python
#-*- coding:utf-8 -*-


from mailboxresource import save_emails, get_folders
from dsn import get_account, input_dsn
import argparse
import configparser
import os
import sys
import getpass
from utilities import errorHandler, get_version, is_docker
from search import do_search


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
        'search_filter': None,
        'input_dsn': False,
        'accounts': []
    }

    # set default folder, if within a docker container
    if is_docker():
        options['local_folder'] = '/var/imapbox'

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
            if config.get('imapbox', 'test_only') == 'folders':
                options['test_only'] = 'folders'
            else:
                options['test_only'] = config.getboolean('imapbox', 'test_only')

    if args.specific_dsn:
        for dsn in args.specific_dsn:
            try:
                account = get_account(dsn)
                if (None == account['host'] or None == account['username'] or None == account['password']):
                    raise ValueError('host / username or password not set')
                
            except Exception as e:
                errorHandler(e, 'Invalid DSN (' + dsn + ')')
            
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
                try:
                    prompt=('Password for ' + account['username'] + ':' + account['host'] + ': ')
                    account['password'] = getpass.getpass(prompt=prompt)
                except Exception as e:
                    errorHandler(e, 'No password set for account {}. Could not ask for password. (no CLI?)'.format(section), exitCode=None)

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
        if args.test_only == 'folders':
            options['test_only'] = 'folders'
        else:
            options['test_only'] = True

    if (args.search_filter):
        options['search_filter'] = args.search_filter

    if (args.input_dsn):
        options['input_dsn'] = args.input_dsn

    if (args.show_version):
        print(get_version())
        sys.exit(0)
    
    return options




def main():
    argparser = argparse.ArgumentParser(description='Dump a IMAP folder into .eml, .txt and .html files, and optionally convert them into PDFs. \n\n' + get_version('version: '), formatter_class=argparse.RawTextHelpFormatter)
    argparser.add_argument('-l', '--local-folder', dest='local_folder', metavar='PATH', help='Local folder where to create the email folders')
    argparser.add_argument('-d', '--days', dest='days', metavar='NUMBER', help='Number of days back to get in the IMAP account', type=int)
    argparser.add_argument('-n', '--dsn', dest='specific_dsn', metavar='DSN', help='Use a specific DSN as account like imap[s]://username:password@host:port/folder,folder', action='append')
    argparser.add_argument('-a', '--account', dest='specific_account', metavar='ACCOUNT', help='Select a specific account section from the config to backup')
    argparser.add_argument('-f', '--folders', dest='specific_folders', help='Backup into specific account subfolders', action='store_true')
    argparser.add_argument('-w', '--wkhtmltopdf', dest='wkhtmltopdf', metavar='PATH', help='The location of the wkhtmltopdf binary')
    argparser.add_argument('-t', '--test', dest='test_only', nargs='?', const=True, default=False, metavar='"folders"', help='Only a connection and folder retrival test will be performed, adding the optional "folders" as parameter will also show the found folders')
    argparser.add_argument('-c', '--config', dest='specific_config', metavar='PATH', help='Path to a config file to use')
    argparser.add_argument('-v', '--version', dest='show_version', help='Show the current version', action='store_true')
    argparser.add_argument('-s', '--search', dest='search_filter', metavar='FILTER', help='Search in backuped emails (Filter: `Keyword,\"fnmatch syntax\"`)')
    argparser.add_argument('-i', '--input-dsn', dest='input_dsn', help='Helper to generate a DSN string, can be used with --test', action='store_true')
    args = argparser.parse_args()
    options = load_configuration(args)
    rootDir = options['local_folder']

    if options['search_filter']:
        do_search(options)

    if options['input_dsn']:
        options = input_dsn(options)
        if not options['test_only']:
            sys.exit(0)


    if not options['accounts']:
        argparser.print_help()

    for account in options['accounts']:

        print('{}/{} (on {})'.format(account['name'], account['remote_folder'], account['host']))

        if options['test_only']:
            try:
                folders = get_folders(account)
                if options['test_only'] == 'folders':
                    print(' - Folders:', ', '.join(folders) )
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
                folders = get_folders(account)
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
