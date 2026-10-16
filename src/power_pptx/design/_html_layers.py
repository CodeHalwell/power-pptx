"""Extract explicitly annotated native regions; leave general CSS to Chromium."""

from __future__ import annotations

from pathlib import Path

_LAYERS = Path(__file__).with_name("html_layers.js").read_text(encoding="utf-8")


def capture_layers(target, *, timeout_ms):
    """Return DOM metadata, isolated capture PNGs, and original inline styles."""
    records = target.evaluate(_LAYERS)
    nodes = target.locator("[data-pptx]")
    original = [nodes.nth(i).get_attribute("style") for i in range(nodes.count())]
    try:
        for index in range(nodes.count()):
            nodes.nth(index).evaluate("el => el.style.setProperty('opacity','0','important')")
        for record in records:
            if record["kind"] != "capture":
                continue
            node = nodes.nth(record["index"])
            _restore(node, original[record["index"]])
            record["png"] = node.screenshot(
                type="png",
                animations="disabled",
                caret="hide",
                omit_background=True,
                timeout=timeout_ms,
            )
            node.evaluate("el => el.style.setProperty('opacity','0','important')")
    except Exception:
        restore_layers(target, original)
        raise
    return tuple(sorted(records, key=lambda item: (item["order"], item["index"]))), original


def _restore(node, original):
    node.evaluate(
        "(el,value) => value===null ? el.removeAttribute('style') : el.setAttribute('style',value)",
        original,
    )


def restore_layers(target, original):
    nodes = target.locator("[data-pptx]")
    for index, value in enumerate(original):
        _restore(nodes.nth(index), value)
