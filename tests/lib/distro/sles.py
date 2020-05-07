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

from tests import config
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
            strategy=(
                "mitogen_free"
                if config._USE_FREE_STRATEGY else "mitogen_linear"
            ),
        )
        return play_source
