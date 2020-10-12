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
import os
import pytest
import threading

from tests.config import settings, converter
from tests.lib import common
from tests.lib.workspace import Workspace


if settings.HARDWARE_PROVIDER.upper() == 'OPENSTACK':
    from tests.lib.hardware.openstack_sdk import Hardware as Hardware  # type: ignore  # noqa: E501
elif settings.HARDWARE_PROVIDER.upper() == 'LIBVIRT':
    from tests.lib.hardware.libvirt import Hardware as Hardware  # type: ignore
elif settings.HARDWARE_PROVIDER.upper() == 'AWS_EC2':
    from tests.lib.hardware.aws_ec2 import Hardware as Hardware  # type: ignore
else:
    raise Exception("Hardware provider '{}' not yet supported by "
                    "rookcheck".format(settings.HARDWARE_PROVIDER))


if settings.DISTRO == 'SLES_CaaSP':
    from tests.lib.kubernetes.caasp import CaaSP as Kubernetes
    from tests.lib.rook.ses import RookSes as RookCluster
else:
    from tests.lib.kubernetes.vanilla import Vanilla as Kubernetes  # type: ignore  # noqa: E501
    from tests.lib.rook.upstream import RookCluster as RookCluster  # type: ignore  # noqa: E501

logger = logging.getLogger(__name__)

# NOTE(jhesketh): Important! When creating a fixture that uses a context
#                 manager, the __exit__ method is not called if the object is
#                 unabled to be instantiated. In other words, if __init__ fails
#                 then no cleanup can occur.
#                 Therefore, be careful when creating fixtures to not put
#                 anything particularly time consuming, expensive, or prone to
#                 failure in the constructor. Instead, move them into a
#                 separate bootstrapping so that any failures to create
#                 resources can still be cleaned up.


def _print_config():
    logger.info("#"*120)
    logger.info("# Rookcheck Settings:")
    logger.info("# ===================")
    logger.info(f"# ROOKCHECK_CLUSTER_PREFIX={settings.CLUSTER_PREFIX}")
    logger.info(f"# ROOKCHECK_WORKSPACE_DIR={settings.WORKSPACE_DIR}")
    logger.info(f"# ROOKCHECK_NUMBER_MASTERS={settings.NUMBER_MASTERS}")
    logger.info(f"# ROOKCHECK_NUMBER_WORKERS={settings.NUMBER_WORKERS}")
    logger.info(
        f"# ROOKCHECK_WORKER_INITIAL_DATA_DISKS="
        f"{settings.WORKER_INITIAL_DATA_DISKS}")
    logger.info(f"# ROOKCHECK_NODE_IMAGE_USER={settings.NODE_IMAGE_USER}")
    logger.info(f"# ROOKCHECK__USE_THREADS={settings._USE_THREADS}")
    logger.info(f"# ROOKCHECK__REMOVE_WORKSPACE={settings._REMOVE_WORKSPACE}")
    logger.info(
        f"# ROOKCHECK__TEAR_DOWN_CLUSTER={settings._TEAR_DOWN_CLUSTER}")
    logger.info(
        f"# ROOKCHECK__TEAR_DOWN_CLUSTER_CONFIRM="
        f"{settings._TEAR_DOWN_CLUSTER_CONFIRM}")
    logger.info(f"# ROOKCHECK__GATHER_LOGS_DIR={settings._GATHER_LOGS_DIR}")
    logger.info(f"# ROOKCHECK_HARDWARE_PROVIDER={settings.HARDWARE_PROVIDER}")
    logger.info("# Hardware provider specific config:")
    logger.info("# ----------------------------------")
    if settings.HARDWARE_PROVIDER.upper() == "OPENSTACK":
        logger.info(
            f"#    ROOKCHECK_OPENSTACK__NODE_IMAGE="
            f"{settings.OPENSTACK.NODE_IMAGE}")
        logger.info(
            f"#    ROOKCHECK_OPENSTACK__NODE_SIZE="
            f"{settings.OPENSTACK.NODE_SIZE}")
        logger.info(
            f"#    ROOKCHECK_OPENSTACK__EXTERNAL_NETWORK="
            f"{settings.OPENSTACK.EXTERNAL_NETWORK}")
    elif settings.HARDWARE_PROVIDER.upper() == "LIBVIRT":
        logger.info(
            f"#    ROOKCHECK_LIBVIRT__CONNECTION="
            f"{settings.LIBVIRT.CONNECTION}")
        logger.info(
            f"#    ROOKCHECK_LIBVIRT__NETWORK_RANGE="
            f"{settings.LIBVIRT.NETWORK_RANGE}")
        logger.info(
            f"#    ROOKCHECK_LIBVIRT__NETWORK_SUBNET="
            f"{settings.LIBVIRT.NETWORK_SUBNET}")
        logger.info(
            f"#    ROOKCHECK_LIBVIRT__IMAGE={settings.LIBVIRT.IMAGE}")
        logger.info(
            f"#    ROOKCHECK_LIBVIRT__VM_MEMORY={settings.LIBVIRT.VM_MEMORY}")
    elif settings.HARDWARE_PROVIDER.upper() == "AWS_EC2":
        logger.info(
            f"#    ROOKCHECK_AWS.AMI_IMAGE_ID={settings.AWS.AMI_IMAGE_ID}")
        logger.info(
            f"#    ROOKCHECK_AWS.NODE_SIZE={settings.AWS.NODE_SIZE}")
    logger.info(f"# ROOKCHECK_DISTRO={settings.DISTRO}")
    logger.info("# Distro specific config:")
    logger.info("# -----------------------")
    if settings.DISTRO == 'SLES_CaaSP':
        logger.info(
            f"#    ROOKCHECK_SES__TARGET={settings.SES.TARGET}")
        logger.info(
            '#    SES Repositories:')
        for repo, url in settings(
                f'SES.{settings.SES.TARGET}.repositories').items():
            logger.info(
                f'#     - {repo} : {url}')
        logger.info(
            '#    YAML Replacements:')
        for key, value in settings(
                f'SES.{settings.SES.TARGET}.yaml_substitutions').items():
            logger.info(
                f'#     - {key} = {value}')
    elif settings.DISTRO == 'openSUSE_k8s':
        logger.info(
            f"#    ROOKCHECK_UPSTREAM_ROOK__BUILD_ROOK_FROM_GIT="
            f"{settings.UPSTREAM_ROOK.BUILD_ROOK_FROM_GIT}")

    logger.info("#")
    logger.info("# Environment Variables:")
    logger.info("# ======================")
    for name, value in sorted(os.environ.items()):
        logger.info(f"# {name}={value}")

    logger.info("#"*120)


