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
import time


class BuildRook():
    def build_play(self, builddir):
        tasks = []

        print("Checkout rook")
        # TODO(jhesketh): Allow setting rook version
        tasks.append(
            dict(
                action=dict(
                    module='git',
                    args=dict(
                        repo="https://github.com/rook/rook.git",
                        dest="%s/src/github.com/rook/rook" % builddir,
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
                        cmd="GOPATH={builddir} make --directory='{builddir}/src/github.com/rook/rook' -j BUILD_REGISTRY='rook-build' IMAGES='ceph' build".format(builddir=builddir)
                    )
                )
            )
        )

        print("tag image")
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd='docker tag "rook-build/ceph-amd64" rook/ceph:master'
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
                        cmd='docker save rook-build/ceph-amd64 | gzip > %s/rook-ceph.tar.gz' % builddir
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

    def upload_image_play(self, buildpath):
        tasks = []

        print("Copy Rook Ceph image to cluster nodes")
        tasks.append(
            dict(
                action=dict(
                    module='copy',
                    args=dict(
                        src=os.path.join(buildpath, "rook-ceph.tar.gz"),
                        dest="/root/.images/"
                    )
                )
            )
        )

        print("load rook ceph image")
        # TODO(jhesketh): build arch may differ
        tasks.append(
            dict(
                action=dict(
                    module='shell',
                    args=dict(
                        cmd='docker load --input /root/.images/rook-ceph.tar.gz'
                    )
                )
            )
        )

        play_source = dict(
            name="Build rook",
            hosts="all",
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

    def install_rook(self):
        # TODO(jhesketh): We may want to provide ways for tests to override these
        ceph_dir = os.path.join(self.builddir, 'src/github.com/rook/rook/cluster/examples/kubernetes/ceph')
        self.kubernetes.kubectl_apply(os.path.join(ceph_dir, 'common.yaml'))
        self.kubernetes.kubectl_apply(os.path.join(ceph_dir, 'operator.yaml'))
        # TODO(jhesketh): Check if sleeping is necessary
        time.sleep(10)
        self.kubernetes.kubectl_apply(os.path.join(ceph_dir, 'cluster.yaml'))
        self.kubernetes.kubectl_apply(os.path.join(ceph_dir, 'toolbox.yaml'))
        time.sleep(3)
        self.kubernetes.kubectl_apply(os.path.join(ceph_dir, 'csi/rbd/storageclass.yaml'))


        ##### TODO:


        # # Wait for all osd prepare pods to be completed
        # num_osd_nodes=$((NUM_WORKERS + NUM_MASTERS))
        # wait_for "Ceph to be installed" ${INSTALL_TIMEOUT} \
        # "[[ \$(kubectl get --namespace ${ROOK_NAMESPACE} pods 2>&1 | grep -c 'rook-ceph-osd-prepare.*Completed') -eq $num_osd_nodes ]]"

        # # osd_count="$(kubectl --namespace ${ROOK_NAMESPACE} get pod | grep -c osd-[[:digit:]] || true)"


        # echo ''
        # echo 'SETTING UP CEPHFS AND INSTALLING MDSES'
        # ( cd ${ROOK_CONFIG_DIR}/ceph
        # kubectl create -f filesystem.yaml
        # )

        # # Wait for 2 mdses to start
        # wait_for "mdses to start" 90 \
        # "kubectl get --namespace ${ROOK_NAMESPACE} pods | grep -q 'rook-ceph-mds-myfs-b.*Running'"



        # wait_for "myfs to be active" 60 \
        # "exec_in_toolbox_pod 'ceph fs status myfs 2>&1 | grep -q active' &> /dev/null"
        # # must use 'bash -c "...stuff..."' to use pipes within kubectl exec
        # # for whatever reason, 'ceph fs status' returns info on stderr ... ?
        # # above will print 'command terminated with exit code #' if stderr isn't sent to /dev/null



        # ...

        # kubectl --namespace rook-ceph exec "rook-ceph-tools-7f96779fb9-bx4kl" -- bash -c "ceph fs status myfs"
