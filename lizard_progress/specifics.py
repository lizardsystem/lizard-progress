# (c) Nelen & Schuurmans.  GPL licensed, see LICENSE.rst.
# -*- coding: utf-8 -*-
"""
Base class and some utilities for the measurement-type specific stuff
that is in mtype_specifics and parsers/*.
"""

# Python 3 is coming
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

import collections
import os
import logging
import metfilelib.util.file_reader

from PIL import Image

logger = logging.getLogger(__name__)


# Parsers can decide what type of opened file they want to receive
FILE_IMAGE = object()   # An Image object
FILE_NORMAL = object()  # A normal file object as returned by open()
FILE_READER = object()  # A file reader with support for line numbers, etc
FILE_PATH = object()    # Just a path to the file

Error = collections.namedtuple('Error', 'line, error_code, error_message')


class Specifics(object):
    def __init__(self, project, activity=None):
        self.project = project
        self.activity = activity
        self.__set_specifics()

    def __set_specifics(self):
        # Only import it now to avoid circular imports (models
        # imports this, this imports mtype_specifics, that imports
        # parsers, those import models).
        from lizard_progress.mtype_specifics import AVAILABLE_SPECIFICS

        slug = self.activity.measurement_type.implementation_slug
        self._specifics = AVAILABLE_SPECIFICS[slug]

    def __instance(self):
        cls = self._specifics[0]
        return cls(self.activity)

    def parsers(self, filename):
        """Return the parsers that have the right extension for this
        filename.
        """

        parsers = [
            specifics.parser
            for specifics in self._specifics
            if os.path.splitext(filename)[-1].lower() in specifics.extensions
            ]

        return parsers

    def html_handler(self, activity=None):
        instance = self.__instance()
        return getattr(instance, 'html_handler', None)

    def image_handler(self, activity=None):
        instance = self.__instance()
        return getattr(instance, 'image_handler', None)

    @property
    def location_types(self):
        return sorted(set(loctype for specifics in self._specifics
                          for loctype in specifics.location_types))

    @property
    def allow_planning_dates(self):
        return any(spec.allow_planning_dates for spec in self._specifics)


def _open_uploaded_file(path, file_type):
    """Open file using PIL.Image.open if it is an image, otherwise
    open normally."""
    filename = os.path.basename(path)

    if file_type is FILE_IMAGE:
        try:
            ob = Image.open(path)
            ob.name = filename
            return ob
        except IOError:
            logger.info("IOError in Image.open(%s)!" % (path,))
            raise

    if file_type is FILE_READER:
        return metfilelib.util.file_reader.FileReader(
            path, skip_empty_lines=True)

    if file_type is FILE_NORMAL:
        return open(path, 'rU')

    if file_type is FILE_PATH:
        return path


def parser_factory(parser, activity, path):
    """Sets up the parser and returns a parser instance."""

    if not issubclass(parser, ProgressParser):
        raise ValueError("Argument 'parser' of parser_factory should be "
                         "a ProgressParser instance.")

    file_object = _open_uploaded_file(path, parser.FILE_TYPE)

    return parser(activity, file_object)


