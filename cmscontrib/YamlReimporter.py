#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2013 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Luca Versari <veluca93@gmail.com>
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

"""This service imports a contest into the database ***over*** an existing
contest, calling an appropriate loader to read it from the disk.

"""

import argparse
import os

from cms import logger
from cms.db import analyze_all_tables, ask_for_contest
from cms.db.FileCacher import FileCacher
from cms.db.SQLAlchemyAll import SessionGen, Contest, Dataset, Task

from cmscontrib.YamlLoader import YamlLoader


class Reimporter:
    """This service imports a contest into the database ***over*** an existing
    contest, calling an appropriate loader to read it from the disk.

    """
    def __init__(self, path, contest_id, force=False, append=False):
        self.old_contest_id = contest_id
        self.force = force
        self.append = append

        self.file_cacher = FileCacher()

        self.loader = YamlLoader(os.path.realpath(path), self.file_cacher)

    def run(self):
        """Interface to make the class do its job."""
        self.do_reimport()

    def update_cprops(self, old, new):
        # We update a column property if it is set in the new object
        for prp in old._col_props:
            if hasattr(new, prp.key):
                setattr(old, prp.key, getattr(new, prp.key))

    def update_obj(self, old_obj, new_obj):
        """Updates the task object given in old_task with the information
        from the dict new_task."""
        self.update_cprops(old_obj, new_obj)

        # We need to handle in a special way non-scalar values.
        # TODO: here we are assuming we have multiple-level relationships only
        # in the case of datasets.
        for k in old_obj._rel_props:
            olds = getattr(old_obj, k.key)
            news = getattr(new_obj, k.key)
            if k.key == "datasets":
                oldd = dict([(d.description, i) for i, d in enumerate(olds)])
                newd = dict([(d.description, i) for i, d in enumerate(news)])
                for i in newd.iterkeys():
                    old = oldd.get(i)
                    new = newd.get(i)
                    if old is None:
                        temp = news[new]
                        del news[new]
                        olds.append(temp)
                    else:
                        if not self.append:
                            self.update_obj(olds[old], news[new])
                        else:
                            rep = 2
                            while "%s (%d)" % (i, rep) in set(oldd.keys()):
                                rep += 1
                            temp = news[new]
                            temp.description = "%s (%d)" % (i, rep)
                            del news[new]
                            olds.append(temp)
            elif isinstance(olds, dict):
                to_check = set(olds.keys()) | set(news.keys())
                for i in to_check:
                    old = olds.get(i)
                    new = news.get(i)
                    if old is None:
                        del news[i]
                        olds[i] = new
                    elif new is None:
                        del olds[i]
                    else:
                        self.update_cprops(old, new)
            elif isinstance(olds, list):
                l1 = len(olds)
                l2 = len(news)
                for i in xrange(0, max(l1, l2)):
                    if i >= l1:
                        new = news[i]
                        del news[i]
                        olds.append(new)
                    elif i >= l2:
                        del olds[i]
                    else:
                        self.update_cprops(olds[i], news[i])
            elif isinstance(olds, Contest):
                # TODO: find a better way to handle this...
                pass
            elif isinstance(olds, Dataset):
                pass
            elif isinstance(olds, Task):
                pass
            elif olds is None:
                pass
            else:
                raise RuntimeError("Unknown type of relationship for %s.%s:"
                                   " %s." %
                                   (old_obj.__class__.__name__,
                                   k.key,
                                   olds.__class__.__name__))

    def do_reimport(self):
        """Ask the loader to load the contest and actually merge the
        two.

        """
        with SessionGen(commit=False) as session:
            # Load the old contest from the database.
            old_contest = Contest.get_from_id(self.old_contest_id, session)
            old_users = dict((x.username, x) for x in old_contest.users)
            old_tasks = dict((x.name, x) for x in old_contest.tasks)

            # Load the new contest from the filesystem.
            new_contest, new_tasks, new_users = self.loader.get_contest()
            new_users = dict((x["username"], x) for x in new_users)
            new_tasks = dict((x["name"], x) for x in new_tasks)

            # Updates contest-global settings that are set in new_contest.
            self.update_cprops(old_contest, new_contest)

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
                    old_contest.users.append(self.loader.get_user(new_user))
                elif new_user is not None:
                    # Update an existing user.
                    logger.info("Updating user %s" % user)
                    new_user = self.loader.get_user(new_user)
                    self.update_cprops(old_user, new_user)
                else:
                    # Delete an existing user.
                    if self.force:
                        logger.info("Deleting user %s" % user)
                        old_contest.users.remove(old_user)
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
                    old_contest.tasks.append(self.loader.get_task(new_task))
                elif new_task is not None:
                    # Update an existing task.
                    logger.info("Updating task %s" % task)
                    new_task = self.loader.get_task(new_task)
                    self.update_obj(old_task, new_task)
                else:
                    # Delete an existing task.
                    if self.force:
                        logger.info("Deleting task %s" % task)
                        old_contest.tasks.remove(old_task)
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

        logger.info("Reimport of contest %s finished." % self.old_contest_id)

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
    parser.add_argument("-a", "--append", action="store_true",
                        help="append the datasets instead of replacing them")
    parser.add_argument("import_directory",
                        help="source directory from where import")

    args = parser.parse_args()

    if args.contest_id is None:
        args.contest_id = ask_for_contest()

    Reimporter(path=args.import_directory,
               contest_id=args.contest_id,
               force=args.force, append=args.append).run()


if __name__ == "__main__":
    main()
