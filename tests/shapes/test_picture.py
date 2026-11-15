"""Test suite for power_pptx.shapes.picture module."""

from __future__ import annotations

import pytest

from power_pptx.dml.line import LineFormat
from power_pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE, PP_MEDIA_TYPE
from power_pptx.parts.image import Image
from power_pptx.parts.slide import SlidePart
from power_pptx.shapes.picture import Movie, Picture, _BasePicture, _MediaFormat
from power_pptx.util import Pt

from ..unitutil.cxml import element, xml
from ..unitutil.mock import call, class_mock, instance_mock, property_mock


class Describe_BasePicture(object):
    def it_knows_its_cropping(self, crop_get_fixture):
        picture, prop_name, expected_value = crop_get_fixture
        crop = getattr(picture, prop_name)
        assert abs(crop - expected_value) < 0.000001

    def it_can_change_its_cropping(self, crop_set_fixture):
        picture, prop_name, value, expected_xml = crop_set_fixture
        setattr(picture, prop_name, value)
        assert picture._element.xml == expected_xml

    def it_provides_access_to_its_outline(self, line_fixture):
        picture = line_fixture
        line = picture.line
        assert isinstance(line, LineFormat)
        # exercise line to test has_line interface, .ln and .get_or_add_ln()
        picture.line.width = Pt(1)
        assert picture.line.width == Pt(1)

    # fixtures -------------------------------------------------------

    @pytest.fixture(
        params=[
            ("p:pic/p:blipFill", "left", 0.0),
            ("p:pic/p:blipFill/a:srcRect", "top", 0.0),
            ("p:pic/p:blipFill/a:srcRect{l=99999}", "bottom", 0.0),
            ("p:pic/p:blipFill/a:srcRect{l=42424}", "left", 0.42424),
            ("p:pic/p:blipFill/a:srcRect{t=-10000}", "top", -0.1),
            ("p:pic/p:blipFill/a:srcRect{r=250000}", "right", 2.5),
            ("p:pic/p:blipFill/a:srcRect{b=33333}", "bottom", 0.33333),
        ]
    )
    def crop_get_fixture(self, request):
        pic_cxml, side, expected_value = request.param
        picture = Picture(element(pic_cxml), None)
        prop_name = "crop_%s" % side
        return picture, prop_name, expected_value

    @pytest.fixture(
        params=[
            (
                "p:pic{a:b=c}/p:blipFill",
                "left",
                0.11,
                "p:pic{a:b=c}/p:blipFill/a:srcRect{l=11000}",
            ),
            (
                "p:pic{a:b=c}/p:blipFill",
                "top",
                0.21,
                "p:pic{a:b=c}/p:blipFill/a:srcRect{t=21000}",
            ),
            (
                "p:pic{a:b=c}/p:blipFill",
                "right",
                0.31,
                "p:pic{a:b=c}/p:blipFill/a:srcRect{r=31000}",
            ),
            (
                "p:pic{a:b=c}/p:blipFill",
                "bottom",
                0.41,
                "p:pic{a:b=c}/p:blipFill/a:srcRect{b=41000}",
            ),
            (
                "p:pic{a:b=c}/p:blipFill/a:srcRect{l=80000}",
                "left",
                0.21,
                "p:pic{a:b=c}/p:blipFill/a:srcRect{l=21000}",
            ),
            (
                "p:pic{a:b=c}/p:blipFill/a:srcRect{t=70000}",
                "top",
                0.22,
                "p:pic{a:b=c}/p:blipFill/a:srcRect{t=22000}",
            ),
            (
                "p:pic{a:b=c}/p:blipFill/a:srcRect{r=60000}",
                "right",
                0.23,
                "p:pic{a:b=c}/p:blipFill/a:srcRect{r=23000}",
            ),
            (
                "p:pic{a:b=c}/p:blipFill/a:srcRect{b=50000}",
                "bottom",
                0.24,
                "p:pic{a:b=c}/p:blipFill/a:srcRect{b=24000}",
            ),
            (
                "p:pic{a:b=c}/p:blipFill/a:srcRect{l=90000}",
                "left",
                0,
                "p:pic{a:b=c}/p:blipFill/a:srcRect",
            ),
            (
                "p:pic{a:b=c}/p:blipFill/a:srcRect{t=91000}",
                "top",
                0.0,
                "p:pic{a:b=c}/p:blipFill/a:srcRect",
            ),
            (
                "p:pic{a:b=c}/p:blipFill/a:srcRect{r=92000}",
                "right",
                0,
                "p:pic{a:b=c}/p:blipFill/a:srcRect",
            ),
            (
                "p:pic{a:b=c}/p:blipFill/a:srcRect{b=93000}",
                "bottom",
                0.0,
                "p:pic{a:b=c}/p:blipFill/a:srcRect",
            ),
        ]
    )
    def crop_set_fixture(self, request):
        pic_cxml, side, value, expected_cxml = request.param
        pic = element(pic_cxml)
        picture = Picture(pic, None)
        prop_name = "crop_%s" % side
        expected_xml = xml(expected_cxml)
        return picture, prop_name, value, expected_xml

    @pytest.fixture
    def line_fixture(self):
        return _BasePicture(element("p:pic/p:spPr"), None)