def _check_docker_requirement():
    logger.debug("Checking if docker is running...")
    if settings.DISTRO == 'openSUSE_k8s' and \
            converter('@bool', settings.UPSTREAM_ROOK.BUILD_ROOK_FROM_GIT):
        rc, out, err = common.execute('docker ps', log_stdout=False)
        if rc != 0:
            raise Exception("Docker is not running - see manual.")
        logger.debug("... Docker appears to be ready")


@pytest.fixture(scope="module")
def preflight_checks():
    # Do some checks before starting and print debug information
    _print_config()
    _check_docker_requirement()


@pytest.fixture(scope="module")
def workspace(preflight_checks):
    with Workspace() as workspace:
        yield workspace


@pytest.fixture(scope="module")
def hardware(workspace):
    # NOTE(jhesketh): The Hardware() object is expected to take care of any
    # cloud provider abstraction.
    with Hardware(workspace) as hardware:
        hardware.boot_nodes(
            masters=settings.NUMBER_MASTERS,
            workers=settings.NUMBER_WORKERS)
        hardware.prepare_nodes()
        yield hardware


@pytest.fixture(scope="module")
def kubernetes(workspace, hardware):
    # NOTE(jhesketh): We can either choose which Kubernetes class to use here
    # or we can have a master class that makes the decision based off the
    # config.
    # If we implement multiple Kubernetes distributions (eg upstream vs skuba
    # etc), we should do them from an ABC so to ensure the interfaces are
    # correct.
    with Kubernetes(workspace, hardware) as kubernetes:
        kubernetes.bootstrap()
        kubernetes.install_kubernetes()
        yield kubernetes


@pytest.fixture(scope="module")
def linear_rook_cluster(workspace, kubernetes):
    # (See above re implementation options)
    # This method shows how fixture inheritance can be used to manage the
    # infrastructure. It also builds things in order, the below rook_cluster
    # fixture is preferred as it will build rook locally in a thread while
    # waiting on the infrastructure
    with RookCluster(workspace, kubernetes) as rook_cluster:
        rook_cluster.build()
        rook_cluster.preinstall()
        rook_cluster.install()
        yield rook_cluster


# TODO
# Need to remove reference to build rook because this won't exist in caasp for
# example
@pytest.fixture(scope="module")
def rook_cluster(workspace):
    with Hardware(workspace) as hardware:
        with Kubernetes(workspace, hardware) as kubernetes:
            with RookCluster(workspace, kubernetes) as rook_cluster:
                if settings.as_bool('_USE_THREADS'):
                    logger.info("Starting rook build in a thread")
                    build_thread = threading.Thread(
                        target=rook_cluster.build())
                    build_thread.start()

                # build rook thread
                hardware.boot_nodes(masters=settings.NUMBER_MASTERS,
                                    workers=settings.NUMBER_WORKERS)
                hardware.prepare_nodes()
                kubernetes.bootstrap()
                kubernetes.install_kubernetes()

                if settings.as_bool('_USE_THREADS'):
                    logger.info("Re-joining rook build thread")
                    build_thread.join()
                else:
                    rook_cluster.build()

                # NOTE(jhesketh): The upload is very slow.. may want to
                #                 consider how to do this in a thread too but
                #                 is more complex with ansible.
                rook_cluster.preinstall()
                rook_cluster.install()

                yield rook_cluster
