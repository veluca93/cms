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

"""This service load a contest from a tree structure "similar" to the
one used in Italian IOI repository.

"""

from __future__ import absolute_import

import os
import os.path
import argparse

import sqlalchemy.exc

from cms import logger
from cms.db.FileCacher import FileCacher

from cmscommon.DateTime import make_datetime

from cmscontrib.YamlLoader import YamlLoader

from cms.db.SQLAlchemyAll import metadata, SessionGen, User, FSObject


def main():
    """Parse arguments and launch process.

    """
    parser = argparse.ArgumentParser(
        description="Importer from the Italian repository for CMS.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-z", "--zero-time", action="store_true",
                       help="set to zero contest start and stop time")
    group.add_argument("-t", "--test", action="store_true",
                       help="setup a contest for testing "
                       "(times: 0, 2*10^9; ips: unset, passwords: a)")
    parser.add_argument("-d", "--drop", action="store_true",
                        help="drop everything from the database "
                        "before importing")
    parser.add_argument("-n", "--user-number", action="store", type=int,
                        help="put N random users instead of importing them")
    parser.add_argument("import_directory",
                        help="source directory from where import")

    args = parser.parse_args()


    logger.info("Creating database structure.")
    if args.drop:
        try:
            with SessionGen() as session:
                FSObject.delete_all(session)
                session.commit()
            metadata.drop_all()
        except sqlalchemy.exc.OperationalError as error:
            logger.critical("Unable to access DB.\n%r" % error)
            return False
    try:
        metadata.create_all()
    except sqlalchemy.exc.OperationalError as error:
        logger.critical("Unable to access DB.\n%r" % error)
        return False


    file_cacher = FileCacher()
    loader = YamlLoader(os.path.realpath(args.import_directory), file_cacher)


    contest, tasks, users = loader.get_contest()

    for task in tasks:
        contest.tasks.append(loader.get_task(task))

    if args.user_number is None:
        for user in users:
            contest.users.append(loader.get_user(user))
    else:
        logger.info("Generating %s random users." % args.user_number)
        contest.users = [User("User %d" % (i),
                              "Last name %d" % (i),
                              "user%03d" % (i))
                         for i in xrange(args.user_number)]

    if args.zero_time:
        contest.start = make_datetime(0)
        contest.stop = make_datetime(0)
    elif args.test:
        contest.start = make_datetime(0)
        contest.stop = make_datetime(2000000000)

        for user in contest.users:
            user.password = 'a'
            user.ip = None


    logger.info("Creating contest on the database.")
    with SessionGen() as session:
        session.add(contest)
        session.commit()
        contest_id = contest.id


    logger.info("Import finished (new contest id: %s)." % contest_id)


if __name__ == "__main__":
    main()
