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
one used in Italian IOI repository ***over*** a contest already in
CMS.

"""

import argparse

from cms import logger
from cms.db import analyze_all_tables, ask_for_contest
from cms.db.FileCacher import FileCacher
from cms.db.SQLAlchemyAll import SessionGen, Contest

from cmscontrib.YamlImporter import YamlLoader


def update(old, new):
    assert type(old) == type(new)
    # assert old._col_props == new._col_props
    # assert old._rel_props == new._rel_props

    for prp in old._col_props:
        setattr(old, prp.key, getattr(new, prp.key))


class Reimporter:
    """This service load a contest from a tree structure "similar" to
    the one used in Italian IOI repository ***over*** a contest
    already in CMS.

    """
    def __init__(self, path, contest_id, force=False):
        self.path = path
        self.contest_id = contest_id
        self.force = force

        self.file_cacher = FileCacher()

        self.loader = YamlLoader(self.path, self.file_cacher)

    def run(self):
        """Interface to make the class do its job."""
        self.do_reimport()

    def do_reimport(self):
        """Ask the loader to load the contest and actually merge the
        two.

        """
        with SessionGen(commit=False) as session:

            # Load the old contest from the database.
            old_contest = Contest.get_from_id(self.contest_id, session)
            old_users = dict((x.username, x) for x in old_contest.users)
            old_tasks = dict((x.name, x) for x in old_contest.tasks)

            # Load the new contest from the filesystem.
            new_contest = self.loader.import_contest()
            new_users = dict((x.username, x) for x in new_contest.users)
            new_tasks = dict((x.name, x) for x in new_contest.tasks)

            update(old_contest, new_contest)

            # Do the actual merge: compare all users of the old and of
            # the new contest and see if we need to create, update or
            # delete them. Delete only if authorized, fail otherwise.
            users = set(old_users.keys()) | set(new_users.keys())
            for user in users:
                old_user = old_users.get(user, None)
                new_user = new_users.get(user, None)

                if old_user is None:
                    # Create a new user.
                    logger.info("Creating user %s" % user)
                    # XXX
                elif new_user is not None:
                    # Update an existing user.
                    logger.info("Updating user %s" % user)
                    update(old_user, new_user)
                else:
                    # Delete an existing user.
                    if self.force:
                        logger.info("Deleting user %s" % user)
                        # XXX
                    else:
                        logger.critical(
                            "User %s exists in old contest, but "
                            "not in the new one. Use -f to force."
                            % user)
                        return False

            # The same for tasks.
            tasks = set(old_tasks.keys()) | set(new_tasks.keys())
            for task in tasks:
                old_task = old_tasks.get(task, None)
                new_task = new_tasks.get(task, None)

                if old_task is None:
                    # Create a new task.
                    logger.info("Creating task %s" % task)
                    # XXX
                elif new_task is not None:
                    # Update an existing task.
                    logger.info("Updating task %s" % task)
                    update(old_task, new_task)
                else:
                    # Delete an existing task.
                    if self.force:
                        logger.info("Deleting task %s" % task)
                        # XXX
                    else:
                        logger.critical(
                            "Task %s exists in old contest, but "
                            "not in the new one. Use -f to force."
                            % task)
                        return False

            session.commit()

        with SessionGen(commit=False) as session:
            logger.info("Analyzing database.")
            analyze_all_tables(session)
            session.commit()

        logger.info("Reimport of contest %s finished." % self.contest_id)

        return True


def main():
    """Parse arguments and launch process.

    """
    parser = argparse.ArgumentParser(
        description="Load a contest from the Italian repository "
        "over an old one in CMS.")
    parser.add_argument("-c", "--contest-id", action="store", type=int,
                        help="id of contest to overwrite")
    parser.add_argument("-f", "--force", action="store_true",
                        help="force the reimport even if some users or tasks "
                        "may get lost")
    parser.add_argument("import_directory",
                        help="source directory from where import")

    args = parser.parse_args()

    if args.contest_id is None:
        args.contest_id = ask_for_contest()

    YamlReimporter(path=args.import_directory,
                   contest_id=args.contest_id,
                   force=args.force).run()


if __name__ == "__main__":
    main()
