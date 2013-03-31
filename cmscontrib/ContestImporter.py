#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2013 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

"""This service imports a contest from a directory that has been the
target of a ContestExport. The process of exporting and importing
again should be idempotent.

"""

import io
import os
import argparse
import shutil
import simplejson as json
import tempfile
import tarfile
import zipfile
from datetime import timedelta

import sqlalchemy.exc
from sqlalchemy.orm import \
    ColumnProperty, RelationshipProperty, configure_mappers
from sqlalchemy.types import \
    Boolean, Integer, Float, String, DateTime, Interval

import cms.db.SQLAlchemyAll as class_hook

from cms import logger
from cms.db.FileCacher import FileCacher
from cms.db.SQLAlchemyAll import metadata, SessionGen, Contest, \
    Submission, UserTest, SubmissionResult, UserTestResult

from cmscontrib import sha1sum
from cmscommon.DateTime import make_datetime

# XXX We need mappers to be configured to access ._col_props and
# ._rel_props. It's not clear what triggers SQLAlchemy to do this
# automatically, so we force it here.
configure_mappers()


def find_root_of_archive(file_names):
    """Given a list of file names (the content of an archive) find the
    name of the root directory, i.e., the only file that would be
    created in a directory if we extract there the archive.

    file_names (list of strings): the list of file names in the
                                  archive

    return (string): the root directory, or None if unable to find.

    """
    current_root = None
    for file_name in file_names:
        if '/' not in file_name:
            if current_root is None:
                current_root = file_name
            else:
                return None
    return current_root


