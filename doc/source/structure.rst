
Test Structure
==============

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
