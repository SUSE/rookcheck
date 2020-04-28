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

# The Hardware module should take care of the operating system abstraction
# through images.
# libcloud will provide a common set of cloud-agnostic objects such as Node[s]
# We might extend the Node object to have an easy way to run arbitrary commands
# on the node such as Node.execute().
# There will be a challenge where those arbitrary commands differ between OS's;
# this is an abstraction that is not yet well figured out, but will likely
# take the form of cloud-init or similar bringing the target node to an
# expected state.

from abc import ABC, abstractmethod
import os
import tempfile
import uuid

import paramiko.rsakey

from tests.lib.ansible_helper import AnsibleRunner
from tests import config


class HardwareBase(ABC):
    """
    Base Hardware class
    """
    def __init__(self):
        # Boot nodes
        print("boot nodes")
        print(self)
        self.nodes = {}
        self.hardware_uuid = str(uuid.uuid4())[:8]
        self.conn = self.get_connection()

        # NOTE(jhesketh): The working_dir is never cleaned up. This is somewhat
        # deliberate to keep the private key if it is needed for debugging.
        self.working_dir = tempfile.mkdtemp(
            prefix="%s%s_" % (config.CLUSTER_PREFIX, self.hardware_uuid))

        self.sshkey_name = None
        self.pubkey = None
        self.private_key = None

        self.ansible_runner = None
        self._ansible_runner_nodes = None

    @abstractmethod
    def generate_keys(self):
        """
        Generatees a public and private key
        """
        key = paramiko.rsakey.RSAKey.generate(2048)
        self.private_key = os.path.join(self.working_dir, 'private.key')
        with open(self.private_key, 'w') as key_file:
            key.write_private_key(key_file)
        os.chmod(self.private_key, 0o400)

        self.sshkey_name = \
            "%s%s_key" % (config.CLUSTER_PREFIX, self.hardware_uuid)
        self.pubkey = "%s %s" % (key.get_name(), key.get_base64())

    @abstractmethod
    def get_connection(self):
        pass

    @abstractmethod
    def boot_nodes(self, masters: int = 1, workers: int = 2, offset: int = 0):
        pass

    @abstractmethod
    def prepare_nodes(self):
        pass

    def execute_ansible_play(self, play_source):
        if not self.ansible_runner or self._ansible_runner_nodes != self.nodes:
            # Create a new AnsibleRunner if the nodes dict has changed (to
            # generate a new inventory).
            self.ansible_runner = AnsibleRunner(self.nodes, self.working_dir)
            self._ansible_runner_nodes = self.nodes.copy()

        return self.ansible_runner.run_play(play_source)
