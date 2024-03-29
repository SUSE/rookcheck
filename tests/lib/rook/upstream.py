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
import requests
import yaml


from tests.config import settings, converter
from tests.lib.common import execute, recursive_replace
from tests.lib.rook.base import RookBase

logger = logging.getLogger(__name__)


class RookCluster(RookBase):
    def __init__(self, workspace, kubernetes):
        super().__init__(workspace, kubernetes)
        self._rook_built = False
        self.build_dir = os.path.join(self.workspace.build_dir, 'rook')
        self.ceph_dir = os.path.join(
            self.build_dir, 'cluster/examples/kubernetes/ceph')
        self.rook_chart = settings.UPSTREAM_ROOK.ROOK_CEPH_CHART

    def build(self):
        super().build()
        self.get_rook()
        if not converter('@bool', settings.UPSTREAM_ROOK.BUILD_ROOK_FROM_GIT):
            return

        self.get_golang()
        logger.info("Compiling rook...")
        execute(
            command=f"make --directory {self.build_dir} "
                    f"-j BUILD_REGISTRY='rook-build' IMAGES='ceph'",
            env={"PATH": f"{self.workspace.bin_dir}/go/bin:"
                         f"{os.environ['PATH']}",
                 "TMPDIR": self.workspace.tmp_dir,
                 "GOCACHE": self.workspace.tmp_dir,
                 "GOPATH": self.workspace.build_dir},
            log_stderr=False)

        image = 'rook/ceph'
        tag = f"{settings.UPSTREAM_ROOK.VERSION}-rookcheck"
        self.rook_image = f"{image}:{tag}"
        logger.info(f"Tag image as {image}:{tag}")
        execute(f'docker tag "rook-build/ceph-amd64" {image}:{tag}')

        logger.info("Save image tar")
        # TODO(jhesketh): build arch may differ
        execute(f"docker save {image}:{tag} | gzip > %s"
                % os.path.join(self.build_dir, 'rook-ceph.tar.gz'))
        self._rook_built = True

    def preinstall(self):
        super().preinstall()
        if converter('@bool', settings.UPSTREAM_ROOK.BUILD_ROOK_FROM_GIT):
            self.upload_rook_image()
            self._fix_yaml()

    def _get_charts(self):
        super()._get_charts()
        logger.info(f"Adding rook chart helm repo {self.rook_chart}")
        self.kubernetes.helm(f"repo add rook-upstream {self.rook_chart}")

    def get_rook(self):
        logger.info("Clone rook version %s from repo %s" % (
            settings.UPSTREAM_ROOK.VERSION,
            settings.UPSTREAM_ROOK.REPO))
        execute(
            "git clone -b %s %s %s" % (
                settings.UPSTREAM_ROOK.VERSION,
                settings.UPSTREAM_ROOK.REPO,
                self.build_dir),
            log_stderr=False
        )

    def get_golang(self):
        url = 'https://golang.org/VERSION?m=text'
        version = requests.get(url).content.decode("utf-8")
        self.workspace.get_unpack(
            "https://dl.google.com/go/%s.linux-amd64.tar.gz" % version,
            unpack_folder=self.workspace.bin_dir
        )

    def _fix_yaml(self):
        # Replace image reference if we built it in this run
        with open(os.path.join(self.ceph_dir, 'operator.yaml')) as file:
            docs = yaml.load_all(file, Loader=yaml.FullLoader)
            for doc in docs:
                try:
                    image = doc['spec']['template']['spec'][
                            'containers'][0]['image']
                    break
                except KeyError:
                    pass
        replacements = {image: self.rook_image}
        recursive_replace(dir=self.ceph_dir, replacements=replacements)

    def upload_rook_image(self):
        self.kubernetes.hardware.ansible_run_playbook(
            "playbook_rook_upstream.yaml")

    def _install_operator_helm(self):
        version = ""
        if settings.UPSTREAM_ROOK.VERSION != "master":
            version = f"--version {settings.UPSTREAM_ROOK.VERSION}"
        logger.info(
            "Installing rook operator with helm rook-upstream/rook-ceph"
            f" {version}"
        )
        self.kubernetes.helm(
            f"install -n rook-ceph rook-ceph rook-upstream/rook-ceph"
            f" {version}")
