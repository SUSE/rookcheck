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

import distutils.util
import os
import getpass

#############################################################
# Cluster settings                                          #
# ----------------                                          #
# These settings should be the same regardless of provider. #
#############################################################

# The cloud provider from libcloud
# (https://libcloud.readthedocs.io/en/latest/supported_providers.html)
CLOUD_PROVIDER = os.getenv('CLOUD_PROVIDER', 'OPENSTACK')

# The location for all of the build assets and state to be stored in. A
# sub-folder will be created using each CLUSTER_PREFIX
WORKSPACE_DIR = os.getenv('WORKSPACE_DIR', '/tmp/rookcheck')

# Prevent cluster collisions in shared environments with a resource name prefix
# Can safely be commented-out for local libvirt use
CLUSTER_PREFIX = os.getenv('CLUSTER_PREFIX', '%s-rookci-' % getpass.getuser())

# The node image by iID known to the provider
# NOTE(jhesketh): The libcloud OpenStack driver only supports finding images by
#                 ID
NODE_IMAGE_ID = os.getenv('NODE_IMAGE_ID',
                          'e9de104d-f03a-4d9f-8681-e5dd4e9cede7')

# The user to SSH into (must be root or sudoer)
NODE_IMAGE_USER = os.getenv('NODE_IMAGE_USER', 'opensuse')

# The node size or flavour name as known by the provider
NODE_SIZE = os.getenv('NODE_SIZE', 'm1.medium')

# The distro used on the underlying nodes
# Available options: openSUSE_k8s, SLES_CaaSP
DISTRO = os.getenv('DISTRO', 'openSUSE_k8s')

# The type of kubernetes deployment
# NOTE(jhesketh): Probably don't need this...
KUBERNETES_DEPLOYMENT = os.getenv('KUBERNETES_DEPLOYMENT', 'upstream')
CRICTL_VERSION = os.getenv('CRICTL_VERSION', 'v1.17.0')
K8S_VERSION = os.getenv('K8S_VERSION', 'v1.17.4')

##############################
# Provider specific settings #
##############################

######################
# OpenStack settings #
######################
# libcloud settings:
OS_AUTH_VERSION = os.getenv('OS_AUTH_VERSION', '3.x_password')
VERIFY_SSL_CERT = bool(distutils.util.strtobool(
    os.getenv('VERIFY_SSL_CERT', 'TRUE')))

# The following settings can be sourced from your openrc v3
# NOTE(jhesketh): libcloud doesn't load clouds.yaml, so env vars must be set
OS_AUTH_URL = os.getenv('OS_AUTH_URL')
# NOTE(jhesketh): OS_PROJECT_ID is not supported
# OS_PROJECT_ID = os.getenv('OS_PROJECT_ID', None)
OS_PROJECT_NAME = os.getenv('OS_PROJECT_NAME', 'default')
OS_USER_DOMAIN_NAME = os.getenv('OS_USER_DOMAIN_NAME', 'default')
OS_PROJECT_DOMAIN_ID = os.getenv('OS_PROJECT_DOMAIN_ID', 'default')
OS_USERNAME = os.getenv('OS_USERNAME')
OS_PASSWORD = os.getenv('OS_PASSWORD')
OS_REGION_NAME = os.getenv('OS_REGION_NAME', None)

# If multiple possible networks exist, you need to specify which one to use:
OS_INTERNAL_NETWORK = os.getenv('OS_INTERNAL_NETWORK', None)

# The external network that smoke-rook can create floating ip's on
OS_EXTERNAL_NETWORK = os.getenv('OS_EXTERNAL_NETWORK', 'floating')

#############################
# Debug/performance options #
#############################

# Whether or not to perform some options as a thread. Turning this off may help
# with debugging at the cost of performance.
_USE_THREADS = os.getenv('ROOKCHECK_USE_THREADS', True)
