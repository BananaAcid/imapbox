#!/usr/bin/env python
# -*- coding:utf-8 -*-


import sys

# Print an error message
#
# Note: if e is NOT None, the message should not end with a dot, since a ':' will be appended
#
# e: if e is None, show no error details
# caption: must always exist (is used from code to show a readable message)
# exitCode: if exitCode is None, do not exit, just show the error
def errorHandler(e, caption, exitCode=1):
    if hasattr(e, 'strerror'):
        msg = e.strerror
    else:
        msg = e
    
    if e is not None:
        # show error details, and in red
        print('\x1b[31;20m{}:'.format(caption), msg, '\x1b[0m', file=sys.stderr)
    else:
        # show no error details, and in cyan
        print('\x1b[36;20m{}\x1b[0m'.format(caption), file=sys.stderr)

    if exitCode is not None:
        sys.exit(exitCode)


import os
from pathlib import Path

def get_version(caption = 'v'):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'VERSION'), 'r') as version_file:
        return caption + version_file.read().strip()


def is_docker():
    cgroup = Path('/proc/self/cgroup')
    return Path('/.dockerenv').is_file() or cgroup.is_file() and 'docker' in cgroup.read_text()



import base64
# https://stackoverflow.com/questions/12776679/imap-folder-path-encoding-imap-utf-7-for-python/45787169#45787169

def b64padanddecode(b):
    """Decode unpadded base64 data"""
    b+=(-len(b)%4)*'=' #base64 padding (if adds '===', no valid padding anyway)
    return base64.b64decode(b,altchars='+,',validate=True).decode('utf-16-be')

def imaputf7decode(s):
    """Decode a string encoded according to RFC2060 aka IMAP UTF7.
    Minimal validation of input, only works with trusted data"""
    lst=s.split('&')
    out=lst[0]
    for e in lst[1:]:
        u,a=e.split('-',1) #u: utf16 between & and 1st -, a: ASCII chars folowing it
        if u=='' : out+='&'
        else: out+=b64padanddecode(u)
        out+=a
    return out

def imaputf7encode(s):
    """"Encode a string into RFC2060 aka IMAP UTF7"""
    s=s.replace('&','&-')
    iters=iter(s)
    unipart=out=''
    for c in s:
        if 0x20<=ord(c)<=0x7f :
            if unipart!='' : 
                out+='&'+base64.b64encode(unipart.encode('utf-16-be')).decode('ascii').rstrip('=')+'-'
                unipart=''
            out+=c
        else : unipart+=c
    if unipart!='' : 
        out+='&'+base64.b64encode(unipart.encode('utf-16-be')).decode('ascii').rstrip('=')+'-'
    return out    