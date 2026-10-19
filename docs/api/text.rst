.. _text_api:

Text-related objects
====================


.. currentmodule:: power_pptx.text.text


|TextFrame| objects
--------------------

.. autoclass:: TextFrame()
   :members:
   :member-order: bysource
   :undoc-members:


|Font| objects
--------------

The |Font| object is encountered as a property of |_Run|, |_Paragraph|, and in
future other presentation text objects.

.. autoclass:: Font()
   :members:
   :member-order: bysource
   :undoc-members:


|_Paragraph| objects
--------------------

.. autoclass:: _Paragraph()
   :members:
   :member-order: bysource
   :undoc-members:


|_Run| objects
--------------

.. autoclass:: _Run()
   :members:
   :member-order: bysource
   :undoc-members:

Read-only measurement
---------------------

.. currentmodule:: power_pptx.text.measurement

.. autoclass:: TextMeasurement
   :members:

.. autofunction:: measure_text

.. autofunction:: truncate_text


Font lookup and registration
----------------------------

.. currentmodule:: power_pptx.text.fonts

.. autofunction:: register_font_dir

.. autofunction:: register_font_family

.. autofunction:: registered_font_dirs

.. autofunction:: clear_registered_fonts

.. autofunction:: find_font_file

.. autofunction:: font_face_family

.. autofunction:: resolve_weight

.. autofunction:: font_is_installed

.. autofunction:: installed_font_families
