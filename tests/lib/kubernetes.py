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


class Deploy(ABC):
    @abstractmethod
    def something(self):
        pass


class DeploySUSE(Deploy):
    pass


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

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
