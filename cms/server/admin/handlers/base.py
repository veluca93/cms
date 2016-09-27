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


"""Base handler for most other handlers in AWS, plus some simple (or useful)
function and classes.
"""


from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals


import datetime
import logging
import json
import pkg_resources
import tornado

from cmscommon.datetime import make_datetime, make_timestamp
from cms.server.util import CommonRequestHandler
from cms.db import SessionGen, Base


logger = logging.getLogger(__name__)


class IndexHandler(tornado.web.StaticFileHandler):
    @classmethod
    def get_routes(cls):
        return ["/()", "/(index\.html)"]

    def initialize(self):
        super(IndexHandler, self).initialize(
            path=pkg_resources.resource_filename("cms.server.admin", "static"),
            default_filename="index.html")


def alchemy_to_dict(obj):
    if not isinstance(obj, Base):
        logger.warning("Non-SQLAlchemy object passed to alchemy_to_dict")
        return None
    fields = {}
    for field in [x.name for x in obj.__table__.columns]:
        data = obj.__getattribute__(field)
        fields[field] = data
    return fields


def dict_to_alchemy(cls, dct):
    vals = dict()
    for k, v in dct.iteritems():
        if k in [x.name for x in cls.__table__.columns]:
            vals[k] = v
    return cls(**vals)


def json_default(obj):
    if isinstance(obj, datetime.datetime):
        return {"__type__": "datetime", "timestamp": make_timestamp(obj)}
    elif isinstance(obj, datetime.timedelta):
        return {"__type__": "timedelta", "seconds": obj.total_seconds()}
    else:
        raise TypeError(repr(obj) + " is not JSON serializable!")


def json_object_hook(obj):
    if "__type__" in obj:
        try:
            if obj["__type__"] == "timedelta":
                return datetime.timedelta(seconds=obj["seconds"])
            elif obj["__type__"] == "datetime":
                return make_datetime(obj["timestamp"])
            else:
                logger.warning("Unknown type " + obj["__type__"])
        except (KeyError, ValueError):
            logger.warning(
                "Error decoding a value with type " + obj["__type__"])


def make_api_handler(Cls):
    class HandlerCls(CommonRequestHandler):
        @classmethod
        def get_routes(cls):
            return [
                "/api/" + Cls.__name__.lower() + "/([0-9]+)",
                "/api/" + Cls.__name__.lower()
            ]

        @classmethod
        def get_api_name(cls):
            return Cls.__name__.lower()

        def can_get(self, id=None):
            return True

        def can_patch(self, obj):
            return True

        def can_post(self, obj):
            return True

        def can_delete(self, obj):
            return True

        def add_metadata(self, data):
            return data

        def objects_query(self, session):
            return session.query(Cls)

        def _answer(self, obj):
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(obj, default=json_default))

        def _request(self):
            return json.loads(self.request.body, object_hook=json_object_hook)

        def get(self, id=None):
            try:
                id = int(id) if id is not None else None
            except ValueError:
                logger.warning("Bad request received from tornado!")
                self.send_error(status_code=500)
                return

            if not self.can_get(id):
                self.send_error(status_code=401)
                return

            with SessionGen() as session:
                if id is None:
                    # Show the list of items of type Cls
                    ans = self.objects_query(session).all()
                    ans = [alchemy_to_dict(obj) for obj in ans]
                else:
                    # Show data about the item of type Cls with the given ID.
                    ans = self.objects_query(session)\
                        .filter(Cls.id == id).first()
                    if ans is None:
                        self.send_error(status_code=404)
                        return
                    else:
                        ans = alchemy_to_dict(ans)
                self._answer(self.add_metadata({"data": ans}))

        def put(self, id):
            print("ciao")
            print(self._request())

        def patch(self, id):
            return self.put(id)

    return HandlerCls
