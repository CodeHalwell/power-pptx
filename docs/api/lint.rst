.. _lint_api:

Linter
======

.. currentmodule:: power_pptx.lint


.. autoclass:: SlideLintReport
   :members:
   :undoc-members:


.. autoclass:: LintIssue
   :members:
   :undoc-members:


.. autoclass:: TextOverflow
   :members:
   :show-inheritance:


.. autoclass:: OffSlide
   :members:
   :show-inheritance:


.. autoclass:: OffSlideShadow
   :members:
   :show-inheritance:


.. autoclass:: ShapeCollision
   :members:
   :show-inheritance:


.. autoclass:: ShapeCollisionShadow
   :members:
   :show-inheritance:


.. autoclass:: MinFontSize
   :members:
   :show-inheritance:


.. autoclass:: OffGridDrift
   :members:
   :show-inheritance:


.. autoclass:: LowContrast
   :members:
   :show-inheritance:


.. autoclass:: ZOrderAnomaly
   :members:
   :show-inheritance:


.. autoclass:: LayerOrderViolation
   :members:
   :show-inheritance:


.. autoclass:: MasterPlaceholderCollision
   :members:
   :show-inheritance:


.. autoclass:: InvalidGeometry
   :members:
   :show-inheritance:


.. autoclass:: RaggedEdge
   :members:
   :show-inheritance:


.. autoclass:: LintSeverity
   :members:
   :undoc-members:


.. autofunction:: lint_report_to_sarif


Whole-deck audits
-----------------

.. currentmodule:: power_pptx.audit

.. autofunction:: audit

.. autoclass:: AuditReport
   :members:


.. currentmodule:: power_pptx.accessibility

.. autofunction:: audit_accessibility

.. autoclass:: AccessibilityReport
   :members:

.. autoclass:: AccessibilityIssue
   :members:

.. autoclass:: AccessibilitySeverity
   :members:
   :undoc-members:
