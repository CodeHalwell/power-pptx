
Running the test suite
======================

|pp| has three layers of tests. ``pytest`` runs the unit tests, the round-trip
tests and the schema-validation tests; ``behave`` runs the acceptance tests.

Set up a development environment from the repository root::

    pip install -e .
    pip install -r requirements-dev.txt

Unit tests
----------

::

    pytest tests

The unit tests mirror the layout of ``src/power_pptx``. Test classes are named
``Describe…`` and test functions ``it_…``, ``but_…`` or ``and_…``. Warnings are
errors, so a deprecation warning from a dependency fails the run. To see
coverage::

    pytest --cov=power_pptx --cov-report term-missing tests

Round-trip and schema tests
---------------------------

::

    pytest tests/integration
    pytest tests/schema

``tests/integration`` saves a deck, reopens it and saves it again, and fails
if anything changed; keeping it green is a release requirement.
``tests/schema`` validates decks generated through the public API against the
ISO/IEC 29500 schemas shipped with the package. This is the check that catches
a file which reopens in this library but which PowerPoint reports as needing
repair, so add a schema test whenever a change emits new XML.

Some integration tests need LibreOffice, Poppler or a Chromium build and are
skipped when those are missing. Continuous integration installs them and runs
those tests in dedicated jobs.

Acceptance tests
----------------

::

    behave --stop

The Gherkin features under ``features/`` exercise the API the way a caller
would, against real presentation files.

Linting and type checking
-------------------------

::

    ruff check src tests
    ruff format --check src tests
    pyright --project pyright-ci.json
    complexipy src/power_pptx

Several interpreters
--------------------

``tox`` runs the unit and acceptance suites on every supported Python version
that is installed::

    tox
