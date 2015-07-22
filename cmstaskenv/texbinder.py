#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# cms-booklet - github.com/obag/cms-booklet
# Copyright © 2014 Gabriele Farina <gabr.farina@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import sys
import os
import argparse
import jinja2
import yaml
import tempfile
import shutil
import subprocess
import threading
from jinja2 import meta as jinja2_meta

def fully_split(path):
    """Split a path into a list of components.

    Call iteratively os.path.split() in order to split a path in
    all its components, which are returned as a list.

    """
    folders = []
    while 1:
        path, folder = os.path.split(path)
        if folder != "":
            folders.append(folder)
        else:
            if path != "":
                folders.append(path)
            break
    folders.reverse()
    return folders

def copy_static(src, dst, force_content=False):
    """Copy src to directory dst.

    If src is a directory, it is recursively copied.

    If src is a symbolic link, its content is copied, unless the
    symlink is relative and points to a location inside the same
    directory (or one of its subdirectories). If force_content is
    True, then the content of symlinks is always copied,
    irrespective of what stated before.

    """
    #print "src: %s, dst: %s" % (src, dst)
    assert os.path.isdir(dst)

    if not os.path.isdir(src):
        if os.path.islink(src):
            linkto = os.readlink(src)
            # If the file is a absolute link or a relative
            # link to something outside the current
            # directory, copy the content instead of the
            # link
            if force_content or os.path.isabs(linkto) or fully_split(linkto)[0] == '..':
                src = linkto if os.path.isabs(linkto) else os.path.join(os.path.dirname(src), linkto)
            else:
                dest_path = os.path.join(dst, os.path.basename(src))
                if os.path.exists(dest_path):
                    os.unlink(dest_path)
                os.symlink(linkto, dest_path)
                return
        shutil.copy(src, dst)
    else:
        shutil.copytree(src, os.path.join(dst, os.path.basename(src)))

def process_problem(raw_content):
    dependencies = []

    lines = raw_content.split('\n')
    for i in xrange(len(lines)):
        line = lines[i]
        if line[:11] == '\\usepackage':
            dependencies += [line]
            lines[i] = '%' + lines[i]
    return '\n'.join(lines), dependencies