class ProgressParser(object):
    """Parser superclass that implementing parsers should inherit from.

    When the parser instance is created, self.project and self.contractor
    will be set. Deciding which measurement type we are dealing with is
    left to the parsers.

    The parse() method will have to be implemented by parsers. It gets
    one argument: file_object, which isn't passed in but set as
    self.file_object so that other methods can access it as well. In
    case the uploaded file is a .jpg, .gif or .png, this is an opened
    PIL.Image object, with the file's basename added as
    file_object.name. Otherwise it's a file object open for reading,
    which always has a file.name attribute.

    parse() should always check whether its argument is an instance of
    PIL.ImageFile.ImageFile, and return UnsuccesfulParserResult if it
    is the wrong type.  This is because the type of object you get is
    effectively controlled by the user, and therefore untrusted.

    Parsers return a tuple with three elements: success, errors,
    measurements.

    Success is None if this parser doesn't apply to this file; it's
    not even wrong.

    If success is True, measurements should be a list of Measurement instances.

    If success is False, errors should be a list of Error instances.

    Parse can return three different things:
    - When it finds it is not applicable to the file in question,
      return UnSuccessfulParserResult without any arguments.
    - If it finds an error, return the same object with the error
      message as its argument. There is a helper function below that
      includes the line number in the file, if you use the also given
      helper method for parsing the file line by line.
    - In case of success, return SuccessfulParserResult with an
      iterable of Measurement objects. The calling view will add the
      full filename of the parsed file and a timestamp to them."""

    FILE_TYPE = FILE_NORMAL

    def __init__(
            self, activity, file_object):
        self.activity = activity
        self.file_object = file_object
        self.errors = []
        self.possible_requests = []

    def parse(self, check_only=False):
        """Not applicable therefore return default."""
        return UnSuccessfulParserResult()

    def error(self, key, *args):
        """Old-style way of returning an error.
        Lookup the error message by its key in self.ERRORS, format it
        using *args and add the line number if possible."""

        prefix = ''
        if hasattr(self, 'file_object') and hasattr(self.file_object, 'name'):
            prefix += '%s: ' % (os.path.basename(self.file_object.name))

        if hasattr(self, 'la') and self.la:
            prefix += "Fout op regel %d: " % (self.la.line_number - 1,)
        else:
            prefix += "Fout: "

        if hasattr(self, 'ERRORS') and key in self.ERRORS:
            message = self.ERRORS[key]
        else:
            message = "Onbekende fout"

        if args:
            message = message % tuple(args)

        return UnSuccessfulParserResult(prefix + message)

    def success(self, measurements):
        """Old-style way of returning success.
        A shortcut with little utility, but if we have self.error()
        perhaps we should also have self.success()."""
        return SuccessfulParserResult(measurements)

    def record_error(
            self, line_number, error_code, error_message, recovery=None):
        """Record an error, then continue parsing. Because the error
        is recorded, self._parser_result() will return an
        UnSuccessfulParserResult later.

        If a recovery dict is given, then we also record a
        PossibleRequest using it. This is used for unknown or
        misplaced locations, to automatically create requests to add
        or change them. A user can turn possible requests into actual
        requests by giving a motivation on the possible requests
        screen. IF all possible requests are turned into actual
        requests, and they are all accepted, and the uploaded file
        isn't removed yet, then the file is re-submitted.

        Don't record an error on a line that already has one. Usually
        if there is an error on some line, that automatically leads to
        more errors in later checks."""

        for error in self.errors:
            if error.line > 0 and error.line == line_number:
                return

        self.errors.append(Error(
            line=line_number,
            error_code=error_code,
            error_message=error_message))

        if recovery is not None:
            self.possible_requests.append(recovery)

    def _parser_result(self, measurements):
        """Called by the parser, from the parse() function, after
        parsing a file using new-style errors. If errors were recorded
        before this point, this will return an
        UnSuccessfulParserResult with those errors in it. If there
        were no errors, this will return a SuccessfulParserResult with
        the right Measurements set."""

        if self.errors:
            return UnSuccessfulParserResult(
                errors=self.errors,
                possible_requests=self.possible_requests)

        return SuccessfulParserResult(measurements)

    def config_value(self, key):
        return self.activity.config_value(key)


class SuccessfulParserResult(object):
    """
    Returned by a successful parser. success is True, and measurements
    is an iterable of Measurement objects that were inserted by the
    parser. Lizard_progress will update them with filename of the file
    that was parsed (after moving it to its eventual destination) and
    a timestamp.

    Note that measurements can be empty, if the parser was called with
    check_only=True (from a checking script, for instance).
    """
    def __init__(self, measurements):
        self.success = True
        self.measurements = tuple(measurements)

    def __str__(self):
        return ("SuccessfulParserResult, {0} measurements".
                format(len(self.measurements)))


class UnSuccessfulParserResult(object):
    """
    Returned by an unsuccessful parser. Error is an error message.
    """
    def __init__(self, error=None, errors=None, possible_requests=None):
        self.success = False

        # A parser should use either the old way of reporting errors,
        # or the new way.

        # Old way -- one error message, presumed to be at line number 0
        self.error = error

        # New way -- iterable of Error namedtuples, with line /
        # error_message / error_code
        self.errors = tuple(errors) if errors else None
        self.possible_requests = possible_requests or []

    def __str__(self):
        return (
            "UnSuccessfulParserResult: {}".
            format(self.error or self.errors))

    @property
    def recovery_possible(self):
        """Recovery from this unsuccessful result is possible if every
        error also has a possible request attached to it."""
        num_errors = len(self.errors) if self.errors else 0

        return num_errors > 0 and len(self.possible_request) == num_errors
