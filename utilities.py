#!/usr/bin/env python
#-*- coding:utf-8 -*-


import configparser
import os
import sys
from pathlib import Path

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


def is_docker():
    cgroup = Path('/proc/self/cgroup')
    return Path('/.dockerenv').is_file() or cgroup.is_file() and 'docker' in cgroup.read_text()


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
