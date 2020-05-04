Usage
=====

Make sure to have followed the :ref:`configuration` steps first, and to source
or ensure the correct environment variables are set:

.. code-block:: bash

    source my.env

.. _running_tests:

Running tests
-------------

`rookcheck` uses `tox <https://tox.readthedocs.io/>`_ to make managing the test
environment easier. If you just ran `tox`, it would execute all of the
available environments. You can see how these are configured in `tox.ini`.
Unless you are developing tests, then running the linting or other checks that
`tox` helps provide may not be necessary. Thus we can limit `tox` with the `-e`
env flag.

Running all tests:

.. code-block:: bash

    tox -e py37

Running an individual test or set of tests:

.. code-block:: bash

    tox -e py37 -- tests/test_basic.py
    # Or specific test
    tox -e py37 -- tests/test_basic.py::test_file_creation

Debugging
---------

Dropping to `PDB (Python Debugger) <http://docs.python.org/library/pdb.html>`_
on failure:

.. code-block:: bash

    tox -e py37 -- --pdb

Dropping to `PDB` at the start of a test:

.. code-block:: bash

    tox -e py37 -- --trace

If you want to use the prepared environment from `tox`, you can activate the
created virtual env:

.. code-block:: bash

    source .tox/py37/bin/activate

This will now let you run `pytest` directly and have all the dependencies
correctly set up. Similarly you can run `python` and start importing
`rookcheck`'s library. See :ref:`development_notes` for more.

Notes/Common Problems
---------------------

 * rookcheck will remove and manage known host keys on the test runner, which
   may include removing legitimate entries.
