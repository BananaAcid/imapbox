#!/usr/bin/env python
# -*- coding:utf-8 -*-


from utilities import errorHandler
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

