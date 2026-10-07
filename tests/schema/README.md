# OOXML schema validation

These tests guard against the **"generates fine but Microsoft PowerPoint
reports the file as broken / repairs it"** class of bug — issues that pass the
usual checks (the ZIP is intact, the XML is well-formed, python-pptx and
LibreOffice reopen the deck) but violate the ISO/IEC 29500 (OOXML) schema, so
PowerPoint rejects them.

Examples that slipped through before this harness existed: an empty
`<a:scene3d>`, a colour-less `<a:outerShdw>`/`<a:glow>`, negative chart
`axId`/`crossAx` values, a bare `<p14:morph>` child of `<p:transition>`, and
`import_slide()` leaving `r:embed` references pointing at the wrong part.

## How it works

`oxml_schema_validator.py` compiles the XSD schemas shipped in
`spec/ISO-IEC-29500-4/xsd/` and validates each generated part against the
schema for its root namespace (PresentationML, DrawingML, chart). It first
resolves `mc:AlternateContent` to its `mc:Fallback` — the ISO-pure branch a
non-extension processor uses — so Microsoft-namespace extensions (e.g. p14
morph) validate through their fallback instead of being reported as
"unexpected".

```python
from tests.schema.oxml_schema_validator import iter_schema_violations

violations = list(iter_schema_violations(pptx_path_or_bytes))  # (partname, message) pairs
```

The tests skip automatically if `lxml` or the bundled XSDs are unavailable.

## Master / layout hierarchy checks

The XSD cannot express how the slide masters and layouts hang together, and a
mistake there makes PowerPoint repair the deck. `hierarchy_validator.py`
checks what the schema cannot, with the same `(partname, message)` shape:

```python
from tests.schema.hierarchy_validator import iter_hierarchy_violations

violations = list(iter_hierarchy_violations(pptx_path_or_bytes))
```

* every `p:sldMasterId` / `p:sldLayoutId` `r:id` resolves to a relationship of
  the right type — a layout entry that lands on the theme part is
  schema-valid;
* a master lists each of its layouts exactly once and each layout points back
  at its master;
* the ids of all masters and layouts share one space: unique, and in
  `2147483648 .. 4294967295`.

Run it next to `iter_schema_violations()` for any feature that clones or
rewrites masters or layouts (`import_slide`, `apply_template`);
`hierarchy_decks.py` has the deck builders (pictures on a master, a layout or
the theme) and zip inspectors those tests share, and
`test_hierarchy_schema.py` is where such decks are validated.

## Adding coverage

When you add a feature that emits new OOXML, add a small deck builder to
`test_schema_validity.py` (the `_DECK_BUILDERS` map) that exercises it. The
parametrized test then asserts the generated deck is schema-clean.
