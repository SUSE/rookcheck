This repository is currently an example of how jobs may be structured. It is
not complete and requires a lot more work. However, given the other paths that
we have been exploring this is a similar amount of work.

Theory and rational:

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


Installing requirements:

# zypper in python-pip
# pip install tox
$ PROFILE=libvirt
$ tox -e bindep ${PROFILE}
# zypper in <indicated missing package names>


Running tests:
$ tox -e py37
