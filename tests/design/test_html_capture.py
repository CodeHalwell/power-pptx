"""Validation and aspect-ratio invariants without optional browser dependencies."""

import io
from unittest.mock import patch

import pytest
from PIL import Image

from power_pptx import Presentation
from power_pptx.design._html import capture_html
from power_pptx.design.figures import _embed_html_png
from power_pptx.util import Inches


@pytest.mark.parametrize(
    "options",
    [
        {"viewport": (0, 100)},
        {"viewport": (100.5, 100)},
        {"viewport": (True, 100)},
        {"device_scale_factor": 0},
        {"device_scale_factor": float("nan")},
        {"timeout_ms": 0},
        {"wait_until": "forever"},
        {"selector": ""},
        {"selector": ".slide", "full_page": True},
    ],
)
def test_invalid_options_fail_before_browser_launch(options):
    with patch("builtins.__import__", wraps=__import__) as imports:
        with pytest.raises(ValueError):
            capture_html("<h1>Example</h1>", **options)
    assert not any(call.args[0].startswith("playwright") for call in imports.call_args_list)


@pytest.mark.parametrize("fit", ["contain", "cover", "stretch"])
def test_picture_fitting_preserves_or_crops_as_requested(fit):
    data = io.BytesIO()
    Image.new("RGB", (400, 200)).save(data, format="PNG")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    picture = _embed_html_png(
        slide,
        data.getvalue(),
        Inches(1),
        Inches(1),
        Inches(4),
        Inches(4),
        fit=fit,
        device_scale_factor=2,
    )
    assert picture.width == Inches(4)
    if fit == "contain":
        assert picture.height == Inches(2)
        assert picture.top == Inches(2)
    elif fit == "cover":
        assert picture.height == Inches(4)
        assert picture.crop_left == picture.crop_right == 0.25
    else:
        assert picture.height == Inches(4)
        assert picture.crop_left == 0


def test_capture_density_does_not_change_physical_size():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sizes = []
    for density in [1, 2, 3]:
        data = io.BytesIO()
        Image.new("RGB", (200 * density, 100 * density)).save(data, format="PNG")
        picture = _embed_html_png(
            slide,
            data.getvalue(),
            Inches(0),
            Inches(0),
            None,
            None,
            fit="contain",
            device_scale_factor=density,
        )
        sizes.append((picture.width, picture.height))
    assert len(set(sizes)) == 1