class ContestImporter:
    """This service imports a contest from a directory that has been
    the target of a ContestExport. The process of exporting and
    importing again should be idempotent.

    """
    def __init__(self, drop, import_source,
                 load_files, load_model, light,
                 skip_submissions, skip_user_tests):
        self.drop = drop
        self.load_files = load_files
        self.load_model = load_model
        self.light = light
        self.skip_submissions = skip_submissions
        self.skip_user_tests = skip_user_tests

        self.import_source = import_source
        self.import_dir = import_source

        self.file_cacher = FileCacher()

    def run(self):
        """Interface to make the class do its job."""
        return self.do_import()

    def do_import(self):
        """Run the actual import code.

        """
        logger.operation = "importing contest from %s" % self.import_source
        logger.info("Starting import.")

        if not os.path.isdir(self.import_source):
            if self.import_source.endswith(".zip"):
                archive = zipfile.ZipFile(self.import_source, "r")
                file_names = archive.infolist()

                self.import_dir = tempfile.mkdtemp()
                archive.extractall(self.import_dir)
            elif self.import_source.endswith(".tar.gz") \
                     or self.import_source.endswith(".tgz") \
                     or self.import_source.endswith(".tar.bz2") \
                     or self.import_source.endswith(".tbz2") \
                     or self.import_source.endswith(".tar"):
                archive = tarfile.open(name=self.import_source)
                file_names = archive.getnames()
            else:
                logger.critical("Unable to import from %s." %
                                self.import_source)
                return False

            root = find_root_of_archive(file_names)
            if root is None:
                logger.critical("Cannot find a root directory in %s." %
                                self.import_source)
                return False

            self.import_dir = tempfile.mkdtemp()
            archive.extractall(self.import_dir)
            self.import_dir = os.path.join(self.import_dir, root)

        if self.drop:
            logger.info("Dropping and recreating the database.")
            try:
                metadata.drop_all()
            except sqlalchemy.exc.OperationalError as error:
                logger.critical("Unable to access DB.\n%r" % error)
                return False
        try:
            metadata.create_all()
        except sqlalchemy.exc.OperationalError as error:
            logger.critical("Unable to access DB.\n%r" % error)
            return False

        with SessionGen(commit=False) as session:

            # Import the contest in JSON format.
            if self.load_model:
                logger.info("Importing the contest from a JSON file.")

                with io.open(os.path.join(self.import_dir,
                                          "contest.json"), "rb") as fin:
                    # Throughout all the code we'll assume the input is
                    # correct without actually doing any validations.
                    # Thus, for example, we're not checking that the
                    # decoded object is a dict...
                    self.datas = json.load(fin, encoding="utf-8")

                self.objs = dict()
                for id_, data in self.datas.iteritems():
                    self.objs[id_] = self.import_object(data)
                for id_, data in self.datas.iteritems():
                    self.add_relationships(self.datas[id_], self.objs[id_])

                # Removing objects while iterating is dangerous...
                # We hope to avoid problems by using a view.
                for k, v in self.objs.viewitems():

                    # Skip submissions if requested
                    if self.skip_submissions and isinstance(v, Submission):
                        del self.objs[k]

                    # Skip user_tests if requested
                    if self.skip_user_tests and isinstance(v, UserTest):
                        del self.objs[k]

                    # Skip generated data if requested
                    if self.light and (isinstance(v, SubmissionResult) or
                                       isinstance(v, UserTestResult)):
                        del self.objs[k]

                # Mmh... kind of fragile interface
                contest = self.objs["0"]

                session.add(contest)
                session.flush()
                contest_id = contest.id
                contest_files = contest.enumerate_files(
                    self.skip_submissions, self.skip_user_tests, self.light)
                session.commit()
            else:
                contest_id = None
                contest_files = None

            # Import files.
            if self.load_files:
                logger.info("Importing files.")

                files_dir = os.path.join(self.import_dir, "files")
                descr_dir = os.path.join(self.import_dir, "descriptions")

                files = set(os.listdir(files_dir))
                descr = set(os.listdir(descr_dir))

                if not descr <= files:
                    logger.warning("Some files do not have an associated "
                                   "description.")
                if not files <= descr:
                    logger.warning("Some descriptions do not have an "
                                   "associated file.")

                if not (contest_files is None or files <= contest_files):
                    # FIXME Check if it's because this is a light import
                    # or because we're skipping submissions or user_tests
                    logger.warning("The dump contains some files that are "
                                   "not needed by the contest.")
                if not (contest_files is None or contest_files <= files):
                    # The reason for this could be that it was a light
                    # export that's not being reimported as such.
                    logger.warning("The contest needs some files that are "
                                   "not contained in the dump.")

                # Limit import to files we actually need.
                if contest_files is not None:
                    files &= contest_files

                for digest in files:
                    file_ = os.path.join(files_dir, digest)
                    desc = os.path.join(descr_dir, digest)
                    if not self.safe_put_file(file_, desc):
                        logger.critical("Unable to put file `%s' in the database. "
                                        "Aborting. Please remove the contest "
                                        "from the database." % file_)
                        # TODO: remove contest from the database.
                        return False


        if contest_id is not None:
            logger.info("Import finished (contest id: %s)." % contest_id)
        else:
            logger.info("Import finished.")
        logger.operation = ""

        # If we extracted an archive, we remove it.
        if self.import_dir != self.import_source:
            shutil.rmtree(self.import_dir)

        return True

    def import_object(self, data):
        """Import objects from the given data (without relationships)

        The given data is assumed to be a dict in the format produced by
        ContestExporter. This method reads the "_class" item and tries
        to find the corresponding class. Then it loads all column
        properties of that class (those that are present in the data)
        and uses them as keyword arguments in a call to the class
        constructor (if a required property is missing this call will
        raise an error).

        Relationships are not handled by this method, since we may not
        have all referenced objects available yet. Thus we prefer to add
        relationships in a later moment, using the add_relationships
        method.

        """
        cls = getattr(class_hook, data["_class"])

        args = dict()

        for prp in cls._col_props:
            if prp.key not in data:
                # We will let the __init__ of the class check if any
                # argument is missing, so it's safe to just skip here.
                continue

            col = prp.columns[0]
            col_type = type(col.type)

            val = data[prp.key]
            if col_type in [Boolean, Integer, Float, String]:
                args[prp.key] = val
            elif col_type is DateTime:
                args[prp.key] = make_datetime(val) if val is not None else None
            elif col_type is Interval:
                args[prp.key] = timedelta(seconds=val) if val is not None else None
            else:
                raise RuntimeError("Unknown SQLAlchemy column type: %s" % col_type)

        return cls(**args)

    def add_relationships(self, data, obj):
        """Add the relationships to the given object, using the given data.

        Do what we didn't in import_objects: importing relationships.
        We already now the class of the object so we simply iterate over
        its relationship properties trying to load them from the data (if
        present), checking wheter they are IDs or collection of IDs,
        dereferencing them (i.e. getting the corresponding object) and
        reflecting all on the given object.

        Note that both methods don't check if the given data has more
        items than the ones we understand and use.

        """
        cls = type(obj)

        for prp in cls._rel_props:
            if prp.key not in data:
                # Relationships are always optional
                continue

            val = data[prp.key]
            if val is None:
                setattr(obj, prp.key, None)
            elif type(val) == str:
                setattr(obj, prp.key, self.objs[val])
            elif type(val) == list:
                setattr(obj, prp.key, list(self.objs[i] for i in val))
            elif type(val) == dict:
                setattr(obj, prp.key, dict((k, self.objs[v]) for k, v in val.iteritems()))
            else:
                raise RuntimeError("Unknown RelationshipProperty value: %s" % type(val))

    def safe_put_file(self, path, descr_path):
        """Put a file to FileCacher signaling every error (including
        digest mismatch).

        path (string): the path from which to load the file.
        descr_path (string): same for description.

        return (bool): True if all ok, False if something wrong.

        """
        # First read the description.
        try:
            with io.open(descr_path, 'rt', encoding='utf-8') as fin:
                description = fin.read()
        except IOError:
            description = ''

        # Put the file.
        try:
            digest = self.file_cacher.put_file(path=path,
                                               description=description)
        except Exception as error:
            logger.critical("File %s could not be put to file server (%r), "
                            "aborting." % (path, error))
            return False

        # Then check the digest.
        calc_digest = sha1sum(path)
        if digest != calc_digest:
            logger.critical("File %s has hash %s, but the server returned %s, "
                            "aborting." % (path, calc_digest, digest))
            return False

        return True


def main():
    """Parse arguments and launch process.

    """
    parser = argparse.ArgumentParser(description="Importer of CMS contests.")
    parser.add_argument("-d", "--drop", action="store_true",
                        help="drop everything from the database "
                        "before importing")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-F", "--files", action="store_true",
                       help="only import files, ignore database structure")
    group.add_argument("-nF", "--no-files", action="store_true",
                       help="only import database structure, ignore files")
    parser.add_argument("-l", "--light", action="store_true",
                        help="light import (without generated data)")
    parser.add_argument("-nS", "--no-submissions", action="store_true",
                        help="don't import submissions")
    parser.add_argument("-nU", "--no-user-tests", action="store_true",
                        help="don't import user tests")
    parser.add_argument("import_source",
                        help="source directory or compressed file")

    args = parser.parse_args()

    ContestImporter(drop=args.drop,
                    import_source=args.import_source,
                    load_files=not args.no_files,
                    load_model=not args.files,
                    light=args.light,
                    skip_submissions=args.no_submissions,
                    skip_user_tests=args.no_user_tests).run()


if __name__ == "__main__":
    main()
