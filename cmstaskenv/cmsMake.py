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

import os
import shutil
import subprocess
import argparse
import yaml

from cms import SOURCE_EXT_TO_LANGUAGE_MAP, LANG_PYTHON
from cms.db import Manager, Executable, File
from cms.db.filecacher import FileCacher
from cms.grading import get_compilation_commands
from cms.grading.Job import CompilationJob, EvaluationJob
from cms.grading.tasktypes import get_task_type
from cmstaskenv import texbinder

BUILDDIR = 'generated-files'
TEXTDIR = 'text'
GENDIR = 'gen'
VALDIR = 'val'
SOLDIR = 'sol'
MANDIR = 'managers'
EXDIR = 'examples'
SOLNAME = 'solution'
TEXTNAME = 'text'
TCFILE = 'testcases.yaml'


def iofile(name, io):
    return os.path.join(io, "%s_%s.txt" % (io, name))


def infile(name):
    return iofile(name, "input")


def outfile(name):
    return iofile(name, "output")


def link(src, dst):
    dst = os.path.join(BUILDDIR, dst)
    try:
        os.makedirs(os.path.dirname(dst))
    except:
        pass
    try:
        os.unlink(dst)
    except:
        pass
    os.symlink(src, dst)


class MakeException(Exception):
    def __init__(self, tgt, msg="Generic error"):
        super(MakeException, self).__init__(
            "Target %s(%s) failed to build: %s" %
            (tgt.__class__.__name__, tgt.name, msg)
        )


class Target(object):
    def __init__(self, maker, name):
        self.maker = maker
        self.name = name
        self.file = None
        self.deps = []
        self.already_run = False

    def run_command(self, c, stdin=None,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE):
        proc = subprocess.Popen(c, stdin=stdin, stdout=stdout, stderr=stderr)
        data = proc.communicate(stdin)
        if proc.returncode != 0:
            print(" ".join(c))
            print(data[1])
            raise MakeException(self, "Command failed!")
        return data

    def __str__(self):
        def dtn(d):
            return (d[0].__name__,) + d[1:]
        return "%s(%s): %s -> %s" % (
            self.__class__.__name__,
            self.name,
            str(list(map(dtn, self.deps))),
            self.file
        )

    def last_run_time(self):
        return os.stat(os.path.join(BUILDDIR, self.file)).st_mtime

    def work(self):
        pass

    def run(self):
        def tgt(x):
            return self.maker.get_tgt(*x)
        if not all(map(lambda x: tgt(x).already_run, self.deps)):
            return False
        if self.file is not None and os.path.exists(self.file):
            src = os.path.relpath(
                self.file,
                os.path.dirname(os.path.join(BUILDDIR, self.file))
            )
            link(src, self.file)
        try:
            lr = self.last_run_time()
            dtimes = [tgt(x).last_run_time() for x in self.deps]
            if all(map(lambda x: lr >= x, dtimes)):
                self.already_run = True
                return True
        except:
            pass

        self.work()
        self.already_run = True
        return True


class LinkTarget(Target):
    def __init__(self, maker, name, src=None):
        # src defaults to ../name
        # All paths are relative to BUILDDIR
        if src is None:
            src = os.path.join("..", name)
        super(LinkTarget, self).__init__(maker, name)
        self.file = name
        self.src = os.path.relpath(
            os.path.join(BUILDDIR, src),
            os.path.dirname(os.path.join(BUILDDIR, self.file))
        )

    def work(self):
        if self.file[0] == '/':
            return
        link(self.src, self.file)


class CompileTarget(Target):
    def __init__(self, maker, name):
        super(CompileTarget, self).__init__(maker, name)
        self.file = name
        source = None
        self.lang = None
        for ext in SOURCE_EXT_TO_LANGUAGE_MAP:
            lang = SOURCE_EXT_TO_LANGUAGE_MAP[ext]
            if os.path.exists(self.file + ext):
                source = self.file + ext
                self.lang = lang
        if source is None:
            raise MakeException(self, "No source found!")
        self.deps = [(LinkTarget, source)]
        self.source = os.path.join(BUILDDIR, source)
        self.deps += maker.get_manager_tgt()

    def work(self):
        digest = self.maker.filecacher.put_file_from_path(self.source)
        fname = os.path.splitext(os.path.basename(self.source))[0]
        fobj = File(fname + '.%l', digest)
        job = CompilationJob(
            language=self.lang,
            files={fname + '.%l': fobj},
            managers=self.maker.get_managers()
        )
        self.maker.task_type.compile(job, self.maker.filecacher)
        if not job.success:
            raise MakeException(self, "Something weird happened!")
        if not job.compilation_success:
            print(job.plus['stderr'])
            raise MakeException(self, "Compilation failed!")
        self.maker.filecacher.get_file_to_path(
            job.executables[fname].digest,
            os.path.join(BUILDDIR, self.file)
        )
        self.run_command(["chmod", "+x", os.path.join(BUILDDIR, self.file)])


