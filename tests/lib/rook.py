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
