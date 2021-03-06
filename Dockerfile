FROM ubuntu:14.04
MAINTAINER Luca Versari <veluca93@gmail.com>

RUN apt-get update
RUN apt-get -y install build-essential fpc postgresql postgresql-client \
    gettext python2.7 iso-codes shared-mime-info stl-manual cgroup-lite \
    texlive texlive-latex-extra nano latexmk pypy python-pip supervisor \
    openssh-server

RUN pip install sortedcontainers
RUN pip install http://github.com/obag/cms-booklet/archive/master.zip

RUN curl -O https://bootstrap.pypa.io/get-pip.py
RUN pypy get-pip.py
RUN mv /usr/local/bin/pip /usr/local/bin/pip-pypy
RUN pypy /usr/local/bin/pip-pypy install sortedcontainers

RUN mkdir -p /var/run/sshd /var/log/supervisor
RUN sed -i 's/StrictModes yes/StrictModes no/' /etc/ssh/sshd_config
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
CMD cgroups-mount && /usr/bin/supervisord

EXPOSE 22 8888 8889 8890

# This apt-get is necessary until the following adopt python wheels:
#   * psycopg2
#   * pycups
#   * PyYAML
# (And until python wheels will support Linux binaries)
RUN apt-get -y install python-dev libpq-dev libcups2-dev libyaml-dev

ADD . /cms
RUN cd /cms && pip install -r requirements.txt && \
    ./setup.py build && ./setup.py install && rm -rf /cms

# See above about python wheels
RUN apt-get -y remove python-dev libpq-dev libcups2-dev libyaml-dev
