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


# This module should take care of deploying kubernetes. There will likely be
# multiple variations of an abstract base class to do so. However, the
# implementation may need to require a certain base OS. For example, skuba
# would require SLE and can raise an exception if that isn't provided.


import logging
import os
import stat
import wget

from tests.lib.kubernetes.kubernetes_base import KubernetesBase
from tests.lib.hardware.hardware_base import HardwareBase


logger = logging.getLogger(__name__)


class Vanilla(KubernetesBase):
    def __init__(self, hardware: HardwareBase):
        super().__init__(hardware)

    def bootstrap(self):
        self.hardware.execute_ansible_play_raw(
            'playbook_kubernetes_vanilla.yaml')

    def join(self, node):
        super().join(node)
        # FIXME(toabctl): Implement this

    def install_kubernetes(self):
        self._configure_kubernetes_client()
        self._download_kubectl()
        self.untaint_master()
        self._setup_flannel()

    def _setup_flannel(self):
        for node in self.hardware.nodes.values():
            self.kubectl(
                "annotate node %s "
                "flannel.alpha.coreos.com/public-ip-overwrite=%s "
                "--overwrite" % (
                    node.name.replace("_", "-"), node.get_ssh_ip()
                )
            )
        self.kubectl_apply(
            "https://raw.githubusercontent.com/coreos/flannel/master/"
            "Documentation/kube-flannel.yml")

    def _download_kubectl(self):
        # Download specific kubectl version
        # TODO(jhesketh): Allow setting version
        logger.info("Downloading kubectl binary")
        wget.download(
            "https://storage.googleapis.com/kubernetes-release/release/v1.17.3"
            "/bin/linux/amd64/kubectl",
            self.kubectl_exec,
            bar=None
        )
        st = os.stat(self.kubectl_exec)
        os.chmod(self.kubectl_exec, st.st_mode | stat.S_IEXEC)
