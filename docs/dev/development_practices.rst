#####################
Development Practices
#####################

Release procedure
=================

Releases are cut automatically when a version bump reaches ``master``:

* in a PR, bump ``__version__`` in ``src/power_pptx/__init__.py``, sync
  ``SITE.version`` in ``site/src/lib/site.ts``, and move the ``Unreleased``
  entries in ``HISTORY.rst`` into a dated ``X.Y.Z (YYYY-MM-DD)`` section;
* check the build with ``python -m build`` and ``python -m twine check dist/*``;
* merge once CI is green. ``release-on-version-bump.yml`` waits for ``ci.yml``
  on the merge commit, then tags ``vX.Y.Z`` and creates the GitHub release from
  the ``HISTORY.rst`` section;
* ``publish.yml`` then builds the tagged commit and uploads it to PyPI with
  Trusted Publishing.

``CONTRIBUTING.md`` and ``AGENTS.md`` describe the checks and recovery steps.


Creating a hand-modified package
================================

* remove file, e.g. /docProps/core.xml
* remove reference from [Content_Types].xml
* remove relationship(s) from _rels/.rels or wherever they are

Repackage::

    rm -f ../no-core-props.pptx && zip -Dqr ../no-core-props.pptx .


Procedure -- Adding a new feature
=================================

* issue added to github issue tracker
* git feature branch created
* working analysis documented
* acceptance test failing (not just raising exceptions)
* recursively, outside in:

  + unit test failing
  + next level method(s) written
  + unit test passing

* all tests passing

  + unit
  + acceptance
  + tox
  + visual confirmation of behavior in PowerPoint

* documentation updated as required

  + API additions
  + example code

* feature branch committed, rebased if required
* feature branch merged into develop

  + ``git flow feature finish paragraph-level``

* changes pushed to github
* issue closed


Outside-in layers
-----------------

* API wrapper method (if applicable)
* Internal API method
* objectify manipulation layer
* perhaps others


Creating slide images for documentation
=======================================

* Desired slide created using a test script
* Zoom slide to 100% with: click on slide, View > Zoom > Zoom... > 100% > OK
* Screenshot file on desktop using Cmd-Shift-4, Space, click
* Load into PhotoShop and crop, keeping dark gray border
* Save as PNG, scaled to 280 x 210px
* Completed image saved in ``doc/_static/img/``


Acceptance testing with ``behave``
==================================

... using *behave* for now for acceptance testing ...


Installation
------------

::

   pip install behave


Tutorial
--------

The `behave tutorial`_ is well worth working through.

.. _behave tutorial:
   http://packages.python.org/behave/tutorial.html

And this more detailed set of `examples and tutorials`_ is great for getting
the practicalities down.

.. _examples and tutorials:
   http://jenisys.github.com/behave.example/index.html


``behave`` Resources
--------------------

* `INVEST in Good Stories, and SMART Tasks`_
* `The Secret Ninja Cucumber Scrolls`_
* `Behavior Driven Outside In Development Explained, Part 1`_
* The `behave website`_ contains excellent documentation on installing and
  using behave.

.. _`INVEST in Good Stories, and SMART Tasks`:
   http://xp123.com/articles/invest-in-good-stories-and-smart-tasks/

.. _`The Secret Ninja Cucumber Scrolls`:
   http://cuke4ninja.com/sec_cucumber_jargon.html

.. _`Behavior Driven Outside In Development Explained, Part 1`:
   http://www.knwang.com/behavior-driven-outside-in-development-explai

.. _behave website:
   http://packages.python.org/behave/index.html
