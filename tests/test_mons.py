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

import logging
import os
import pytest
import yaml

logger = logging.getLogger(__name__)


# check if rbd service gets started automatically
def test_service_mons(rook_cluster):
    cluster_yaml = os.path.join(rook_cluster.ceph_dir, 'cluster.yaml')
    with open(cluster_yaml, 'r') as f:
        cluster_object = yaml.load(f, Loader=yaml.BaseLoader)
    # get configured number of monitors
    count = cluster_object['spec']['mon']['count']
    count = int(count)
    logger.info("Expecting %d monitors", count)

    # get number of mon-services
    services = rook_cluster.kubernetes.get_services_by_app_label(
        "rook-ceph-mon")

    if count != len(services):
        pytest.fail("Expected %d mon-services but got %d",
                    count, len(services))

    # get number of mon-pods
    pods = rook_cluster.kubernetes.get_pods_by_app_label("rook-ceph-mon")
    if count != len(pods):
        pytest.fail("Expected %d mon-pods but got %d",
                    count, len(pods))