class MakerCompileTarget(Target):
    def __init__(self, maker, name):
        super(MakerCompileTarget, self).__init__(maker, name)
        self.file = name
        self.source = None
        self.lang = None
        for ext in SOURCE_EXT_TO_LANGUAGE_MAP:
            lang = SOURCE_EXT_TO_LANGUAGE_MAP[ext]
            if os.path.exists(self.file + ext):
                self.source = self.file + ext
                self.lang = lang
        if self.source is None:
            raise MakeException(self, "No source found!")
        self.deps = [(LinkTarget, self.source)]

    def work(self):
        src = os.path.join(BUILDDIR, self.source)
        dst = os.path.join(BUILDDIR, self.file)
        if self.lang != LANG_PYTHON:
            commands = get_compilation_commands(self.lang, [src], dst)
        else:
            commands = [[
                'ln', '-s',
                os.path.relpath(src, os.path.dirname(dst)),
                dst
            ]]
        for c in commands:
            self.run_command(c)


class GeneratorTarget(Target):
    def __init__(self, maker, name):
        super(GeneratorTarget, self).__init__(maker, name)
        self.file = os.path.join(GENDIR, name)
        self.deps = [(MakerCompileTarget, self.file)]


class ValidatorTarget(Target):
    def __init__(self, maker, name):
        super(ValidatorTarget, self).__init__(maker, name)
        self.file = os.path.join(VALDIR, name)
        self.deps = [(MakerCompileTarget, self.file)]


class SolutionTarget(Target):
    def __init__(self, maker, name):
        super(SolutionTarget, self).__init__(maker, name)
        self.file = os.path.join(SOLDIR, name)
        self.deps = [(CompileTarget, self.file)]


class GenInputTarget(Target):
    def __init__(self, maker, name, gen, val, line):
        super(GenInputTarget, self).__init__(maker, name)
        self.file = infile(name)
        self.line = line
        self.gen = os.path.join(BUILDDIR, GENDIR, gen)
        self.val = os.path.join(BUILDDIR, VALDIR, val)
        self.deps = [
            (LinkTarget, TCFILE),
            (GeneratorTarget, gen),
            (ValidatorTarget, val)
        ]

    def work(self):
        rfile = os.path.join(BUILDDIR, self.file)
        try:
            os.makedirs(os.path.dirname(rfile))
        except:
            pass
        with open(rfile, 'w') as f:
            self.run_command([self.gen] + self.line.split(), stdout=f)
        self.run_command([self.val, rfile])


class ExampleInputTarget(Target):
    def __init__(self, maker, name):
        super(ExampleInputTarget, self).__init__(maker, name)
        self.file = infile("example_%s" % name)
        src = os.path.join("..", EXDIR, name, "input.txt")
        self.deps = [(LinkTarget, self.file, src)]


class CopyInputTarget(Target):
    def __init__(self, maker, name, orig):
        super(CopyInputTarget, self).__init__(maker, name)
        self.file = infile(name)
        src = infile(orig)
        self.deps = [maker.testcases[orig]['params'],
                     (LinkTarget, self.file, src)]


class OutputTarget(Target):
    def __init__(self, maker, name):
        super(OutputTarget, self).__init__(maker, name)
        self.file = outfile(name)
        self.deps = [maker.testcases[name]['params'],
                     (SolutionTarget, SOLNAME)]

    def work(self):
        inname = os.path.join(
            BUILDDIR,
            self.maker.get_tgt(*self.deps[0]).file
        )
        indigest = self.maker.filecacher.put_file_from_path(inname)
        edigest = self.maker.filecacher.put_file_from_path(
            os.path.join(BUILDDIR, SOLDIR, SOLNAME)
        )
        eobj = Executable(SOLNAME, edigest)
        lang = self.maker.get_tgt(SolutionTarget, SOLNAME)
        lang = self.maker.get_tgt(*lang.deps[0]).lang
        job = EvaluationJob(
            language=lang,
            executables={SOLNAME: eobj},
            managers=self.maker.get_managers(),
            input=indigest,
            get_output=True,
            only_execution=True,
            memory_limit=2048,
            time_limit=20
        )
        self.maker.task_type.evaluate(job, self.maker.filecacher)
        if not job.success:
            raise MakeException(self, "Something weird happened!")
        if job.outcome is None or job.user_output is None:
            print(job.text[0] % job.text[1:])
            raise MakeException(self, "Output creation failed!")
        try:
            os.makedirs(os.path.join(BUILDDIR, "output"))
        except:
            pass
        self.maker.filecacher.get_file_to_path(
            job.user_output,
            os.path.join(BUILDDIR, self.file)
        )


class TestSolutionTarget(Target):
    def __init__(self, maker, name):
        super(TestSolutionTarget, self).__init__(maker, name)
        self.deps = [(SolutionTarget, name)]
        self.deps += maker.get_output_tgt()
        self.deps += maker.get_manager_tgt()

    def work(self):
        raise NotImplementedError(self.__class__.__name__)


class BuildStatementTarget(Target):
    def __init__(self, maker, name):
        super(BuildStatementTarget, self).__init__(maker, name)
        self.deps += maker.get_output_tgt()
        self.deps += maker.get_manager_tgt()

    def work(self):
        texbinder.compile_task_pdf()


