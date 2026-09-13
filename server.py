#!/usr/bin/env python
# -*- coding:utf-8 -*-


from utilities import errorHandler
from hooks import dispatch_status, make_status_item, join_hooks
import threading
#from imapbox import do_accounts
import croniter
import datetime

exit_flag = threading.Event()
def start_server(options, do_accounts):
    """
    Starts a server, where the cron is checked every minute and the accounts are processed

    help: https://crontab.guru/
    """

    # test cron expression
    try:
        croniter.croniter(options['server'])
    except Exception as e:
        errorHandler(e, 'Invalid CRON expression')
    



    print("Started server")
    print("Cron: " + options['server'])

    # signal that the server is ready, before any account is checked
    dispatch_status(options['hooks'], ['serverstart'], make_status_item('serverstart', None, options['local_folder'], []))
    join_hooks()

    cron = croniter.croniter(options['server'], datetime.datetime.now())
    next_cron = cron.get_next(datetime.datetime)
    print("Waiting for first cron: " + str(next_cron))

    while not exit_flag.wait(60.0):

        if next_cron <= datetime.datetime.now():

            # do action
            do_accounts(options)

            # update next cron
            next_cron = cron.get_next(datetime.datetime)
            print("Done. Waiting for next cron: " + str(next_cron))