class DescribeMovie(object):
    def it_knows_its_shape_type(self, shape_type_fixture):
        movie = shape_type_fixture
        assert movie.shape_type == MSO_SHAPE_TYPE.MEDIA

    def it_knows_its_media_type(self, media_type_fixture):
        movie = media_type_fixture
        assert movie.media_type == PP_MEDIA_TYPE.MOVIE

    def it_provides_access_to_its_media_format(self, format_fixture):
        movie, MediaFormat_, pic, parent, media_format_ = format_fixture
        media_format = movie.media_format
        MediaFormat_.assert_called_once_with(pic, parent)
        assert media_format is media_format_

    def it_provides_access_to_its_poster_frame_image(self, pfrm_fixture):
        movie, slide_part_, calls, expected_value = pfrm_fixture
        poster_frame = movie.poster_frame
        assert slide_part_.get_image.call_args_list == calls
        assert poster_frame == expected_value

    # fixtures -------------------------------------------------------

    @pytest.fixture
    def format_fixture(self, _MediaFormat_, media_format_):
        pic = element("p:pic")
        parent = movie = Movie(pic, None)
        return movie, _MediaFormat_, pic, parent, media_format_

    @pytest.fixture
    def media_type_fixture(self):
        return Movie(None, None)

    @pytest.fixture(
        params=[
            ("p:pic/p:blipFill/a:blip{r:embed=rId42}", True),
            ("p:pic/p:blipFill/a:blip", False),
        ]
    )
    def pfrm_fixture(self, request, slide_part_, image_, part_prop_):
        cxml, is_present = request.param
        movie = Movie(element(cxml), None)
        calls, expected_value = [], None
        part_prop_.return_value = slide_part_
        slide_part_.get_image.return_value = image_
        if is_present:
            calls.append(call("rId42"))
            expected_value = image_
        return movie, slide_part_, calls, expected_value

    @pytest.fixture
    def shape_type_fixture(self):
        return Movie(None, None)

    # fixture components ---------------------------------------------

    @pytest.fixture
    def image_(self, request):
        return instance_mock(request, Image)

    @pytest.fixture
    def _MediaFormat_(self, request, media_format_):
        return class_mock(
            request, "power_pptx.shapes.picture._MediaFormat", return_value=media_format_
        )

    @pytest.fixture
    def media_format_(self, request):
        return instance_mock(request, _MediaFormat)

    @pytest.fixture
    def part_prop_(self, request):
        return property_mock(request, Movie, "part")

    @pytest.fixture
    def slide_part_(self, request):
        return instance_mock(request, SlidePart)


