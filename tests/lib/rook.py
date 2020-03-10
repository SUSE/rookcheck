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

class BuildRook():
    def build_play(self):
        tasks = []

        print("Create temporary builddir")
        tasks.append(
            dict(
                action=dict(
                    module='tempfile',
                    args=dict(
                        state="directory",
                        suffix="build"
                    )
                ),
                register="builddir"
            )
        )

        print("Checkout rook")
        # TODO(jhesketh): Allow setting rook version
        tasks.append(
            dict(
                action=dict(
                    module='git',
                    args=dict(
                        repo="https://github.com/rook/rook.git",
                        dest="{{ builddir.path }}/src/github.com/rook/rook",
                        #version=...
                    )
                )
            )
        )

        print("make rook")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd="GOPATH={{ builddir.path }} make --directory='{{ builddir.path }}/github.com/rook/rook' -j BUILD_REGISTRY='rook-build' IMAGES='ceph' build"
                    )
                )
            )
        )

        print("save image tar")
        # TODO(jhesketh): build arch may differ
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd='docker save rook-build/ceph-amd64 | gzip > {{ builddir.path }}/rook-ceph.tar.gz'
                    )
                )
            )
        )

        play_source = dict(
            name="Build rook",
            hosts="localhost",
            tasks=tasks
        )
        return play_source


class RookCluster():
    def __init__(self, kubernetes):
        self.kubernetes = kubernetes
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
        d = BuildRook()
        r = self.kubernetes.hardware.execute_ansible_play(d.build_play())

        if r.host_failed or r.host_unreachable:
            # TODO(jhesketh): Provide some more useful feedback and/or checking
            raise Exception("One or more hosts failed")