def compile_task_pdf():
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')

    # Set up jinja2:
    jinja2_env = jinja2.Environment(loader = jinja2.FileSystemLoader(templates_dir))
    jinja2_env.block_start_string = '((*'
    jinja2_env.block_end_string = '*))'
    jinja2_env.variable_start_string = '((('
    jinja2_env.variable_end_string = ')))'
    jinja2_env.comment_start_string = '((='
    jinja2_env.comment_end_string = '=))'

    def get_template_variables(template_name, filename):
        template_source = jinja2_env.loader.get_source(jinja2_env, os.path.join(template_name, filename))[0]
        parsed_content = jinja2_env.parse(template_source)
        return sorted(list(jinja2_meta.find_undeclared_variables(parsed_content)))

    def get_template(template_name, filename):
        return jinja2_env.get_template(os.path.join(template_name, filename))

    # Get the list of all the available templates
    templates = [
        name for name in os.listdir(templates_dir)
        if os.path.isdir(os.path.join(templates_dir, name))
    ]

    epilog = ''
    for template_name in templates:
        epilog += 'Options for template \'%s\':\n' % template_name
        template_dir = os.path.join(templates_dir, template_name)
        defaults = yaml.load(open(os.path.join(template_dir, 'defaults.yaml')).read())

        for opt in get_template_variables(template_name, 'contest.tpl'):
            if opt[:2] != '__': # Variables beginning with __ are meant to be private
                epilog += '  - %s' % opt
                if 'contest' in defaults and opt in defaults['contest']:
                    epilog += ' (default: \'%s\')' % defaults['contest'][opt]
                epilog += '\n'

    # Build the parser object
    parser = argparse.ArgumentParser(
        epilog = epilog,
        formatter_class = argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-k', '--keep',
        action = 'store_true',
        help = 'Keep working directory'
    )
    parser.add_argument(
        '-t', '--template',
        default = 'cms-contest',
        help = 'The template to be used'
    )
    parser.add_argument(
        '-n', '--no-compile',
        action = 'store_true',
        help = 'Do not compile latex'
    )
    parser.add_argument(
        '-f', '--force',
        action = 'store_true',
        help = 'Delete working directories if they exist'
    )
    parser.add_argument(
        '-l', '--language',
        default = 'english',
        help = 'The language to be used')
    parser.add_argument(
        '--set',
        action = 'append',
        default = [],
        metavar = 'KEY=VALUE',
        help = 'Set (or override) template variables'
    )

    # Parse the arguments
    args = vars(parser.parse_args())
    language = args['language']

    # Check that the templates exist:
    template_dir = os.path.join(templates_dir, args['template'])
    contest_template_file = os.path.join(template_dir, 'contest.tpl')
    problem_template_file = os.path.join(template_dir, 'problem.tpl')
    template_defaults_file = os.path.join(template_dir, 'defaults.yaml')
    template_data_folder = os.path.join(template_dir, 'data')

    print "[i] Loading contest template (%s)" % contest_template_file
    contest_template = get_template(args['template'], 'contest.tpl')
    contest_template_variables = get_template_variables(args['template'], 'contest.tpl')

    print "[i] Loading problem template (%s)" % problem_template_file
    problem_template = get_template(args['template'], 'problem.tpl')
    problem_template_variables = get_template_variables(args['template'], 'problem.tpl')

    print "[i] Loading template defaults (%s)" % template_defaults_file
    template_defaults = yaml.load(open(template_defaults_file).read())

    task = os.path.basename(os.getcwd())

    contest_abspath = os.path.abspath("../contest.yaml")
    print "[>] Processing CONTEST file: %s" % contest_abspath
    print "[i] Reading contest file"

    contest_tpl_args = dict(
        zip(contest_template_variables, [None]*len(contest_template_variables))
    )
    if 'contest' in template_defaults:
        for var in template_defaults['contest']:
            if var in contest_tpl_args:
                contest_tpl_args[var] = template_defaults['contest'][var]

    # Process the contest.yaml file
    contest_yaml = yaml.load(open(contest_abspath).read())
    for (key, value) in contest_yaml.items():
        if key in contest_template_variables:
            contest_tpl_args[key] = value
    # Process manual --set options
    for opt in args['set']:
        try:
            key, value = opt.split("=")
            if value in ('True', 'False'):
                value = eval(value)
        except:
            raise NotImplementedError
        if key in contest_template_variables:
            contest_tpl_args[key] = value
        else:
            print "[w] No template variable named '%s'!" % key
    contest_tpl_args['__language'] = language

    print "[*] Contest template variables:"
    for (key, value) in contest_tpl_args.items():
        if key[:2] != '__':
            print "[-] '%s': '%s'" % (key, value)

    assert 'tasks' in contest_yaml

    rendered_problem_templates = []
    additional_packages = []
    contest_statics = []

    task_abspath = os.path.join(os.path.dirname(contest_abspath), task, 'task.yaml')
    print "[>] Processing PROBLEM file: %s" % task_abspath
    print "[i] Reading problem file"

    problem_tpl_args = dict(
        zip(problem_template_variables, [None]*len(problem_template_variables))
    )
    if 'problem' in template_defaults:
        for var in template_defaults['problem']:
            if var in problem_tpl_args:
                problem_tpl_args[var] = template_defaults['problem'][var]

    # Process the task.yaml file
    task_yaml = yaml.load(open(task_abspath).read())
    for (key, value) in task_yaml.items():
        if key in problem_template_variables:
            problem_tpl_args[key] = value
    # Process manual --set options
    for opt in args['set']:
        try:
            key, value = opt.split("=")
            if value in ('True', 'False'):
                value = eval(value)
        except:
            raise NotImplementedError
        if key in problem_template_variables:
            problem_tpl_args[key] = value
        else:
            print "[w] No template variable named '%s'!" % key
    problem_tpl_args['__language'] = language

    print "[*] Problem template variables:"
    for (key, value) in problem_tpl_args.items():
        if key[:2] != '__':
            print "[-] '%s': '%s'" % (key, value)

    # Fill in the template for the single problem
    if args['keep']:
        target_dir = os.path.join(os.path.dirname(task_abspath), 'testo', '_%s_files' % language)
        if os.path.exists(target_dir):
            if args['force']:
                print "[w] Deleting old directory"
                shutil.rmtree(target_dir)
            else:
                raise NotImplementedError
    else:
        target_dir = tempfile.mkdtemp()
        shutil.rmtree(target_dir)
    print "[i] Setting up working directory (%s)" % target_dir
    if os.path.exists(template_data_folder):
        shutil.copytree(template_data_folder, target_dir)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    for obj in os.listdir(os.path.join(os.path.dirname(task_abspath), 'testo')):
        path = os.path.join(os.path.dirname(task_abspath), 'testo', obj)
        if obj[0] not in ('_', '.'):
            print "[i] Copying file/dir %s" % path
            contest_statics += [path]
            copy_static(path, target_dir)

    problem_statement_file = os.path.join(os.path.dirname(task_abspath), 'testo', '%s.tex' % language)
    target_statement_file = os.path.join(target_dir, 'statement.tex')
    problem_pdf_file = os.path.join(os.path.dirname(task_abspath), 'testo', '%s.pdf' % language)

    print "[i] Reading problem statement file (%s)" % problem_statement_file
    raw_problem_content = open(problem_statement_file).read().decode('utf8')
    problem_content, problem_dependencies = process_problem(raw_problem_content)
    additional_packages += problem_dependencies
    for package in problem_dependencies:
        print "[-] Additional package: %s" % package

    problem_tpl_args['__content'] = problem_content
    rendered_problem_templates += [ problem_template.render(problem_tpl_args) ]

    print "[i] Writing problem statement (%s)" % target_statement_file
    open(target_statement_file, 'w').write(
        contest_template.render(
            contest_tpl_args,
            __problems = rendered_problem_templates[-1:],
            __additional_packages = problem_dependencies
        ).encode('utf8')
    )

    if not args['no_compile']:
        print "[>] Compiling tex file"
        proc = subprocess.Popen(
            ['latexmk', '-f', '-interaction=nonstopmode', '-pdf', target_statement_file],
            cwd = target_dir,
            stdout = open(os.devnull, "w"),
            stderr = open(os.devnull, "w")
        )
        timer = threading.Timer(60, lambda: proc.kill())
        timer.start()
        proc.wait()
        timer.cancel()
        target_pdf_file = os.path.join(target_dir, 'statement.pdf')
        if os.path.exists(target_pdf_file):
            print "[i] PDF file succesfully created"
            shutil.copyfile(target_pdf_file, problem_pdf_file)
            errors = False
        else:
            print "[w] PDF file not created. Rerun with --keep or view log files in %s" % target_dir
            errors = True

    if not args['keep'] and not errors:
        print "[i] Deleting working directory"
        shutil.rmtree(target_dir)
