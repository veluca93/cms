#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2016 Luca Versari <veluca93@gmail.com>
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

"""This script exports one or more tasks from the database to a folder,
in italy_yaml format.

"""

from __future__ import absolute_import
from __future__ import print_function

import argparse
import logging
import json
import os
from datetime import timedelta

import yaml

from cms import utf8_decoder
from cms.db import Task, SessionGen
from cms.db.filecacher import FileCacher


logger = logging.getLogger(__name__)


class ExportTask(object):
    """This class exports a single task to disk"""

    def __init__(self, path, task, file_cacher):
        self.task = task
        self.path = path
        self.file_cacher = file_cacher

    def do_export(self):
        """Get the task from the database and save it"""
        ex_path = os.path.join(self.path, self.task.name)

        # Export task.yaml info
        def append_data(d, obj, params):
            for p in params:
                data = getattr(obj, p)
                if isinstance(data, unicode):
                    data = data.encode('utf-8')
                if isinstance(data, timedelta):
                    data = data.seconds
                d[p] = data
        task_data = dict()
        task_params = [
            "name", "title", "token_mode", "token_max_number",
            "token_min_interval", "token_gen_initial", "token_gen_number",
            "token_gen_interval", "token_gen_max"]
        dataset_params = ["time_limit", "memory_limit"]
        append_data(task_data, self.task, task_params)
        dataset = self.task.active_dataset
        append_data(task_data, dataset, dataset_params)
        if dataset.task_type == 'Batch':
            ioinfo = json.loads(dataset.task_type_parameters)[1]
            task_data["infile"], task_data["outfile"] = map(str, ioinfo)

        # Export gen/GEN
        fake_gen = []
        if dataset.score_type == 'GroupMin':
            for tc in json.loads(dataset.score_type_parameters):
                fake_gen.append("#ST: %s" % tc[0])
                fake_gen += ["0"] * tc[1]
        elif dataset.score_type == 'Sum':
            fake_gen = ["0" for i in dataset.testcases]
        else:
            raise NotImplementedError("Score type %s not implemented yet!" %
                                      dataset.score_type)

        # Select statement to export
        if 'it' in self.task.statements:
            statement = self.task.statements['it']
        else:
            statement = self.task.statements.values()[0]

        # Create directory
        try:
            os.makedirs(ex_path)
        except OSError:
            logger.warning("Error creating folder %s!", ex_path)
            return
        # Graders are the only files stored in sol, so we
        # create that directory only if there is any grader.
        # Moreover, other managers go in check, so if other
        # managers are present we create that folder too.
        gmap = map(lambda x: x.startswith('grader'), dataset.managers.keys())
        if any(gmap):
            os.mkdir(os.path.join(ex_path, "sol"))
        if not all(gmap):
            os.mkdir(os.path.join(ex_path, "check"))
        os.mkdir(os.path.join(ex_path, "statement"))
        os.mkdir(os.path.join(ex_path, "input"))
        os.mkdir(os.path.join(ex_path, "output"))
        os.mkdir(os.path.join(ex_path, "gen"))
        os.mkdir(os.path.join(ex_path, "att"))

        # Actually write the files
        # task.yaml
        with open(os.path.join(ex_path, 'task.yaml'), 'wb') as f:
            yaml.dump(task_data, default_flow_style=False, stream=f)
        # gen/GEN
        with open(os.path.join(ex_path, "gen", "GEN"), 'wb') as f:
            f.write('\n'.join(fake_gen) + '\n')

        # statement/statement.pdf
        self.file_cacher.get_file_to_path(
            statement.digest,
            os.path.join(ex_path, "statement", "statement.pdf"))

        # sol/grader.* and check/*
        for fname, manager in dataset.managers.iteritems():
            if fname.startswith('grader'):
                fld = 'sol'
            else:
                fld = 'check'
            self.file_cacher.get_file_to_path(
                manager.digest,
                os.path.join(ex_path, fld, fname))

        # input/* and output/*
        testcases = dataset.testcases.values()
        testcases.sort(key=lambda x: x.codename)
        for tcname, testcase in enumerate(testcases):
            self.file_cacher.get_file_to_path(
                testcase.input,
                os.path.join(ex_path, "input", "input%s.txt" % tcname))
            self.file_cacher.get_file_to_path(
                testcase.output,
                os.path.join(ex_path, "output", "output%s.txt" % tcname))

        # att/*
        for attname, attachment in self.task.attachments.iteritems():
            self.file_cacher.get_file_to_path(
                attachment.digest,
                os.path.join(ex_path, "att", attname))


def main():
    parser = argparse.ArgumentParser(
        description="Export one or more tasks from the DB to disk.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-t", "--task",
        action="store", type=utf8_decoder,
        default=None,
        help="use the specified loader (default: autodetect)"
    )
    parser.add_argument(
        "target",
        action="store", type=utf8_decoder,
        help="target file where task(s) should be exported to"
    )
    args = parser.parse_args()
    with SessionGen() as session:
        tasks = session.query(Task)
        if args.task is not None:
            tasks = tasks.filter(Task.name == args.task)
        tasks = tasks.all()
        fc = FileCacher()
        for task in tasks:
            logger.info("Exporting task %s", task.name)
            ExportTask(args.target, task, fc).do_export()
        fc.destroy_cache()


if __name__ == '__main__':
    main()
