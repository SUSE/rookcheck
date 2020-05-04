Theory and rational
===================

`rookcheck` is designed to do smoke or scenario testing of
`rook.io <https://rook.io>`_ - specifically for `ceph` (but may be expanded in
the future).

Because we want to be able to test how rook behaves when the underlying
infrastructure is modified, the tests must own said infrastructure. In other
words, the tests are responsible for provisioning/deploying, configuring, and
managing the entire stack.

By having the tests "own" the entire stack, we are able to write scenarios to
check correct behavour when things such as new nodes are added, a kernel panic
occurs, a hard drive fails, and so on.

Why Python and pytest?
----------------------

`pytest <https://docs.pytest.org/>`_ is primarily used due to developer
familiarity, and available tools. `rookcheck` leans heavily on
`pytest's fixtures <https://docs.pytest.org/en/latest/fixture.html>`_ for
doing the initial deployment and configuration on a per-test level. See
:ref:`test_structure` for more information, and :ref:`writing_tests` for
examples.

The intention of `rookcheck` is to provide a simple to use and easy to
understand API to developers. For example, to be able to perform common actions
easily such as `hardware.boot_nodes()`, and eventually `rook.validate_state()`.

Why tox?
--------

`tox <https://tox.readthedocs.io/>`_ makes it easier to manage virtual
environments for tests. As such, it gives us a very easy and common entrypoint.

Why libcloud?
-------------

We need a way for an individual test to provision machines. We also want to
ensure this tool is useful to both developers testing/building locally and the
community who may be testing in a CI. Therefore we want compatibility with
multiple public and private clouds, as well as things such as libvirt.

`Apache Libcloud <https://libcloud.apache.org/>`_ gives us a head start on a
common API that we can use to provision hardware. `rookcheck` may end up
further abstracting the hardware provisioner for various clouds/platforms, but
the general intent is to provide a common interface to common actions such as
creating new nodes, attaching disks, bringing up networks etc.

Why not terraform?
------------------

There are a number of reasons not to use
`Terraform <https://www.terraform.io/>`_ (or something similar).

 * Complexity: The number of tools required for `rookcheck` is increased. It
   also means that a test has to call out to terraform to make modifications to
   the infrastructure.
 * Following state: Using terraform would make determining the state of a
   deployment complex. `rookcheck` knows what nodes are provisioned and is able
   to track them in simple python code. Using terraform would mean we need to
   maintain a copy of Terraforms understanding of the infrastructure.
 * Different configuration files for different providers: This makes it complex
   to write tests that are agnostic to the underlying cloud/hardware.
   We are therefore writing and providing this abstraction. (It is possible to
   place some of the abstraction in terraform, but it adds to the complexity).
 * Modifications to infrastructure: Reapplying a terraform configuration is
   possible, but again adds to the complexity of following the state. It also
   means that we would likely need to "sed" or otherwise modify the Terraform
   configuration files. This further blurs the line between where modifications
   are made. That is, they are either made in Terraform configuration or in
   `rookcheck`'s python code somewhere. By using `libcloud` we are able to
   limit this to one place.

Having said all of that, `rookcheck` is still a young and growing tool, and the
above reasons may be fallacies. So it is possible that in the future this
decision is revised.

Why Ansible?
------------

`rookcheck` needs to be able to run commands across multiple nodes.
`Ansible <https://www.ansible.com/>`_ enables this is a simple and linear way.
Because Ansible is more or less stateless, it allows the tests to keep track of
the state and simply lean on Ansible as a way of executing arbitrary commands.

To help keep the configuration in code and easy to follow as independent steps
by tests, we are currently writing Ansible plays as Python lists and
dictionaries. We may in the future split these out into yaml playbooks where it
makes sense. However, if we did so at the moment there would be no expectation
that the playbooks would work individually.
