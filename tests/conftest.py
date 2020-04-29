# Copyright (c) 2019 SUSE LINUX GmbH
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

import logging
import pytest
import threading

from tests import config
from tests.lib.kubernetes.vanilla import Vanilla as Kubernetes
from tests.lib.rook import RookCluster


if config.CLOUD_PROVIDER == 'OPENSTACK':
    from tests.lib.hardware.openstack_libcloud import Hardware as Hardware
else:
    raise Exception("Cloud provider '{}' not yet supported by "
                    "rookcheck".format(config.CLOUD_PROVIDER))


logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def hardware():
    # NOTE(jhesketh): The Hardware() object is expected to take care of any
    # cloud provider abstraction. It primarily does this via libcloud.
    with Hardware() as hardware:
        hardware.boot_nodes()
        hardware.prepare_nodes()
        yield hardware


@pytest.fixture(scope="module")
def kubernetes(hardware):
    # NOTE(jhesketh): We can either choose which Kubernetes class to use here
    # or we can have a master class that makes the decision based off the
    # config.
    # If we implement multiple Kubernetes distributions (eg upstream vs skuba
    # etc), we should do them from an ABC so to ensure the interfaces are
    # correct.
    with Kubernetes(hardware) as kubernetes:
        kubernetes.install_kubernetes()
        yield kubernetes


@pytest.fixture(scope="module")
def linear_rook_cluster(kubernetes):
    # (See above re implementation options)
    # This method shows how fixture inheritance can be used to manage the
    # infrastructure. It also builds things in order, the below rook_cluster
    # fixture is preferred as it will build rook locally in a thread while
    # waiting on the infrastructure
    with RookCluster(kubernetes) as rook_cluster:
        rook_cluster.build_rook()
        rook_cluster.install_rook()
        yield rook_cluster


@pytest.fixture(scope="module")
def rook_cluster():
    with Hardware() as hardware:
        with Kubernetes(hardware) as kubernetes:
            with RookCluster(kubernetes) as rook_cluster:
                logger.info("Starting rook build in a thread")
                build_thread = threading.Thread(target=rook_cluster.build_rook)
                build_thread.start()

                # build rook thread
                hardware.boot_nodes()
                hardware.prepare_nodes()
                kubernetes.install_kubernetes()

                logger.info("Re-joining rook build thread")
                build_thread.join()
                # NOTE(jhesketh): The upload is very slow.. may want to
                #                 consider how to do this in a thread too but
                #                 is more complex with ansible.
                rook_cluster.upload_rook_image()
                rook_cluster.install_rook()

                yield rook_cluster
