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
import os
import re

from tests.config import settings
from tests.lib import common
from abc import ABC, abstractmethod

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

    @abstractmethod
    def build(self):
        # Having the method in child classes allows easier test writing
        # when using threads to speed things up
        pass

    @abstractmethod
    def preinstall(self):
        pass

    def destroy(self, skip=True):
        if skip:
            # We can skip in most cases since the kubernetes cluster, if not
            # the nodes themselves will be destroyed instead.
            return

        if settings.as_bool('_TEAR_DOWN_CLUSTER_CONFIRM'):
            common.handle_cleanup_input("pause before cleanup rook")

        # TODO(jhesketh): Uninstall rook
        logger.info(f"rook destroy on {self.kubernetes.hardware}")
        pass

    def execute_in_ceph_toolbox(self, command, log_stdout=False):
        if not self.toolbox_pod:
            toolbox_pods = self.kubernetes.get_pods_by_app_label(
                "rook-ceph-tools")
            self.toolbox_pod = toolbox_pods[0]

        return self.kubernetes.execute_in_pod(
            command, self.toolbox_pod, log_stdout=False)

    def install(self):
        # TODO(jhesketh): We may want to provide ways for tests to override
        #                 these
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'common.yaml'))
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'operator.yaml'))

        # set operator log level
        self.kubernetes.kubectl(
            "-n rook-ceph set env "
            "deployment/rook-ceph-operator ROOK_LOG_LEVEL=DEBUG")

        # reduce wait time to discover devices
        self.kubernetes.kubectl(
            "-n rook-ceph set env "
            "deployment/rook-ceph-operator ROOK_DISCOVER_DEVICES_INTERVAL=2m")

        logger.info("Wait for rook-ceph-operator running")
        pattern = re.compile(r'.*rook-ceph-operator.*Running')
        common.wait_for_result(
            self.kubernetes.kubectl, "-n rook-ceph get pods",
            matcher=common.regex_count_matcher(pattern, 1),
            attempts=30, interval=10)

        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'cluster.yaml'))
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'toolbox.yaml'))

        logger.info("Wait for OSD prepare to complete "
                    "(this may take a while...)")
        pattern = re.compile(r'.*rook-ceph-osd-prepare.*Completed')
        common.wait_for_result(
            self.kubernetes.kubectl, "-n rook-ceph get pods"
            " -l app=rook-ceph-osd-prepare",
            matcher=common.regex_count_matcher(pattern, 3),
            attempts=120, interval=15)

        logger.info("Wait for rook-ceph-tools running")
        pattern = re.compile(r'.*rook-ceph-tools.*Running')
        common.wait_for_result(
            self.kubernetes.kubectl, "-n rook-ceph get pods",
            matcher=common.regex_count_matcher(pattern, 1),
            attempts=30, interval=10)

        logger.info("Wait for Ceph HEALTH_OK")
        pattern = re.compile(r'.*HEALTH_OK')
        common.wait_for_result(
            self.execute_in_ceph_toolbox, "ceph status",
            matcher=common.regex_matcher(pattern),
            attempts=60, interval=10)

        logger.info("Rook successfully installed and ready!")

    # TODO: need to check this in details
    # but Ceph features methods should belong to rook base class
    def deploy_rbd(self):
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'csi/rbd/storageclass.yaml'))

    def deploy_filesystem(self):
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'filesystem.yaml'))
        logger.info("Wait for 2 mdses to start")
        pattern = re.compile(r'.*rook-ceph-mds-myfs.*Running')
        common.wait_for_result(
            self.kubernetes.kubectl, "-n rook-ceph get pods",
            log_stdout=False,
            matcher=common.regex_count_matcher(pattern, 2),
            attempts=60, interval=5)

        logger.info("Wait for myfs to be active")
        pattern = re.compile(r'.*active')
        common.wait_for_result(
            self.execute_in_ceph_toolbox, "ceph fs status myfs",
            log_stdout=False,
            matcher=common.regex_matcher(pattern),
            attempts=60, interval=5)
        logger.info("Ceph FS successfully installed and ready!")

    def get_number_of_osds(self):
        # get number of osds
        osds = self.kubernetes.get_pods_by_app_label("rook-ceph-osd")
        osds = len(osds)
        logger.info("cluster has %s osd pods running", osds)
        return osds

    def get_number_of_mons(self):
        # get number of mons
        mons = self.kubernetes.get_pods_by_app_label("rook-ceph-mon")
        mons = len(mons)
        logger.info("cluster has %s mon pods running", mons)
        return mons

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy(skip=not settings.as_bool('_TEAR_DOWN_CLUSTER'))
