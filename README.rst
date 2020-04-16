==========
smoke_rook
==========

> This repository is currently an example of how jobs may be structured. It is
> not complete and requires a lot more work. However, given the other paths
> that we have been exploring this is a similar amount of work.

`smoke_rook` is a testing platform for rook.io. The intention is to provide
developers with a way to simulate various environments and scenarios that may
occur within them.

For example, smoke_rook can perform tests such as adding new nodes to your
kubernetes cluster and ensuring that they are correctly enrolled and handled by
rook.io.

Additionally smoke_rook can handle disaster testing such as kernel panics,
physically removed nodes, and so forth.

Because a test may need to interact with the underlying hardware the unit tests
will set up and configure the nodes, distros, kubernetes, and rook itself.
These are then exposed to the test writer to interact with further or to verify
the environment.

smoke_rook requires VM's from `libcloud` to set up and perform the tests
against.

*****
Usage
*****


Installing requirements::

    # zypper in python-pip docker
    # systemctl start docker
    # pip install tox
    $ PROFILE=libvirt
    $ tox -e bindep ${PROFILE}
    # zypper in <indicated missing package names>


You will need to configure the platform that the tests are ran against::

    cp configuration.env my.env
    vim my.env # Make any changes needed
    source my.env

When using the `OPENSTACK` provider and a OpenStack rc config file (eg. openrc.sh),
some mappings are needed to set the correct config values for smoke_rook::

  source openrc.sh
  export OS_USER_DOMAIN=$OS_USER_DOMAIN_NAME
  export OS_PROJECT=$OS_PROJECT_NAME
  export OS_REGION=$OS_REGION_NAME

Also the `OS_AUTH_URL` should not contain any version (or the full path,
see apache-libcloud docs)::

  export OS_AUTH_URL=`echo $OS_AUTH_URL|sed -e 's/\/v3.*//'`

Running tests::

    $ tox -e py37

OpenStack provider specifics
++++++++++++++++++++++++++++

A OpenStack network needs to be available for usage. The network name needs to
be exported as::

  export OS_NETWORK=my-test-net

If the network is not available, one can be created via::

  _OS_SUBNET=`echo $OS_NETWORK|sed -e 's/-net/-subnet/'`
  _OS_ROUTER=`echo $OS_NETWORK|sed -e 's/-net/-router/'`
  openstack network create ${OS_NETWORK}
  openstack subnet create --network ${OS_NETWORK} --subnet-range 192.168.100.0/24 ${_OS_SUBNET}
  openstack router create ${_OS_ROUTER}
  openstack router set --external-gateway floating ${_OS_ROUTER}

where `floating` is the name of the external network.

*********************
Notes/Common Problems
*********************

 * smoke_rook will remove and manage known host keys on the test runner, which
   may include removing legitimate entries.

*********
Structure
*********

Currently there are [at least] 4 abstractions that need to be available:

* Hardware (VM's, etc),
* Operating Systems (packages/configuration etc),
* Kubernetes (deployment/packages etc),
* Rook (packaging etc).

To begin with, each of these is being implemented targeting OpenStack,
openSUSE, Upstream Kubernetes, and Upstream rook.io respectfully. It is
intended that each of these are easy to swap out for other platforms depending
on the testing environment. Therefore the code is being written in a
generic/pluggable way.

 * Uses `pytest <https://docs.pytest.org/en/latest/>`_
 * Each aforementioned abstraction is set up as a
   `pytest fixture <https://docs.pytest.org/en/latest/fixture.html>`_

 * `tests/conftest.py` sets up the required fixtures

   * The fixtures are generally scoped to the module
   * This means a file such as `test/test_my_grouped_tests.py` can do serial
     tests against the same cluster
   * When the fixtures are 'exited' they clean up their resources

 * Tests are thread-safe at a module level. Each test module will have its own
   deployment created to perform tests against.

*************
Writing tests
*************

TODO some examples


*******************
Theory and rational
*******************

Use either libcloud or kcli to abstract away the hardware.
Extend either library for our needs.
 - kcli: Will likely need fixes for how auth against OpenStack works to be
         compatible with ECP's domain/project_domain.
         I also ran into a bug testing against libvirt networks that will
         require more exploration.
 - libcloud: Needs a new release to get
             https://github.com/apache/libcloud/issues/1365.
             The libvirt driver needs extending to be able to create and
             destroy vms, images, volumes, and networks. This is a large amount
             of work, but can also be pulled from existing projects such as
             kcli or python-libvirt.

Create a library for deploying kubernetes on provided nodes.
 - This would be an ABC with implementations for Vanilla Kubenetes, CaaSP and
   so on. The hardest part will be the underlying operating systems a various
   deployment will support. It may be enough to raise an error if the OS is not
   compatible.

Create a library for deploying rook.io on said kubernetes cluster.
 - This will likely need some plugability to change things such as container
   registries.

Each Hardware, Kubenetes, and Rook deployments are py.test fixtures. As we can
scope those to a module we can write tests that reuse the same deployments
rather than setting up new nodes for each individual test.

We can also eventually break things out of py.test to allow devs to build and
debug clusters etc. as well as providing tools for checking any rogue resources
left behind by tests and so on.
