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
CLUSTER_PREFIX = os.getenv('CLUSTER_PREFIX', '%s-rookci-' % os.getlogin())

# The node image by name known to the provider
NODE_IMAGE = os.getenv('NODE_IMAGE', 'opensuse')

# The node size or flavour name as known by the provider
NODE_SIZE = os.getenv('NODE_SIZE', 'small')

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

VERIFY_SSL_CERT = bool(distutils.util.strtobool(
    os.getenv('VERIFY_SSL_CERT', 'TRUE')))