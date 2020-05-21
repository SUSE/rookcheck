# Copyright (c) 2019 SUSE LINUX GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from abc import ABC

logger = logging.getLogger(__name__)


class RookBase(ABC):
    def __init__(self, workspace, kubernetes):
        self._workspace = workspace
        self.kubernetes = kubernetes
        self.toolbox_pod = None
        self.ceph_dir = None
        logger.info(f"rook init on {self.kubernetes.hardware}")

    @property
    def workspace(self):
        return self._workspace

    def destroy(self, skip=True):
        logger.info(f"rook destroy on {self.kubernetes.hardware}")
        if skip:
            # We can skip in most cases since the kubernetes cluster, if not
            # the nodes themselves will be destroyed instead.
            return
        # TODO(jhesketh): Uninstall rook
        pass

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
