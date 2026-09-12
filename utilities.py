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


import re
import hashlib

def createReliableMessageId(message_id, data):
    if message_id and len(message_id.strip()) > 10:
        msg_id_safe = re.sub(r'[^a-zA-Z0-9_\-\.() ]+', '', message_id.strip())
    else:
        try:
            if type(data) is list:
                msg_id_safe = hashlib.sha224(data[1]).hexdigest()
            else:
                msg_id_safe = hashlib.sha224(data).hexdigest()

        except Exception as e:
            errorHandler(e, '- FAILED: Creating message ID', exitCode=None)
            raise e

    return msg_id_safe

def createReliableFoldername(message_id, data):
    # 255 is the max filename length on all systems
    if message_id and len(message_id.strip()) < 255:
        foldername = re.sub(r'[^a-zA-Z0-9_\-\.() ]+', '', message_id.strip())
    else:
        try:
            if type(data) is list:
                foldername = hashlib.sha224(data[1]).hexdigest()
            else:
                foldername = hashlib.sha224(data).hexdigest()

        except Exception as e:
            errorHandler(e, '- FAILED: Creating folder name', exitCode=None)
            raise e

    return foldername

def hasTTY():
    return sys.stdin and sys.stdin.isatty()



import configparser
#import os

class DollarInterpolation(configparser.ExtendedInterpolation):
    """ExtendedInterpolation for the imapbox config.

    - `${name}` resolves `name` from the unnamed section
      (`allow_unnamed_section=True`), i.e. the key=value block before the
      first `[section]` header.
    - `${section:name}` resolves `name` from the given `section`.
    - `${env:name}` resolves `name` from an `[env]` section if present,
      otherwise from the environment (`os.environ`).
    - Every other `$` is kept literally: `$$` stays `$$`, and `$${...}`
      writes a literal `${...}` instead of being interpolated.
    """

    def _interpolate_some(self, parser, option, accum, rest, section, map,
                          depth):
        rawval = parser.get(section, option, raw=True, fallback=rest)
        if depth > configparser.MAX_INTERPOLATION_DEPTH:
            raise configparser.InterpolationDepthError(option, section, rawval)
        while rest:
            p = rest.find("$")
            if p < 0:
                accum.append(rest)
                return
            if p > 0:
                accum.append(rest[:p])
                rest = rest[p:]
            # p is no longer used
            c = rest[1:2]
            if c == "$":
                if rest[2:3] == "{":
                    accum.append("${")
                    rest = rest[3:]
                else:
                    accum.append("$$")
                    rest = rest[2:]
            elif c == "{":
                m = self._KEYCRE.match(rest)
                if m is None:
                    raise configparser.InterpolationSyntaxError(
                        option, section,
                        "bad interpolation variable reference %r" % rest)
                path = m.group(1).split(':')
                rest = rest[m.end():]
                sect = section
                opt = option
                try:
                    if len(path) == 1:
                        opt = parser.optionxform(path[0])
                        v = parser.get(configparser.UNNAMED_SECTION, opt,
                                       raw=True)
                    elif len(path) == 2:
                        sect = path[0]
                        opt = parser.optionxform(path[1])
                        if sect == 'env':
                            if parser.has_option('env', opt):
                                v = parser.get('env', opt, raw=True)
                            elif path[1] in os.environ:
                                v = os.environ[path[1]]
                            elif path[1].upper() in os.environ:
                                v = os.environ[path[1].upper()]
                            else:
                                raise configparser.InterpolationMissingOptionError(
                                    option, section, rawval,
                                    ":".join(path))
                        else:
                            v = parser.get(sect, opt, raw=True)
                    else:
                        raise configparser.InterpolationSyntaxError(
                            option, section,
                            "More than one ':' found: %r" % (rest,))
                except (KeyError, configparser.NoSectionError,
                        configparser.NoOptionError):
                    raise configparser.InterpolationMissingOptionError(
                        option, section, rawval, ":".join(path)) from None
                if v is None:
                    continue
                if "$" in v:
                    self._interpolate_some(parser, opt, accum, v, sect,
                                           dict(parser.items(sect, raw=True)),
                                           depth + 1)
                else:
                    accum.append(v)
            else:
                accum.append("$")
                rest = rest[1:]
