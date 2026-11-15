.. _design_api:

Design system
=============


Tokens
------

.. currentmodule:: power_pptx.design.tokens

.. autoclass:: DesignTokens
   :members:
   :undoc-members:


.. autoclass:: TypographyToken
   :members:
   :undoc-members:


.. autoclass:: ShadowToken
   :members:
   :undoc-members:


Style facade
------------

.. currentmodule:: power_pptx.design.style

.. autoclass:: ShapeStyle
   :members:
   :undoc-members:


Layout primitives
-----------------

Measured native components are documented in :doc:`../user/authoring-workflows`.

.. currentmodule:: power_pptx.design.layout

.. autoclass:: Box
   :members:
   :undoc-members:


.. autoclass:: Grid
   :members:
   :undoc-members:


.. autoclass:: Stack
   :members:
   :undoc-members:

Native components
-----------------

.. currentmodule:: power_pptx.design.containers

.. autoclass:: Component
   :members:
.. autoclass:: TextBlock
   :members:
.. autoclass:: Container
   :members:
.. autoclass:: Row
   :members:
.. autoclass:: Column
   :members:
.. autoclass:: Card
   :members:
.. autoclass:: Badge
   :members:
.. autoclass:: MetricTile
   :members:
.. autoclass:: NativeContent
   :members:
.. autoclass:: DataTable
   :members:
.. autoclass:: LayoutResult
   :members:
.. autoexception:: LayoutOverflowError
.. autoclass:: LayoutWarning


Recipes
-------

.. currentmodule:: power_pptx.design.recipes

.. autofunction:: title_slide
.. autofunction:: bullet_slide
.. autofunction:: kpi_slide
.. autofunction:: quote_slide
.. autofunction:: image_hero_slide
.. autofunction:: section_divider
.. autofunction:: chart_slide
.. autofunction:: table_slide
.. autofunction:: code_slide
.. autofunction:: timeline_slide
.. autofunction:: comparison_slide
.. autofunction:: figure_slide


Shape-level components
----------------------

These are also importable from the top-level :mod:`power_pptx` package.

.. currentmodule:: power_pptx.design.components

.. autofunction:: add_kpi_card
.. autofunction:: add_progress_bar
.. autofunction:: add_gauge
.. autofunction:: add_status_pill
.. autofunction:: add_stat_strip
.. autofunction:: add_article_card

.. autoclass:: KpiCard
   :members:
.. autoclass:: ProgressBar
   :members:
.. autoclass:: Gauge
   :members:
.. autoclass:: StatusPill
   :members:
.. autoclass:: StatStrip
   :members:
.. autoclass:: ArticleCard
   :members:


Diagram recipes
---------------

.. automodule:: power_pptx.diagrams
   :no-members:

.. currentmodule:: power_pptx.diagrams

.. autofunction:: horizontal_pipeline
.. autofunction:: vertical_pipeline
.. autofunction:: hub_and_spoke
.. autofunction:: cycle
.. autofunction:: decision_tree
.. autofunction:: comparison_columns

.. autoclass:: PipelineResult
   :members:
.. autoclass:: HubAndSpokeResult
   :members:
.. autoclass:: CycleResult
   :members:
.. autoclass:: DecisionTreeResult
   :members:
.. autoclass:: ColumnsResult
   :members:


Content embedding
-----------------

.. currentmodule:: power_pptx.design.figures

.. autofunction:: add_html_figure
.. autofunction:: add_svg_figure
.. autofunction:: add_matplotlib_figure
.. autofunction:: add_plotly_figure
