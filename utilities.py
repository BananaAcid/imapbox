#!/usr/bin/env python
#-*- coding:utf-8 -*-


import os
import sys

# if exitCode is None, do not exit, just show the error
def errorHandler(e, caption, exitCode=1):
    if hasattr(e, 'strerror'):
        msg = e.strerror
    else:
        msg = e
    
    if e is not None:
        print('\x1b[31;20m{}:'.format(caption), msg, '\x1b[0m', file=sys.stderr)
    else:
        print('\x1b[31;20m{}\x1b[0m'.format(caption), file=sys.stderr)

    if exitCode is not None:
        sys.exit(exitCode)


def get_version(caption = 'v'):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'VERSION'), 'r') as version_file:
        return caption + version_file.read().strip()