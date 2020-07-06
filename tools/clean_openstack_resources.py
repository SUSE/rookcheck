#!/usr/bin/env python3

# Copyright (c) 2020 SUSE LLC
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


import argparse

import openstack

# from tests.config import settings


def parse_args():
    parser = argparse.ArgumentParser(
        description="Removes resources created by rookcheck that may be "
                    "orphaned.")
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help="Do not actually remove resources. "
                             " Prints what would happen.")
    # TODO(jhesketh): Fix importing settings
    parser.add_argument('-s', '--search', type=str,
                        # default=settings.CLUSTER_PREFIX,
                        default="rookcheck*",
                        help="The search glob to find leaked resources. "
                             "e.g 'rookcheck*'")
    return parser.parse_args()


def print_summary(subtitle, items):
    print(subtitle)
    print('-'*len(subtitle))
    for i in items:
        print(i.name)


def main():
    args = parse_args()
    conn = openstack.connect()

    keypairs = conn.search_keypairs(args.search)
    print_summary("Keypairs:", keypairs)

    print()

    sec_groups = conn.search_security_groups(args.search)
    print_summary("Security Groups:", sec_groups)

    print()

    networks = conn.search_networks(args.search)
    print_summary("Networks:", networks)

    print()

    subnets = conn.search_subnets(args.search)
    print_summary("Subnets:", subnets)

    print()

    routers = conn.search_routers(args.search)
    print_summary("Routers:", routers)

    print()

    nodes = conn.search_servers(args.search)
    print_summary("Nodes:", nodes)

    print()

    volumes = conn.search_volumes(args.search)
    print_summary("Volumes:", volumes)

    # Floating IP's should be cleaned by up the delete_ips=True arg, but to
    # be more thorough we should probably check all the attached networks.

    # TODO(jheketh):
    # - Only remove resources older than $age
    # - Check attached resources are cleared. For example, any additional disks
    #   to instances. Or any additional subnets to a network etc.

    print()

    if args.dry_run:
        print("Doing a dry-run, exiting here.")
        return

    cont = input("Delete all of the above resources? [y, N] ")
    if cont.lower() not in ['y', 'yes']:
        return

    for node in nodes:
        print(f"Deleting {node.name}")
        conn.delete_server(node.id, delete_ips=True, wait=True)

    for volume in volumes:
        print(f"Deleting {volume.name}")
        conn.delete_volume(volume.id, wait=True)

    for router in routers:
        print(f"Deleting {router.name}")
        interfaces = conn.list_router_interfaces(router)
        for interface in interfaces:
            print(f"..removing router interface first {interface.id}")
            conn.remove_router_interface(router, port_id=interface.id)
        conn.delete_router(router.id)

    for subnet in subnets:
        print(f"Deleting {subnet.name}")
        conn.delete_subnet(subnet.id)

    for network in networks:
        print(f"Deleting {network.name}")
        conn.delete_network(network.id)

    for sec_group in sec_groups:
        print(f"Deleting {sec_group.name}")
        conn.delete_security_group(sec_group.id)

    for keypair in keypairs:
        print(f"Deleting {keypair.name}")
        conn.delete_keypair(keypair.id)

    print()
    print("Done!")


if __name__ == '__main__':
    main()
