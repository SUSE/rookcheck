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


class SLES_CaaSP(base.Distro):
    def bootstrap_play(self):
        tasks = []

        # First task will be installing the correct repositories for Skuba.
        # SLES doesn't have any respositories configured by default. We either
        # need to register the node against SCC or add the repos assuming we
        # have access to IBS.

        # "caasp_devel": 
        #         "http://download.suse.de/ibs/Devel:/CaaSP:/4.0/SLE_15_SP1/",
        # "suse_ca": 
        #         "http://download.suse.de/ibs/SUSE:/CA/SLE_15_SP1/",
        # "sle_server_pool": 
        #         "http://download.suse.de/ibs/SUSE/Products/SLE-Product-SLES/"
        #         "15-SP1/x86_64/product/",
        # "basesystem_pool": 
        #         "http://download.suse.de/ibs/SUSE/Products/"
        #         "SLE-Module-Basesystem/15-SP1/x86_64/product/",
        # "containers_pool": 
        #         "http://download.suse.de/ibs/SUSE/Products/"
        #         "SLE-Module-Containers/15-SP1/x86_64/product/",
        # "serverapps_pool": 
        #         "http://download.suse.de/ibs/SUSE/Products/"
        #         "SLE-Module-Server-Applications/15-SP1/x86_64/product/",
        # "sle_server_updates": 
        #         "http://download.suse.de/ibs/SUSE/Updates/"
        #         "SLE-Product-SLES/15-SP1/x86_64/update/",
        # "basesystem_updates": 
        #         "http://download.suse.de/ibs/SUSE/Updates/"
        #         "SLE-Module-Basesystem/15-SP1/x86_64/update/",
        # "containers_updates": 
        #         "http://download.suse.de/ibs/SUSE/Updates/"
        #         "SLE-Module-Containers/15-SP1/x86_64/update/",
        # "serverapps_updates": 
        #         "http://download.suse.de/ibs/SUSE/Updates/"
        #         "SLE-Module-Server-Applications/15-SP1/x86_64/update/"

        
        play_source = dict(
            name="Prepare nodes",
            hosts="all",
            tasks=tasks,
            gather_facts="no",
            strategy="mitogen_free",
        )
        return play_source
