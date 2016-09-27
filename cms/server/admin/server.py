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


"""Web server for administration of contests.
"""

import base64
import logging

from cms.io import WebService
from cms import config

from .handlers import HANDLERS

logger = logging.getLogger(__name__)


class AdminWebServer(WebService):
    """Service that runs the web server serving the managers.
    """
    def __init__(self, shard):
        parameters = {
            "cookie_secret": base64.b64encode(config.secret_key),
            "static_files": [("cms.server", "static"),
                             ("cms.server.admin", "static")],
            "rpc_enabled": True,
            "rpc_auth": self.is_rpc_authorized}
        handlers = []

        for hdl in HANDLERS:
            for route in hdl.get_routes():
                handlers.append((route, hdl))

        super(AdminWebServer, self).__init__(
            config.admin_listen_port,
            handlers,
            parameters,
            shard=shard,
            listen_address=config.admin_listen_address)

    def is_rpc_authorized(self, service, shard, method):
        """Check if the current admin is allowed to call an RPC."""
        # TODO: implement this
        return False
