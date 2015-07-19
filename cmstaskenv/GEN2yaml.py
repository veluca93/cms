#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2015 Luca Versari <veluca93@gmail.com>
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

from __future__ import print_function
import sys
import yaml


def print_as_yaml(data):
    sys.stdout.write(yaml.dump(data, default_flow_style=False))


def main():
    if len(sys.argv) != 2:
        print("Usage: %s GEN_file" % sys.argv[0], file=sys.stderr)
        sys.exit(1)
    GEN = open(sys.argv[1])
    subtasks = []
    subtask = None
    testcases = []
    for line in GEN.readlines():
        line = line.strip()
        if line.startswith('#ST:'):
            if subtask is not None:
                subtasks.append(subtask)
            subtask = dict()
            subtask["testcases"] = []
            subtask["score"] = int(line[4:])
        line = line.split('#')[0].strip()
        if len(line) == 0:
            continue
        testcase = dict()
        testcase["gen_line"] = line
        if subtask is None:
            testcases.append(testcase)
        else:
            subtask["testcases"].append(testcase)
    if subtask is not None:
        subtasks.append(subtask)
        print_as_yaml({"subtasks": subtasks})
    else:
        print_as_yaml({"testcases": testcases})


if __name__ == '__main__':
    main()
