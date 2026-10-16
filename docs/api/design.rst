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
.. autoclass:: LayoutResult
   :members:
.. autoexception:: LayoutOverflowError


Recipes
-------

.. currentmodule:: power_pptx.design.recipes

.. autofunction:: title_slide
.. autofunction:: bullet_slide
.. autofunction:: kpi_slide
.. autofunction:: quote_slide
.. autofunction:: image_hero_slide


Content embedding
-----------------

.. currentmodule:: power_pptx.design.figures

.. autofunction:: add_html_figure
.. autofunction:: add_svg_figure
.. autofunction:: add_matplotlib_figure
.. autofunction:: add_plotly_figure