class DescribePicture(object):
    def it_knows_its_masking_shape(self, autoshape_get_fixture):
        picture, expected_value = autoshape_get_fixture
        auto_shape_type = picture.auto_shape_type
        assert auto_shape_type == expected_value

    def it_can_change_its_masking_shape(self, autoshape_set_fixture):
        picture, new_value, expected_xml = autoshape_set_fixture
        picture.auto_shape_type = new_value
        assert picture._element.xml == expected_xml

    def it_knows_its_shape_type(self, shape_type_fixture):
        picture = shape_type_fixture
        assert picture.shape_type == MSO_SHAPE_TYPE.PICTURE

    def it_provides_access_to_its_image(self, image_fixture):
        picture, slide_part_, rId, image_ = image_fixture
        image = picture.image
        slide_part_.get_image.assert_called_once_with(rId)
        assert image is image_

    def it_drops_the_lum_element_when_adjustments_reset_to_neutral(self):
        # brightness/contrast of 0.0 are the schema defaults, so their
        # attributes are dropped on write; once both are neutral the `a:lum`
        # itself must go too, not linger as a dead empty element.
        from power_pptx.dml.picture import PictureEffects
        from power_pptx.oxml.ns import qn

        pic = element("p:pic/p:blipFill/a:blip{r:embed=rId1}")
        blip = pic.blipFill.blip
        effects = PictureEffects(blip)

        effects.brightness = 0.0  # no-op on a picture with no a:lum
        assert blip.find(qn("a:lum")) is None

        effects.brightness = 0.3
        effects.contrast = -0.2
        assert blip.find(qn("a:lum")) is not None

        effects.brightness = 0.0
        assert blip.find(qn("a:lum")) is not None  # contrast still set
        effects.contrast = 0.0
        assert blip.find(qn("a:lum")) is None

    # fixtures -------------------------------------------------------

    @pytest.fixture(
        params=[
            ("", None),
            ("/a:prstGeom{prst=rect}", MSO_SHAPE.RECTANGLE),
            ("/a:prstGeom{prst=hexagon}", MSO_SHAPE.HEXAGON),
        ]
    )
    def autoshape_get_fixture(self, request):
        prstGeom_cxml, expected_value = request.param
        pic_cxml = "p:pic/p:spPr%s" % prstGeom_cxml
        picture = Picture(element(pic_cxml), None)
        return picture, expected_value

    @pytest.fixture(
        params=[
            (
                "p:pic/p:spPr/a:custGeom",
                MSO_SHAPE.RECTANGLE,
                "p:pic/p:spPr/a:prstGeom{prst=rect}",
            ),
            (
                "p:pic/p:spPr/a:prstGeom{prst=rect}",
                MSO_SHAPE.OVAL,
                "p:pic/p:spPr/a:prstGeom{prst=ellipse}",
            ),
            (
                "p:pic/p:spPr/a:prstGeom{prst=ellipse}",
                MSO_SHAPE.PIE,
                "p:pic/p:spPr/a:prstGeom{prst=pie}",
            ),
        ]
    )
    def autoshape_set_fixture(self, request):
        pic_cxml, new_value, expected_cxml = request.param
        picture = Picture(element(pic_cxml), None)
        expected_xml = xml(expected_cxml)
        return picture, new_value, expected_xml

    @pytest.fixture
    def image_fixture(self, part_prop_, slide_part_, image_):
        pic_cxml, rId = "p:pic/p:blipFill/a:blip{r:embed=rId42}", "rId42"
        picture = Picture(element(pic_cxml), None)
        slide_part_.get_image.return_value = image_
        return picture, slide_part_, rId, image_

    @pytest.fixture
    def shape_type_fixture(self):
        return Picture(None, None)

    # fixture components ---------------------------------------------

    @pytest.fixture
    def image_(self, request):
        return instance_mock(request, Image)

    @pytest.fixture
    def part_prop_(self, request, slide_part_):
        return property_mock(request, Picture, "part", return_value=slide_part_)

    @pytest.fixture
    def slide_part_(self, request):
        return instance_mock(request, SlidePart)


