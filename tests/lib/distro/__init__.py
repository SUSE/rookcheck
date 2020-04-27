# Copyright (c) 2020 SUSE LINUX GmbH
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

"""The Hardware module should take care of the operating system abstraction
through images.
libcloud will provide a common set of cloud-agnostic objects such as Node[s]
We might extend the Node object to have an easy way to run arbitrary commands
on the node such as Node.execute().
There will be a challenge where those arbitrary commands differ between OS's;
this is an abstraction that is not yet well figured out, but will likely
take the form of cloud-init or similar bringing the target node to an
expected state."""

from tests import config
from tests.lib.distro.opensuse import openSUSE_k8s
from tests.lib.distro.sles import SLES_CaaSP


def get_distro():
    if config.DISTRO == 'openSUSE_k8s':
        return openSUSE_k8s
    elif config.DISTRO == 'SLES_CaaSP':
        return SLES_CaaSP
    else:
        raise Exception('Unknown distro {}'.format(config.DISTRO))
