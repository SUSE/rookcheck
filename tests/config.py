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

# Prevent cluster collisions in shared environments with a resource name prefix
# Can safely be commented-out for local libvirt use
CLUSTER_PREFIX = os.getenv('CLUSTER_PREFIX', '%s-rookci-' % getpass.getuser())

# The node image by name known to the provider
NODE_IMAGE = os.getenv('NODE_IMAGE', 'openSUSE-Leap-15.1-OpenStack')

# The node size or flavour name as known by the provider
NODE_SIZE = os.getenv('NODE_SIZE', 'm1.medium')

# The distro used on the underlying nodes
DISTRO = os.getenv('DISTRO', 'SUSE')

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
OS_USERNAME = os.getenv('OS_USERNAME')
OS_PASSWORD = os.getenv('OS_PASSWORD')
OS_AUTH_URL = os.getenv('OS_AUTH_URL')
OS_AUTH_VERSION = os.getenv('OS_AUTH_VERSION', '3.x_password')
OS_USER_DOMAIN = os.getenv('OS_USER_DOMAIN', 'default')
OS_PROJECT = os.getenv('OS_PROJECT', 'default')
OS_PROJECT_DOMAIN = os.getenv('OS_PROJECT_DOMAIN', 'default')
OS_REGION = os.getenv('OS_REGION', None)
OS_NETWORK = os.getenv('OS_NETWORK', 'user')

VERIFY_SSL_CERT = bool(distutils.util.strtobool(
    os.getenv('VERIFY_SSL_CERT', 'TRUE')))
