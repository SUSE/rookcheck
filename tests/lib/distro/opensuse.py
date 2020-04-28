# Copyright (c) 2020 SUSE LINUX GmbH
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

# The Hardware module should take care of the operating system abstraction
# through images.
# libcloud will provide a common set of cloud-agnostic objects such as Node[s]
# We might extend the Node object to have an easy way to run arbitrary commands
# on the node such as Node.execute().
# There will be a challenge where those arbitrary commands differ between OS's;
# this is an abstraction that is not yet well figured out, but will likely
# take the form of cloud-init or similar bringing the target node to an
# expected state.

from tests.lib.distro import base


class openSUSE_k8s(base.Distro):
    def bootstrap_play(self):
        tasks = []

        tasks.append(
            dict(
                name="Installing dependencies",
                action=dict(
                    module='zypper',
                    args=dict(
                        name=['bash-completion',
                              'ca-certificates',
                              'conntrack-tools',
                              'curl',
                              'docker',
                              'ebtables',
                              'ethtool',
                              'lvm2',
                              'lsof',
                              'ntp',
                              'socat',
                              'tree',
                              'vim',
                              'wget',
                              'xfsprogs'],
                        state='present',
                        extra_args_precommand='--non-interactive '
                                              '--gpg-auto-import-keys',
                        update_cache='yes',
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Updating kernel",
                action=dict(
                    module='zypper',
                    args=dict(
                        name='kernel-default',
                        state='latest',
                        extra_args_precommand='--non-interactive '
                                              '--gpg-auto-import-keys',
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Removing anti-dependencies",
                action=dict(
                    module='zypper',
                    args=dict(
                        name='firewalld',
                        state='absent',
                        extra_args_precommand='--non-interactive '
                                              '--gpg-auto-import-keys',
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Enabling docker",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="systemctl enable --now docker",
                    )
                )
            )
        )

        # TODO(jhesketh): These commands are lifted from dev-rook-ceph. However
        # it appears that the sysctl settings are reset after reboot so they
        # may not be useful here.
        tasks.append(
            dict(
                name="Raising max open files",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="sysctl -w fs.file-max=1200000",
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Minimize swappiness",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="sysctl -w vm.swappiness=0",
                    )
                )
            )
        )

        # TODO(jhesketh): Figure out if this is appropriate for all OpenStack
        #                 clouds.
        config = "\nIPADDR_0={{ ansible_host }}/32"
        config += "\nLABEL_0=Floating\n"
        tasks.append(
            dict(
                name="Add floating IP to eth0",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd='printf "%s" >> /etc/sysconfig/network/ifcfg-eth0'
                            % config,
                    )
                )
            )
        )

        # Alternate approach that likely doesn't require setting --node-ip with
        # kubelet (as it'll default to the floating ip).
        # Set static IP to be the floating,
        # add second IP for the internal network,
        # Create default route,
        # Set up DNS again

        tasks.append(
            dict(
                name="Reboot nodes",
                action=dict(
                    module='reboot',
                )
            )
        )

        tasks.append(
            dict(
                name="Setting iptables on nodes to be permissive",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="iptables -I INPUT -j ACCEPT && "
                            "iptables -P INPUT ACCEPT",
                    )
                )
            )
        )

        play_source = dict(
            name="Prepare nodes",
            hosts="all",
            tasks=tasks,
            gather_facts="no",
            strategy="mitogen_free",
        )
        return play_source