class cmsMaker(object):
    def __init__(self, basedir='.'):
        self.targets = dict()
        self.orig_cwd = os.getcwd()
        self.basedir = os.path.realpath(basedir)
        self.filecacher = FileCacher(null=True)
        os.chdir(self.basedir)
        try:
            self.testcases = dict()

            if os.path.isdir(EXDIR):
                for name in os.listdir(EXDIR):
                    d = os.path.join(EXDIR, name)
                    if not os.path.isdir(d):
                        continue
                    tc = dict()
                    tc['name'] = "example_%s" % name
                    tc['params'] = (ExampleInputTarget, name)
                    self.testcases[tc['name']] = tc

            with open("testcases.yaml") as f:
                tc_data = yaml.load(f)

            # Propagate gen/val/limits information
            if 'limits' not in tc_data:
                tc_data['limits'] = None
            for gv in ['generator', 'validator', 'limits']:
                if gv not in tc_data:
                    tc_data[gv] = gv
                if 'testcases' in tc_data:
                    for t in tc_data['testcases']:
                        if gv not in t:
                            t[gv] = tc_data[gv]
                if 'subtasks' in tc_data:
                    for s in tc_data['subtasks']:
                        if gv not in s:
                            s[gv] = tc_data[gv]
                        for t in s['testcases']:
                            if gv not in t:
                                t[gv] = s[gv]

            idx = 0

            def parse_tc(tc, idx):
                if 'name' not in tc:
                    if 'copy' not in tc:
                        tc['name'] = '%03d' % idx
                    else:
                        tc['name'] = '%03d_%s' (idx, tc['copy'])
                if 'copy' in tc:
                    orig = tc['copy']
                    tc['params'] = (CopyInputTarget, tc['name'], orig)
                else:
                    tc['params'] = (GenInputTarget, tc['name'],
                                    tc['generator'], tc['validator'],
                                    tc['gen_line'])
                return tc

            if 'testcases' in tc_data:
                for tc in tc_data['testcases']:
                    tc = parse_tc(tc, idx)
                    idx += 1
                    self.testcases[tc['name']] = tc

            if 'subtasks' in tc_data:
                for s in tc_data['subtasks']:
                    for tc in s['testcases']:
                        tc = parse_tc(tc, idx)
                        idx += 1
                        self.testcases[tc['name']] = tc

            # Managers and task type
            with open('task.yaml', 'r') as f:
                conf = yaml.load(f)
            self.managers = {}
            use_grader = False
            task_type = conf.get('task_type', 'Batch')
            if os.path.isdir(MANDIR):
                for f in os.listdir(MANDIR):
                    path = os.path.join(MANDIR, f)
                    if f.startswith('grader'):
                        self.managers[f] = (LinkTarget, path)
                        use_grader = True
                    else:
                        self.managers[os.path.splitext(f)[0]] = (
                            MakerCompileTarget,
                            os.path.splitext(path)[0]
                        )
            params = conf.get(
                'task_type_parameters',
                '["%s", ["%s", "%s"], "%s"]' %
                ('grader' if use_grader else 'alone',
                 conf.get('infile', 'input.txt'),
                 conf.get('outfile', 'output.txt'),
                 'comparator' if 'checker' in self.managers else 'diff')
            )
            self.task_type = get_task_type(name=task_type, parameters=params)
        finally:
            os.chdir(self.orig_cwd)

    def get_tgt(self, cls, *args):
        key = tuple((cls,) + args)
        if key not in self.targets:
            self.targets[key] = cls(self, *args)
        return self.targets[key]

    def _add_tgt(self, cls, *args):
        tgt = self.get_tgt(cls, *args)
        for d in tgt.deps:
            self._add_tgt(*d)

    def add_tgt(self, cls, *args):
        os.chdir(self.basedir)
        try:
            self._add_tgt(cls, *args)
        finally:
            os.chdir(self.orig_cwd)

    def get_output_tgt(self):
        return [(OutputTarget, name) for name in self.testcases]

    def get_manager_tgt(self):
        return self.managers.values()

    def get_managers(self):
        if hasattr(self, 'cached_managers'):
            return self.cached_managers
        d = os.path.join(BUILDDIR, MANDIR)
        ret = dict()
        if os.path.isdir(d):
            for f in os.listdir(d):
                path = os.path.join(d, f)
                ret[f] = Manager(
                    f,
                    self.filecacher.put_file_from_path(path)
                )
        self.cached_managers = ret
        return ret

    def run(self):
        os.chdir(self.basedir)
        try:
            to_run = self.targets.keys()
            while len(to_run):
                run_next = []
                for k in to_run:
                    if not self.targets[k].run():
                        run_next.append(k)
                to_run = run_next
        finally:
            os.chdir(self.orig_cwd)


def main():
    maker = cmsMaker()
    maker.add_tgt(BuildStatementTarget, SOLNAME)
    maker.run()

if __name__ == "__main__":
    main()
