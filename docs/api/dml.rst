.. _dml_api:

DrawingML objects
=================

Low-level drawing elements like fill and color that appear repeatedly in
various aspects of shapes.


|ChartFormat| objects
---------------------

.. autoclass:: pptx.dml.chtfmt.ChartFormat
   :members:


|FillFormat| objects
--------------------

.. autoclass:: pptx.dml.fill.FillFormat
   :members:
   :exclude-members: from_fill_parent
   :undoc-members:


|LineFormat| objects
--------------------

.. autoclass:: pptx.dml.line.LineFormat
   :members:
   :undoc-members:


|LineFormat| line ends
~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: pptx.dml.line.LineEndFormat
   :members:
   :undoc-members:


|ColorFormat| objects
---------------------

.. autoclass:: pptx.dml.color.ColorFormat
   :members: brightness, rgb, theme_color, type, alpha
   :undoc-members:


|RGBColor| objects
------------------

.. autoclass:: pptx.dml.color.RGBColor
   :members: from_string, from_hex
   :undoc-members:


Effect proxies
--------------

|ShadowFormat| objects
~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: pptx.dml.effect.ShadowFormat
   :members:
   :undoc-members:


.. autoclass:: pptx.dml.effect.GlowFormat
   :members:
   :undoc-members:


.. autoclass:: pptx.dml.effect.SoftEdgeFormat
   :members:
   :undoc-members:


.. autoclass:: pptx.dml.effect.BlurFormat
   :members:
   :undoc-members:


.. autoclass:: pptx.dml.effect.ReflectionFormat
   :members:
   :undoc-members:


Picture effects
---------------

.. autoclass:: pptx.dml.picture.PictureEffects
   :members:
   :undoc-members:
