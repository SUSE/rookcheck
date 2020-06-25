.. _test_structure:

Test Structure
==============

In general, most tests will undergo 4 setup steps:

 1. Provision hardware
 2. Configure operating system
 3. Deploy and configure Kubernetes
 4. Deploy rook.io to Kubernetes cluster

These are usually done prior to a test performing its actions although it is
possible for a test to do one or more of the above steps manually to make
changes to the initial deployment.

Provided Abstractions
---------------------

Currently there are 5 abstractions available:

* Workspace (basically a directory where files (eg. config) can be stored
* Hardware (VM's, etc),
* Operating Systems (packages/configuration etc),
* Kubernetes (deployment/packages etc),
* Rook (packaging etc).

To begin with, each of these is being implemented targeting OpenStack,
openSUSE, Upstream Kubernetes, and Upstream rook.io respectfully. It is
intended that each of these are easy to swap out for other platforms depending
on the testing environment. Therefore the code is being written in a
generic/pluggable way.

Tests will have access to each of these abstractions to be able to perform
actions at the various levels. For example, a test may provision a new node
through `hardware.node_create(); hardware.node_add()`, or join it to a cluster
with `kubernetes.join_node(node)` (NOTE: These methods have not been finalised
and are examples only. The base classes will be documented below).

Each driver for the above abstractions must implement their
`Abstract Base Class`. This ensures that the expected functions are available
regardless of what hardware or other resource a developer is using.

.. autoclass:: tests.lib.hardware.hardware_base.HardwareBase
   :members:

.. autoclass:: tests.lib.hardware.node_base.NodeBase
   :members:

TODO: Finish documenting the available base classes

pytest
------

`rookcheck` uses `pytest <https://docs.pytest.org/en/latest/>`_ and
`pytest fixture <https://docs.pytest.org/en/latest/fixture.html>`_'s.

`tox <https://tox.readthedocs.io/>`_ is used to set up the environment and
execute `pytest`. You can see the exact command used in the `tox.ini` file,
but generally speaking, after the dependencies are installed,
`py.test --log-cli-level=INFO --capture=sys -s {posargs}` is executed.

See :ref:`running_tests` for information on how to get started.

`pytest` will then execute any tests in a `tests/test_*.py` file that begins
with `test_*()`.

In `pytest`, `conftest.py` is a special file (located in `tests/`). This file
is always loaded by `pytest` and gives us a place to define our fixtures and
other bootstrapping requirements.

When defining a test, any arguments required by the test method that match a
fixture method's name will have the value that fixture provided to it by
`pytest`. This is done without any imports.

For example:

.. code-block:: python

    # tests/conftest.py

    from tests.lib.hardware.openstacksdk import Hardware
    @pytest.fixture
    def hardware():
        return Hardware()

    # tests/test_example.py

    from tests.lib.hardware.openstacksdk import Hardware
    def test_hardware(hardware):
        assert type(hardware) == Hardware

The above test will pass because `pytest` will provide the returned value of
hardware() as an argument to test_hardware.

There are a few ways to clean up test resources in `pytest`. When a fixture
yields a value, that is provided as the test method argument. Then, after the
test has finished, the fixture method continues. This allows us to do a cleanup
in the fixture like so:

.. code-block:: python

    # tests/conftest.py

    from tests.lib.hardware.openstacksdk import Hardware
    @pytest.fixture
    def hardware():
        h = Hardware()
        yield h
        h.cleanup()

This is how most of the current fixtures clean up resources after a test run.
The current abstractions provided also use `python`'s context manager to allow
`__enter__` and `__exit__` to do the setup and teardown. See `conftest.py` for
examples.

The last thing to note is that most of our fixtures are scoped to the `module`
level. This means that one instance of a fixture is provided for all tests
inside one module. This is helpful as provisioning the infrastructure is
expensive so being able to reuse the same provisioned rook cluster across
multiple tests helps speed things up and reduces resources.

Therefore, it should be expected that all of the tests in one `module` (eg
`tests/test_myset.py`) be executed in serial and not make any unexpected
modifications or side-effects to the cluster. Each test inside the `module`
should ideally be able to be ran independently.

If you need to modify the provisioned cluster in a test in a way that is not
reversible, then that test should go inside its own module. If the test can
return the cluster state to the same as before then other tests can continue.

See `tests/test_fixtures.py` for an example on fixture scoping.
