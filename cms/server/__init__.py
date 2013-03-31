#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012 Luca Wehrstedt <luca.wehrstedt@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Random utilities for web servers and page templates.

"""

import os
import time

import tarfile
import zipfile

from functools import wraps
from tornado.web import RequestHandler
import tornado.locale

from cms import logger
from cms.db.FileCacher import FileCacher
from cmscommon.DateTime import make_datetime, utc


def actual_phase_required(*actual_phases):
    """Return decorator that accepts requests iff contest is in the given phase

    """
    def decorator(func):
        @wraps(func)
        def wrapped(self, *args, **kwargs):
            if self.r_params["actual_phase"] not in actual_phases:
                # TODO maybe return some error code?
                self.redirect("/")
            else:
                return func(self, *args, **kwargs)
        return wrapped
    return decorator


def extract_archive(temp_name, original_filename):
    """Obtain a list of files inside the specified archive.

    Returns a list of the files inside the archive located in
    temp_name, using original_filename to guess the type of the
    archive.

    """
    file_list = []
    if original_filename.endswith(".zip"):
        try:
            zip_object = zipfile.ZipFile(temp_name, "r")
            for item in zip_object.infolist():
                file_list.append({
                    "filename": item.filename,
                    "body": zip_object.read(item)})
        except Exception as error:
            logger.warning("Exception while extracting zip file `%s'. %r" %
                           (original_filename, error))
            return None
    elif original_filename.endswith(".tar.gz") \
            or original_filename.endswith(".tar.bz2") \
            or original_filename.endswith(".tar"):
        try:
            tar_object = tarfile.open(name=temp_name)
            for item in tar_object.getmembers():
                if item.isfile():
                    file_list.append({
                        "filename": item.name,
                        "body": tar_object.extractfile(item).read()})
        except tarfile.TarError:
            logger.warning("Exception while extracting tar file `%s'. %r" %
                           (original_filename, error))
            return None
        except IOError:
            return None
    else:
        logger.warning("Compressed file `%s' not recognized."
                       % original_filename)
        return None
    return file_list


UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
DIMS = list(1024 ** x for x in xrange(9))


def format_size(n):
    """Format the given number of bytes

    Return a size, given as a number of bytes, properly formatted
    using the most appropriate size unit. Always use three
    significant digits.

    """
    if n == 0:
        return '0 B'

    # Use the last unit that's smaller than n
    unit = map(lambda x: n >= x, DIMS).index(False) - 1
    n = float(n) / DIMS[unit]

    if n < 10:
        return "%g %s" % (round(n, 2), UNITS[unit])
    elif n < 100:
        return "%g %s" % (round(n, 1), UNITS[unit])
    else:
        return "%g %s" % (round(n, 0), UNITS[unit])


def format_date(dt, timezone, locale=None):
    """Return the date of dt formatted according to the given locale

    dt (datetime): a datetime object
    timezone (subclass of tzinfo): the timezone the output should be in
    return (str): the date of dt, formatted using the given locale

    """
    if locale is None:
        locale = tornado.locale.get()

    _ = locale.translate

    # convert dt from UTC to local time
    dt = dt.replace(tzinfo=utc).astimezone(timezone)

    return dt.strftime(_("%Y-%m-%d"))


def format_time(dt, timezone, locale=None):
    """Return the time of dt formatted according to the given locale

    dt (datetime): a datetime object
    timezone (subclass of tzinfo): the timezone the output should be in
    return (str): the time of dt, formatted using the given locale

    """
    if locale is None:
        locale = tornado.locale.get()

    _ = locale.translate

    # convert dt from UTC to local time
    dt = dt.replace(tzinfo=utc).astimezone(timezone)

    return dt.strftime(_("%H:%M:%S"))


def format_datetime(dt, timezone, locale=None):
    """Return the date and time of dt formatted according to the given locale

    dt (datetime): a datetime object
    timezone (subclass of tzinfo): the timezone the output should be in
    return (str): the date and time of dt, formatted using the given locale

    """
    if locale is None:
        locale = tornado.locale.get()

    _ = locale.translate

    # convert dt from UTC to local time
    dt = dt.replace(tzinfo=utc).astimezone(timezone)

    return dt.strftime(_("%Y-%m-%d %H:%M:%S"))


def format_datetime_smart(dt, timezone, locale=None):
    """Return dt formatted as 'date & time' or, if date is today, just 'time'

    dt (datetime): a datetime object
    timezone (subclass of tzinfo): the timezone the output should be in
    return (str): the [date and] time of dt, formatted using the given locale

    """
    if locale is None:
        locale = tornado.locale.get()

    _ = locale.translate

    # convert dt and 'now' from UTC to local time
    dt = dt.replace(tzinfo=utc).astimezone(timezone)
    now = make_datetime().replace(tzinfo=utc).astimezone(timezone)

    if dt.date() == now.date():
        return dt.strftime(_("%H:%M:%S"))
    else:
        return dt.strftime(_("%Y-%m-%d %H:%M:%S"))


def get_score_class(score, max_score):
    """Return a CSS class to visually represent the score/max_score

    score (float): the score of the submission.
    max_score (float): maximum score.
    return (str): class name

    """
    if score <= 0:
        return "score_0"
    elif score >= max_score:
        return "score_100"
    else:
        return "score_0_100"


# Dummy function to mark strings for translation
def _(*args, **kwargs):
    pass

_("%d second", "%d seconds", 0)
_("%d minute", "%d minutes", 0)
_("%d hour", "%d hours", 0)
_("%d day", "%d days", 0)


def format_amount_of_time(seconds, precision=2, locale=None):
    """Return the number of seconds formatted 'X days, Y hours, ...'

    The time units that will be used are days, hours, minutes, seconds.
    Only the first "precision" units will be output. If they're not
    enough, a "more than ..." will be prefixed (non-positive precision
    means infinite).

    seconds (int): the length of the amount of time in seconds.
    precision (int): see above
    locale (tornado.locale.Locale): the locale to be used.

    return (string): seconds formatted as above.

    """
    seconds = abs(int(seconds))

    if locale is None:
        locale = tornado.locale.get()

    _ = locale.translate

    if seconds == 0:
        return _("%d second", "%d seconds", 0) % 0

    units = [(("%d day", "%d days"), 60 * 60 * 24),
             (("%d hour", "%d hours"), 60 * 60),
             (("%d minute", "%d minutes"), 60),
             (("%d second", "%d seconds"), 1)]

    ret = list()
    counter = 0

    for name, length in units:
        tmp = seconds // length
        seconds %= length
        if tmp == 0:
            continue
        else:
            ret.append(_(name[0], name[1], tmp) % tmp)
        counter += 1
        if counter == precision:
            break

    if len(ret) == 1:
        ret = ret[0]
    else:
        ret = _("%s and %s") % (", ".join(ret[:-1]), ret[-1])

    if seconds > 0:
        ret = _("more than %s") % ret

    return ret


def format_token_rules(tokens, t_type=None, locale=None):
    """Return a human-readable string describing the given token rules

    tokens (dict): all the token rules (as seen in Task or Contest),
                   without the "token_" prefix.
    t_type (str): the type of tokens the string should refer to (can be
                  "contest" to mean contest-tokens, "task" to mean
                  task-tokens, any other value to mean normal tokens).
    locale (tornado.locale.Locale): the locale to be used.

    return (string): localized string describing the rules.

    """
    if locale is None:
        locale = tornado.locale.get()

    _ = locale.translate

    if t_type == "contest":
        tokens["type_s"] = _("contest-token")
        tokens["type_pl"] = _("contest-tokens")
    elif t_type == "task":
        tokens["type_s"] = _("task-token")
        tokens["type_pl"] = _("task-tokens")
    else:
        tokens["type_s"] = _("token")
        tokens["type_pl"] = _("tokens")

    tokens["min_interval"] = int(tokens["min_interval"].total_seconds())
    tokens["gen_time"] = int(tokens["gen_time"].total_seconds() / 60)

    result = ""

    if tokens['initial'] is None:
        # note: we are sure that this text will only be displayed in task
        # pages because if tokens are disabled for the whole contest they
        # don't appear anywhere in CWS
        result += _("You don't have %(type_pl)s available for this task.") % tokens
    elif tokens['gen_time'] == 0 and tokens['gen_number'] > 0:
        result += _("You have infinite %(type_pl)s.") % tokens

        result += " "

        if tokens['min_interval'] > 0:
            result += _("You can use a %(type_s)s every second.",
                        "You can use a %(type_s)s every %(min_interval)d seconds.",
                        tokens['min_interval']) % tokens
        else:
            result += _("You have no limitations on how you use them.") % tokens
    else:
        if tokens['initial'] == 0:
            result += _("You start with no %(type_pl)s.") % tokens
        else:
            result += _("You start with one %(type_s)s.",
                        "You start with %(initial)d %(type_pl)s.",
                        tokens['initial'] == 1) % tokens

        result += " "

        if tokens['gen_time'] > 0 and tokens['gen_number'] > 0:
            result += _("Every minute ",
                        "Every %(gen_time)d minutes ",
                        tokens['gen_time']) % tokens
            if tokens['max'] is not None:
                result += _("you get another %(type_s)s, ",
                            "you get %(gen_number)d other %(type_pl)s, ",
                            tokens['gen_number']) % tokens
                result += _("up to a maximum of one %(type_s)s.",
                            "up to a maximum of %(max)d %(type_pl)s.",
                            tokens['max']) % tokens
            else:
                result += _("you get another %(type_s)s.",
                            "you get %(gen_number)d other %(type_pl)s.",
                            tokens['gen_number']) % tokens
        else:
            result += _("You don't get other %(type_pl)s.") % tokens

        result += " "

        if tokens['min_interval'] > 0 and tokens['total'] is not None:
            result += _("You can use a %(type_s)s every second ",
                        "You can use a %(type_s)s every %(min_interval)d seconds ",
                        tokens['min_interval']) % tokens
            result += _("and no more than one %(type_s)s in total.",
                        "and no more than %(total)d %(type_pl)s in total.",
                        tokens['total']) % tokens
        elif tokens['min_interval'] > 0:
            result += _("You can use a %(type_s)s every second.",
                        "You can use a %(type_s)s every %(min_interval)d seconds.",
                        tokens['min_interval']) % tokens
        elif tokens['total'] is not None:
            result += _("You can use no more than one %(type_s)s in total.",
                        "You can use no more than %(total)d %(type_pl)s in total.",
                        tokens['total']) % tokens
        else:
            result += _("You have no limitations on how you use them.") % tokens

    return result


def format_dataset_attrs(dataset):
    """Construct a printable string containing the attributes of a given
    dataset (e.g. live, autojudge enabled, etc.)

    dataset (Dataset): the dataset in question
    return (str): printable string of relevant attributes

    """
    dataset_attrs = []
    active = dataset.version == dataset.task.active_dataset_version
    judging = dataset.autojudge
    if active:
        dataset_attrs.append("Live")
    if judging:
        dataset_attrs.append("Judging")
    if dataset_attrs:
        return " (" + ", ".join(dataset_attrs) + ")"
    else:
        return ""


def filter_ascii(string):
    """Avoid problem with printing a string provided by a malicious
    entity.

    string (str): the input string.
    return (str): string with non-printable chars substituted by *.

    """
    def filter_ascii_char(c):
        """Return * if c is non-printable."""
        if 32 <= ord(c) <= 127:
            return c
        else:
            return '*'

    return "".join(filter_ascii_char(c) for c in string)


def file_handler_gen(BaseClass):
    """This generates an extension of the BaseHandler that allows us
    to send files to the user. This *Gen is needed because the code in
    the class FileHandler is exactly the same (in AWS and CWS) but
    they inherits from different BaseHandler.

    BaseClass (class): the BaseHandler of our server.

    return (class): a FileHandler extending BaseClass.

    """
    class FileHandler(BaseClass):
        """Base class for handlers that need to serve a file to the user.

        """
        def fetch(self, digest, content_type, filename):
            """Sends the RPC to the FS.

            """
            if digest == "":
                logger.error("No digest given")
                self.finish()
                return
            try:
                self.temp_filename = \
                    self.application.service.file_cacher.get_file(
                        digest, temp_path=True)
            except Exception as error:
                logger.error("Exception while retrieving file `%s'. %r" %
                             (filename, error))
                self.finish()
                return

            self.set_header("Content-Type", content_type)
            self.set_header("Content-Disposition",
                            "attachment; filename=\"%s\"" % filename)
            self.start_time = time.time()
            self.size = 0
            self.temp_file = open(self.temp_filename, "rb")
            self.application.service.add_timeout(self._fetch_write_chunk,
                                                 None, 0.02,
                                                 immediately=True)

        def _fetch_write_chunk(self):
            """Send a chunk of the file to the browser.

            """
            data = self.temp_file.read(FileCacher.CHUNK_SIZE)
            length = len(data)
            self.size += length / 1024.0 / 1024.0
            self.write(data)
            if length < FileCacher.CHUNK_SIZE:
                self.temp_file.close()
                os.unlink(self.temp_filename)
                duration = time.time() - self.start_time
                logger.info("%.3lf seconds for %.3lf MB, %.3lf MB/s" %
                            (duration, self.size, self.size / duration))
                self.finish()
                return False
            return True

    return FileHandler


def get_url_root(request_path):
    '''Generates a URL relative to request_uri which would point to the root of
    the website.'''

    # Compute the number of levels we would need to ascend.
    path_depth = request_path.count("/") - 1

    if path_depth > 0:
        return "/".join([".."] * path_depth)
    else:
        return "."


class CommonRequestHandler(RequestHandler):
    """Encapsulates shared RequestHandler functionality.
    """

    def redirect(self, url):
        url = get_url_root(self.request.path) + url

        # We would prefer to just use this:
        #   tornado.web.RequestHandler.redirect(self, url)
        # but unfortunately that assumes it knows the full path to the current
        # page to generate an absolute URL. This may not be the case if we are
        # hidden behind a proxy which is remapping part of its URL space to us.

        self.set_status(302)
        self.set_header("Location", url)
        self.finish()
