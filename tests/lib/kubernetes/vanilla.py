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

from tests import config
from tests.lib.kubernetes.kubernetes_base import KubernetesBase
from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.workspace import Workspace


logger = logging.getLogger(__name__)


class Vanilla(KubernetesBase):
    def __init__(self, workspace: Workspace, hardware: HardwareBase):
        super().__init__(workspace, hardware)
        if config.DISTRO == 'openSUSE_k8s':
            self.distro = DeploySUSE()
        else:
            raise Exception("OS yet to be implemented/unsupport.")

    def bootstrap(self):
        self.hardware.execute_ansible_play_raw(
            'playbook_kubernetes_vanilla.yaml')
        self.hardware.execute_ansible_play(
            self.distro.copy_needed_files_master())

        self.hardware.execute_ansible_play(self.distro.setup_master_play())

    def install_kubernetes(self):
        # FIXME(toabctl): we call this already in bootstrap().
        # Need to figure out how to get "r"
        r = self.hardware.execute_ansible_play(self.distro.setup_master_play())
        # TODO(jhesketh): Figure out a better way to get ansible output/results
        join_command = \
            r.host_ok[list(r.host_ok.keys())[0]][-1]._result['stdout']

        self.hardware.execute_ansible_play(
            self.distro.join_workers_to_master(join_command))

        self.hardware.execute_ansible_play(
            self.distro.fetch_kubeconfig(self.workspace.working_dir))

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


class DeploySUSE():
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                           '../../'))

    def copy_needed_files_master(self):
        # Temporary workaround for mitogen failing to copy files or templates.
        tasks = []

        tasks.append(
            dict(
                name="Create /root/.setup-kube dir",
                action=dict(
                    module='file',
                    args=dict(
                        path="/root/.setup-kube",
                        state="directory"
                    )
                )
            )
        )

        cluster_psp_file = os.path.join(
            self.basedir, 'assets/cluster-psp.yaml')
        tasks.append(
            dict(
                name="Copy cluster-psp.yaml",
                action=dict(
                    module='copy',
                    args=dict(
                        src=cluster_psp_file,
                        dest="/root/.setup-kube/"
                    )
                )
            )
        )

        kubeadm_init_file = os.path.join(
            self.basedir, 'assets/kubeadm-init-config.yaml.j2')
        tasks.append(
            dict(
                name="Copy kubeadm-init-config.yaml",
                action=dict(
                    module='template',
                    args=dict(
                        src=kubeadm_init_file,
                        dest="/root/.setup-kube/kubeadm-init-config.yaml"
                    )
                )
            )
        )

        play_source = dict(
            name="Copy needed files for master",
            hosts="first_master",
            tasks=tasks,
            gather_facts="no",
            # Only one host, so more helpful to see current step with linear
            # strategy
            strategy="linear",
        )
        return play_source

    def setup_master_play(self):
        tasks = []

        # init config file has extra API server args to enable psp access
        # control
        init_command = (
            "kubeadm init "
            "--config=/root/.setup-kube/kubeadm-init-config.yaml"
        )
        tasks.append(
            dict(
                name="Run 'kubeadm init'",
                action=dict(
                    module='shell',
                    args=dict(
                        # for idempotency, do not run init if docker is already
                        # running kube resources
                        cmd=("if ! docker ps -a | grep -q kube; "
                             "then %s ; fi" % init_command)
                    )
                )
            )
        )

        grouped_commands = [
            "mkdir -p /root/.kube",
            "ln -f -s /etc/kubernetes/admin.conf /root/.kube/config",
            "kubectl completion bash > ~/.kube/kubectl-completion.sh",
            "chmod +x ~/.kube/kubectl-completion.sh",
        ]
        tasks.append(
            dict(
                name="Set up root user as Kubernetes administrator",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd=" && ".join(grouped_commands)
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Wait until kubernetes is ready",
                action=dict(
                    module='command',
                    args=dict(
                        cmd="kubectl get nodes",
                    )
                ),
                retries=20,
                delay=5,
                register="cmd_result",
                until="cmd_result.rc == 0",
            )
        )

        tasks.append(
            dict(
                name="Set up default cluster pod security policies (PSPs)",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd=("kubectl apply "
                             "-f /root/.setup-kube/cluster-psp.yaml")
                    )
                )
            )
        )

        # print("setup cluster overlay network CNI")
        # tasks.append(
        #     dict(
        #         action=dict(
        #             module='shell',
        #             args=dict(
        #                 cmd=("kubectl apply -f "
        #                      "https://docs.projectcalico.org/"
        #                      "manifests/calico.yaml")
        #             )
        #         )
        #     )
        # )

        # print("setup cluster overlay network CNI")
        # tasks.append(
        #     dict(
        #         action=dict(
        #             module='shell',
        #             args=dict(
        #                 cmd=("kubectl apply -f "
        #                      "https://raw.githubusercontent.com/coreos/"
        #                      "flannel/master/Documentation/kube-flannel.yml")
        #             )
        #         )
        #     )
        # )

        tasks.append(
            dict(
                name="Get join command",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd=("kubeadm token create --print-join-command "
                             "| grep 'kubeadm join'")
                    )
                )
            )
        )

        play_source = dict(
            name="Set up master",
            hosts="first_master",
            tasks=tasks,
            gather_facts="no",
            # Only one host, so more helpful to see current step with linear
            # strategy
            strategy="mitogen_linear",
        )
        return play_source

    def join_workers_to_master(self, join_command):
        tasks = []

        tasks.append(
            dict(
                name="Join node to Kubernetes cluster",
                action=dict(
                    module='shell',
                    args=dict(
                        # for idempotency, do not run join if docker is already
                        # running kube resources
                        cmd=("if ! docker ps -a | grep -q kube; "
                             "then %s ; fi" % join_command)
                    )
                )
            )
        )

        play_source = dict(
            name="Enroll workers",
            hosts="worker",
            tasks=tasks,
            gather_facts="no",
            strategy=(
                "mitogen_free"
                if config._USE_FREE_STRATEGY else "mitogen_linear"
            ),
        )
        return play_source

    def fetch_kubeconfig(self, destination):
        tasks = []

        tasks.append(
            dict(
                name="Download kubeconfig",
                action=dict(
                    module='fetch',
                    args=dict(
                        src="/root/.kube/config",
                        dest="%s/kubeconfig" % destination,
                        flat=True
                    )
                )
            )
        )

        play_source = dict(
            name="Download kubeconfig",
            hosts="first_master",
            tasks=tasks,
            gather_facts="no",
            # Only one host, so more helpful to see current step with linear
            # strategy
            strategy="mitogen_linear",
        )
        return play_source
