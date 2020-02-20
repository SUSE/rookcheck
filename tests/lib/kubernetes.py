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

from tests import config


class Deploy(ABC):
    @abstractmethod
    def install_kubeadm_play(self):
        pass


class DeploySUSE(Deploy):
    basedir = os.path.dirname(__file__)

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
        extra_args_file = os.path.join(self.basedir, 'assets/KUBELET_EXTRA_ARGS')
        tasks.append(
            dict(
                action=dict(
                    module='copy',
                    args=dict(
                        src=extra_args_file,
                        dest="/root/"
                    )
                )
            )
        )

        play_source = dict(
                name="Prepare nodes",
                hosts="all",
                tasks=tasks
            )
        return play_source

class VanillaKubernetes():
    def __init__(self, hardware):
        self.hardware = hardware
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

    def install_kubeadm(self):
        if config.DISTRO == 'SUSE':
            d = DeploySUSE()
        else:
            raise Exception("OS yet to be implemented/unsupport.")

        r = self.hardware.execute_ansible_play(d.install_kubeadm_play())

        if r.host_failed or r.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