class DescribePictureEnclosingContainer:
    """`Picture.enclosing_container()` finds the card a picture sits in."""

    def it_returns_None_when_the_picture_is_not_on_a_slide(self, slide):
        from types import SimpleNamespace

        picture = _add_picture(slide, 1, 1, 1, 1)
        detached = Picture(picture._element, SimpleNamespace(part=object()))

        assert detached.enclosing_container() is None

    def it_returns_None_when_no_shape_encloses_the_picture(self, slide):
        _add_rect(slide, 5, 5, 1, 1)
        picture = _add_picture(slide, 1, 1, 1, 1)

        assert picture.enclosing_container() is None

    def it_picks_the_smallest_enclosing_shape(self, slide):
        _add_rect(slide, 0.5, 0.5, 8, 6)
        _add_rect(slide, 1, 1, 6, 5)
        picture = _add_picture(slide, 2, 2, 2, 2)

        assert picture.enclosing_container(shrink_around=False) == _bbox(1, 1, 6, 5)
        # -- the outer card does not lie inside the inner one, so trims nothing --
        assert picture.enclosing_container() == _bbox(1, 1, 6, 5)

    def it_does_not_trim_its_card_around_a_zero_width_picture(self, slide):
        # -- `slide.shapes` makes new proxies, so the picture and its card used
        # -- to escape an identity check and be trimmed around as obstacles --
        _add_rect(slide, 1, 1, 6, 4)
        picture = _add_picture(slide, 3, 2, 2, 1)
        picture.width = 0

        assert picture.enclosing_container() == _bbox(1, 1, 6, 4)

    def it_skips_an_enclosing_shape_that_holds_text_unless_told_not_to(self, slide):
        card = slide.shapes.add_textbox(*_bbox(1, 1, 6, 5))
        card.text_frame.text = "label"
        picture = _add_picture(slide, 2, 2, 2, 2)

        assert picture.enclosing_container() is None
        assert picture.enclosing_container(exclude_text=False) == _bbox(1, 1, 6, 5)

        card.text_frame.text = "   "
        assert picture.enclosing_container() == _bbox(1, 1, 6, 5)

    def it_ignores_shapes_that_have_no_geometry(self, slide):
        _add_rect(slide, 1, 1, 6, 5)
        shapeless = _add_rect(slide, 1, 1, 1, 1)
        spPr = shapeless._element.spPr
        spPr.remove(spPr.xfrm)
        picture = _add_picture(slide, 2, 2, 2, 2)

        assert picture.enclosing_container() == _bbox(1, 1, 6, 5)

    def it_trims_away_content_beside_the_picture(self, slide):
        _add_rect(slide, 1, 1, 6, 5)
        _add_rect(slide, 0.5, 4, 2, 0.5)  # -- not inside the card: ignored --
        _add_rect(slide, 1.2, 1.5, 0.6, 1)  # -- a strip left of the picture --
        picture = _add_picture(slide, 2, 2, 4, 3)

        assert picture.enclosing_container() == _bbox(1.8, 1, 5.2, 5)

    def it_trims_away_a_title_strip_above_the_picture(self, slide):
        from power_pptx import BBox

        _add_rect(slide, 1, 1, 6, 5)
        slide.shapes.add_text(BBox.from_inches(1.2, 1.2, 5.6, 0.6), text="Architecture")
        picture = _add_picture(slide, 1.5, 2, 5, 3.5)

        assert picture.enclosing_container() == _bbox(1, 1.8, 6, 4.2)

    # fixtures -------------------------------------------------------

    @pytest.fixture
    def slide(self):
        from power_pptx import Presentation

        prs = Presentation()
        return prs.slides.add_slide(prs.slide_layouts[6])


_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415478da6300010000000500010d0a2db40000000049"
    "454e44ae426082"
)


def _bbox(left, top, width, height):
    from power_pptx import BBox

    return BBox.from_inches(left, top, width, height)


def _add_rect(slide, left, top, width, height):
    return slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *_bbox(left, top, width, height))


def _add_picture(slide, left, top, width, height):
    import io

    return slide.shapes.add_picture(io.BytesIO(_ONE_PIXEL_PNG), *_bbox(left, top, width, height))
