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

from cms import logger
from cms.db.SQLAlchemyAll import SessionGen, Contest, User, Task, Submission


def get_submission_results(contest_id=None, user_id=None, task_id=None,
                           submission_id=None, dataset_id=None, session=None):
    """Search for submission results that match the given criteria

    The submission results will be returned as a list, and the first
    five parameters determine the filters used to decide which
    submission results to include. Some of them are incompatible, that
    is they cannot be non-None at the same time. When this happens it
    means that one of the parameters "implies" the other (for example,
    giving the user already gives the contest it belongs to). Trying to
    give them both is useless and could only lead to inconsistencies
    and errors.

    contest_id (int): id of the contest to invalidate, or None.
    user_id (int): id of the user to invalidate, or None.
    task_id (int): id of the task to invalidate, or None.
    submission_id (int): id of the submission to invalidate, or None.
    dataset_id (int): id of the dataset to invalidate, or None.
    session (Session): the database session to use, or None to use a
                       temporary one.

    """
    if session is None:
        with SessionGen(commit=False) as session:
            return get_submission_results(
                contest_id, user_id, task_id, submission_id, dataset_id,
                session)

    if task_id is not None and contest_id is not None:
        raise ValueError("contest_id is superfluous if task_id is given")
    if user_id is not None and contest_id is not None:
        raise ValueError("contest_id is superfluous if user_id is given")
    if submission_id is not None and contest_id is not None:
        raise ValueError("contest_id is superfluous if submission_id is given")
    if submission_id is not None and task_id is not None:
        raise ValueError("task_id is superfluous if submission_id is given")
    if submission_id is not None and user_id is not None:
        raise ValueError("user_id is superfluous if submission_id is given")
    if dataset_id is not None and task_id is not None:
        raise ValueError("task_id is superfluous if dataset_id is given")
    if dataset_id is not None and contest_id is not None:
        raise ValueError("contest_id is superfluous if dataset_id is given")

    # If we don't already know the task (either via task_id or,
    # indirectly, via submission_id) get it from dataset_id.
    if submission_id is None and task_id is None and \
            dataset_id is not None:
        dataset = Dataset.get_from_id(dataset_id, session)
        task_id = dataset.task_id

    q = session.query(SubmissionResult)
    if dataset_id is not None:
        q = q.filter(SubmissionResult.dataset_id == dataset_id)
    if submission_id is not None:
        q = q.filter(SubmissionResult.submission_id == submission_id)
    if user_id is not None:
        q = q.join(Submission).filter(Submission.user_id == user_id)
    if task_id is not None:
        q = q.join(Submission).filter(Submission.task_id == task_id)
    if contest_id is not None:
        q = q.join(Submission)\
             .join(User).filter(User.contest_id == contest_id)\
             .join(Task).filter(Task.contest_id == contest_id)
    return q.all()
