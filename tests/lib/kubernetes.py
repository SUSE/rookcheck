# Copyright (c) 2019 SUSE LINUX GmbH
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


# This module should take care of deploying kubernetes. There will likely be
# multiple variations of an abstract base class to do so. However, the
# implementation may need to require a certain base OS. For example, skuba
# would require SLE and can raise an exception if that isn't provided.

from abc import ABC, abstractmethod
import os
import stat
import wget

import kubernetes
from tests import config


class Deploy(ABC):
    @abstractmethod
    def install_kubeadm_play(self):
        pass


class DeploySUSE(Deploy):
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))

    def install_kubeadm_play(self):
        tasks = []

        print("start required IPVS kernel modules")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="modprobe ip_vs ; modprobe ip_vs_rr ; "
                            "modprobe ip_vs_wrr ; modprobe ip_vs_sh",
                    )
                )
            )
        )

        print("download and install crictl")
        grouped_commands = [
            "wget https://github.com/kubernetes-sigs/cri-tools/releases/download/{CRICTL_VERSION}/crictl-{CRICTL_VERSION}-linux-amd64.tar.gz",
            "tar -C /usr/bin -xf crictl-{CRICTL_VERSION}-linux-amd64.tar.gz",
            "chmod +x /usr/bin/crictl",
            "rm crictl-{CRICTL_VERSION}-linux-amd64.tar.gz",
        ]
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd=" && ".join(grouped_commands).format(
                            CRICTL_VERSION=config.CRICTL_VERSION
                        )
                    )
                )
            )
        )

        print("downloading and installing kubeadm binaries")
        for binary in ['kubeadm', 'kubectl', 'kubelet']:
            grouped_commands = [
                "curl -LO https://storage.googleapis.com/kubernetes-release/release/{K8S_VERSION}/bin/linux/amd64/{binary}",
                "chmod +x {binary}",
                "mv {binary} /usr/bin/"
            ]
            tasks.append(
                dict(
                    action=dict(
                        module='shell',
                        args=dict(
                            cmd=" && ".join(grouped_commands).format(
                                K8S_VERSION=config.K8S_VERSION,
                                CRICTL_VERSION=config.CRICTL_VERSION,
                                binary=binary
                            )
                        )
                    )
                )
            )

        print("download and install CNI plugins")
        # CNI plugins are required for most network addons
        # https://github.com/containernetworking/plugins/releases
        CNI_VERSION = "v0.7.5"
        grouped_commands = [
            "rm -f cni-plugins-amd64-{CNI_VERSION}.tgz*",
            "wget https://github.com/containernetworking/plugins/releases/download/{CNI_VERSION}/cni-plugins-amd64-{CNI_VERSION}.tgz",
            "mkdir -p /opt/cni/bin",
            "tar -C /opt/cni/bin -xf cni-plugins-amd64-{CNI_VERSION}.tgz",
            "rm cni-plugins-amd64-{CNI_VERSION}.tgz"
        ]
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd=" && ".join(grouped_commands).format(
                            CNI_VERSION=CNI_VERSION,
                            CRICTL_VERSION=config.CRICTL_VERSION
                        )
                    )
                )
            )
        )

        print("setting up kubelet service")
        service_file = os.path.join(self.basedir, 'assets/kubelet.service')
        tasks.append(
            dict(
                action=dict(
                    module='copy',
                    args=dict(
                        src=service_file,
                        dest="/usr/lib/systemd/system/"
                    )
                )
            )
        )
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="systemctl enable kubelet"
                    )
                )
            )
        )

        print("disable apparmor")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="systemctl disable apparmor --now || true"
                    )
                )
            )
        )

        print("copy config files to cluster")
        extra_args_file = os.path.join(self.basedir, 'assets/KUBELET_EXTRA_ARGS.j2')
        tasks.append(
            dict(
                action=dict(
                    module='template',
                    args=dict(
                        src=extra_args_file,
                        dest="/root/KUBELET_EXTRA_ARGS"
                    )
                )
            )
        )

        play_source = dict(
            name="Install kubeadm",
            hosts="all",
            tasks=tasks
        )
        return play_source

    def setup_master_play(self):
        tasks = []

        print("copy config files to cluster")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        # for idempotency, do not run init if docker is already running kube resources
                        cmd="mkdir /root/.setup-kube"
                    )
                )
            )
        )
        kubeadm_init_file = os.path.join(self.basedir, 'assets/kubeadm-init-config.yaml.j2')
        tasks.append(
            dict(
                action=dict(
                    module='template',
                    args=dict(
                        src=kubeadm_init_file,
                        dest="/root/.setup-kube/kubeadm-init-config.yaml"
                    )
                )
            )
        )
        cluster_psp_file = os.path.join(self.basedir, 'assets/cluster-psp.yaml')
        tasks.append(
            dict(
                action=dict(
                    module='copy',
                    args=dict(
                        src=cluster_psp_file,
                        dest="/root/.setup-kube/"
                    )
                )
            )
        )

        print("Run 'kubeadm init' on first master")
        # init config file has extra API server args to enable psp access control
        init_command = "kubeadm init --config=/root/.setup-kube/kubeadm-init-config.yaml"
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        # for idempotency, do not run init if docker is already running kube resources
                        cmd="if ! docker ps -a | grep -q kube; then {init_command} ; fi".format(init_command=init_command)
                    )
                )
            )
        )

        print("setup root user on first master as Kubernetes administrator")
        grouped_commands = [
            "mkdir -p /root/.kube",
            "ln -f -s /etc/kubernetes/admin.conf /root/.kube/config",
            "kubectl completion bash > ~/.kube/kubectl-completion.sh",
            "chmod +x ~/.kube/kubectl-completion.sh",
        ]
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd=" && ".join(grouped_commands)
                    )
                )
            )
        )

        # FIXME(jhesketh): Wait for services to be ready
        # wait_for "kubernetes master services to be ready" 90 "${OCTOPUS} --host-groups first_master run \
        #  'kubectl get nodes'"
        tasks.append(
            dict(
                action=dict(
                    module='pause',
                    args=dict(
                        seconds=90
                    )
                )
            )
        )

        print("setup default cluster pod security policies (PSPs)")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        # for idempotency, do not run init if docker is already running kube resources
                        cmd="kubectl apply -f /root/.setup-kube/cluster-psp.yaml"
                    )
                )
            )
        )

        print("setup cluster overlay network CNI")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        # for idempotency, do not run init if docker is already running kube resources
                        cmd="kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml"
                    )
                )
            )
        )

        print("get join command")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        # for idempotency, do not run init if docker is already running kube resources
                        cmd="kubeadm token create --print-join-command | grep 'kubeadm join'"
                    )
                )
            )
        )

        play_source = dict(
                name="Set up master",
                hosts="first_master",
                tasks=tasks
            )
        return play_source

    def join_workers_to_master(self, join_command):
        tasks = []

        print("join worker nodes to Kubernetes cluster")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        # for idempotency, do not run init if docker is already running kube resources
                        cmd="if ! docker ps -a | grep -q kube; then {join_command} ; fi".format(join_command=join_command)
                    )
                )
            )
        )

        play_source = dict(
            name="Enroll workers",
            hosts="worker",
            tasks=tasks
        )
        return play_source

    def fetch_kubeconfig(self, destination):
        tasks = []

        print("download kubeconfig from master")
        tasks.append(
            dict(
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
            tasks=tasks
        )
        return play_source

class VanillaKubernetes():
    def __init__(self, hardware):
        self.hardware = hardware
        self.kubeconfig = None
        self.v1 = None
        print("kube init")
        print(self)
        print(self.hardware)

    def destroy(self, skip=True):
        print("kube destroy")
        print(self)
        if skip:
            # We can skip in most cases since the nodes themselves will be
            # destroyed instead.
            return
        # TODO(jhesketh): Uninstall kubernetes
        pass

    def install_kubernetes(self):
        if config.DISTRO == 'SUSE':
            d = DeploySUSE()
        else:
            raise Exception("OS yet to be implemented/unsupport.")

        r = self.hardware.execute_ansible_play(d.install_kubeadm_play())

        if r.host_failed or r.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

        r2 = self.hardware.execute_ansible_play(d.setup_master_play())

        if r2.host_failed or r2.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

        # TODO(jhesketh): Figure out a better way to get ansible output/results
        join_command = r2.host_ok[list(r2.host_ok.keys())[0]][-1]._result['stdout']

        r3 = self.hardware.execute_ansible_play(
            d.join_workers_to_master(join_command))

        if r3.host_failed or r3.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

        r4 = self.hardware.execute_ansible_play(
            d.fetch_kubeconfig(self.hardware.working_dir))

        if r4.host_failed or r4.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

        self.kubeconfig = os.path.join(self.hardware.working_dir, 'kubeconfig')
        self.download_kubectl()
        self.untaint_master()

    def configure_kubernetes_client(self):
        kubernetes.config.load_kube_config(self.kubeconfig)
        self.v1 = kubernetes.client.CoreV1Api()

    def create_from_yaml(self, yaml_file):
        # NOTE(jhesketh): This works for most things, but expects CRD's to be
        #                 available via the kubernetes-client python. As such
        #                 for most manifests it will be easier to use kubectl
        #                 directly (helper function).
        kubernetes.utils.create_from_yaml(self.v1.api_client, yaml_file)

    def download_kubectl(self):
        # Download specific kubectl version
        # TODO(jhesketh): Allow setting version
        self.kubectl_exec = os.path.join(self.hardware.working_dir, 'kubeadm')
        wget.download(
            "https://storage.googleapis.com/kubernetes-release/release/v1.17.3/bin/linux/amd64/kubectl",
            self.kubectl_exec
        )
        st = os.stat(self.kubectl_exec)
        os.chmod(self.kubectl_exec, st.st_mode | stat.S_IEXEC)

    def kubectl(self, command):
        # Execute kubectl command
        return os.system(
            " ".join([self.kubectl_exec, "--kubeconfig", self.kubeconfig, command]))

    def kubectl_apply(self, yaml_file):
        return self.kubectl("apply -f %s" % yaml_file)

    def untaint_master(self):
        self.kubectl("taint nodes --all node-role.kubernetes.io/master-")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
