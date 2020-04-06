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

import os
import re
import time

from tests.lib import common


class BuildRook():
    def build_play(self, builddir):
        tasks = []

        tasks.append(
            dict(
                name="Download go",
                action=dict(
                    module='get_url',
                    args=dict(
                        url="https://dl.google.com/go/"
                            "go1.13.9.linux-amd64.tar.gz",
                        dest="%s/go-amd64.tar.gz" % builddir
                    )
                )
            )
        )
        tasks.append(
            dict(
                name="Unpack go",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="tar -C {builddir} -xzf "
                            "{builddir}/go-amd64.tar.gz".format(
                                builddir=builddir)
                    )
                )
            )
        )

        # TODO(jhesketh): Allow setting rook version
        tasks.append(
            dict(
                name="Checkout rook",
                action=dict(
                    module='git',
                    args=dict(
                        repo="https://github.com/rook/rook.git",
                        dest="%s/src/github.com/rook/rook" % builddir,
                        # version=...
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Make rook",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="PATH={builddir}/go/bin:$PATH GOPATH={builddir} "
                            "make --directory="
                            "'{builddir}/src/github.com/rook/rook' "
                            "-j BUILD_REGISTRY='rook-build' IMAGES='ceph' "
                            "build".format(builddir=builddir)
                    )
                )
            )
        )

        tasks.append(
            dict(
                name="Tag image",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd='docker tag "rook-build/ceph-amd64" '
                            'rook/ceph:master'
                    )
                )
            )
        )

        # TODO(jhesketh): build arch may differ
        tasks.append(
            dict(
                name="Save image tar",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd='docker save rook-build/ceph-amd64 | '
                            'gzip > %s/rook-ceph.tar.gz' % builddir
                    )
                )
            )
        )

        play_source = dict(
            name="Build rook",
            hosts="localhost",
            tasks=tasks,
            gather_facts="no",
            # strategy="free",
        )
        return play_source

    def upload_image_play(self, buildpath):
        tasks = []

        tasks.append(
            dict(
                name="Copy Rook Ceph image to cluster nodes",
                action=dict(
                    module='copy',
                    args=dict(
                        src=os.path.join(buildpath, "rook-ceph.tar.gz"),
                        dest="/root/.images/"
                    )
                )
            )
        )

        # TODO(jhesketh): build arch may differ
        tasks.append(
            dict(
                name="Load rook ceph image",
                action=dict(
                    module='shell',
                    args=dict(
                        cmd='docker load '
                            '--input /root/.images/rook-ceph.tar.gz'
                    )
                )
            )
        )

        play_source = dict(
            name="Upload rook image",
            hosts="all",
            tasks=tasks,
            gather_facts="no",
            strategy="free",
        )
        return play_source


class RookCluster():
    def __init__(self, kubernetes):
        self.kubernetes = kubernetes
        self.toolbox_pod = None
        self.ceph_dir = None
        print("rook init")
        print(self)
        print(self.kubernetes)
        print(self.kubernetes.hardware)

    def destroy(self, skip=True):
        print("rook destroy")
        print(self)
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

    def build_rook(self):
        self.builddir = os.path.join(
            self.kubernetes.hardware.working_dir, 'rook_build')
        os.mkdir(self.builddir)

        d = BuildRook()
        r = self.kubernetes.hardware.execute_ansible_play(
            d.build_play(self.builddir))

        if r.host_failed or r.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

        r2 = self.kubernetes.hardware.execute_ansible_play(
            d.upload_image_play(self.builddir))

        if r2.host_failed or r2.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")

        self.ceph_dir = os.path.join(
            self.builddir,
            'src/github.com/rook/rook/cluster/examples/kubernetes/ceph'
        )

    def install_rook(self):
        # TODO(jhesketh): We may want to provide ways for tests to override
        #                 these
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'common.yaml'))
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'operator.yaml'))

        # TODO(jhesketh): Check if sleeping is necessary
        time.sleep(10)

        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'cluster.yaml'))
        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'toolbox.yaml'))
        time.sleep(3)

        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'csi/rbd/storageclass.yaml'))

        print("Wait for OSD prepare to complete (this may take a while...)")
        pattern = re.compile(r'.*rook-ceph-osd-prepare.*Completed')

        common.wait_for_result(
            self.kubernetes.kubectl, "--namespace rook-ceph get pods",
            matcher=common.regex_count_matcher(pattern, 3),
            attempts=90, interval=10)

        self.kubernetes.kubectl_apply(
            os.path.join(self.ceph_dir, 'filesystem.yaml'))

        print("Wait for 2 mdses to start")
        pattern = re.compile(r'.*rook-ceph-mds-myfs.*Running')

        common.wait_for_result(
            self.kubernetes.kubectl, "--namespace rook-ceph get pods",
            matcher=common.regex_count_matcher(pattern, 2),
            attempts=20, interval=5)

        print("Wait for myfs to be active")
        pattern = re.compile(r'.*active')

        common.wait_for_result(
            self.execute_in_ceph_toolbox, "ceph fs status myfs",
            matcher=common.regex_matcher(pattern),
            attempts=20, interval=5)

    def execute_in_ceph_toolbox(self, command):
        if not self.toolbox_pod:
            self.toolbox_pod = self.kubernetes.get_pod_by_app_label(
                "rook-ceph-tools")

        return self.kubernetes.execute_in_pod(command, self.toolbox_pod)
