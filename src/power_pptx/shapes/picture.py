"""Shapes based on the `p:pic` element, including Picture and Movie."""

from __future__ import annotations

from typing import TYPE_CHECKING

from power_pptx.dml.line import LineFormat
from power_pptx.dml.picture import PictureEffects
from power_pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE, PP_MEDIA_TYPE
from power_pptx.shapes.base import BaseShape
from power_pptx.shared import ParentedElementProxy
from power_pptx.util import lazyproperty

if TYPE_CHECKING:
    from power_pptx.oxml.shapes.picture import CT_Picture
    from power_pptx.oxml.shapes.shared import CT_LineProperties
    from power_pptx.types import ProvidesPart


class _BasePicture(BaseShape):
    """Base class for shapes based on a `p:pic` element."""

    def __init__(self, pic: CT_Picture, parent: ProvidesPart):
        super(_BasePicture, self).__init__(pic, parent)
        self._pic = pic

    @property
    def crop_bottom(self) -> float:
        """|float| representing relative portion cropped from shape bottom.

        Read/write. 1.0 represents 100%. For example, 25% is represented by 0.25. Negative values
        are valid as are values greater than 1.0.
        """
        return self._pic.srcRect_b

    @crop_bottom.setter
    def crop_bottom(self, value: float):
        self._pic.srcRect_b = value

    @property
    def crop_left(self) -> float:
        """|float| representing relative portion cropped from left of shape.

        Read/write. 1.0 represents 100%. A negative value extends the side beyond the image
        boundary.
        """
        return self._pic.srcRect_l

    @crop_left.setter
    def crop_left(self, value: float):
        self._pic.srcRect_l = value

    @property
    def crop_right(self) -> float:
        """|float| representing relative portion cropped from right of shape.

        Read/write. 1.0 represents 100%.
        """
        return self._pic.srcRect_r

    @crop_right.setter
    def crop_right(self, value: float):
        self._pic.srcRect_r = value

    @property
    def crop_top(self) -> float:
        """|float| representing relative portion cropped from shape top.

        Read/write. 1.0 represents 100%.
        """
        return self._pic.srcRect_t

    @crop_top.setter
    def crop_top(self, value: float):
        self._pic.srcRect_t = value

    def get_or_add_ln(self):
        """Return the `a:ln` element for this `p:pic`-based image.

        The `a:ln` element contains the line format properties XML.
        """
        return self._pic.get_or_add_ln()

    @lazyproperty
    def line(self) -> LineFormat:
        """Provides access to properties of the picture outline, such as its color and width."""
        return LineFormat(self)

    @property
    def ln(self) -> CT_LineProperties | None:
        """The `a:ln` element for this `p:pic`.

        Contains the line format properties such as line color and width. |None| if no `a:ln`
        element is present.
        """
        return self._pic.ln


class Movie(_BasePicture):
    """A movie shape, one that places a video on a slide.

    Like |Picture|, a movie shape is based on the `p:pic` element. A movie is composed of a video
    and a *poster frame*, the placeholder image that represents the video before it is played.
    """

    @lazyproperty
    def media_format(self) -> _MediaFormat:
        """The |_MediaFormat| object for this movie.

        The |_MediaFormat| object provides access to formatting properties for the movie.
        """
        return _MediaFormat(self._pic, self)

    @property
    def media_type(self) -> PP_MEDIA_TYPE:
        """Member of :ref:`PpMediaType` describing this shape.

        The return value is unconditionally `PP_MEDIA_TYPE.MOVIE` in this case.
        """
        return PP_MEDIA_TYPE.MOVIE

    @property
    def poster_frame(self):
        """Return |Image| object containing poster frame for this movie.

        Returns |None| if this movie has no poster frame (uncommon).
        """
        slide_part, rId = self.part, self._pic.blip_rId
        if rId is None:
            return None
        return slide_part.get_image(rId)

    @property
    def shape_type(self) -> MSO_SHAPE_TYPE:
        """Return member of :ref:`MsoShapeType` describing this shape.

        The return value is unconditionally `MSO_SHAPE_TYPE.MEDIA` in this
        case.
        """
        return MSO_SHAPE_TYPE.MEDIA


class Picture(_BasePicture):
    """A picture shape, one that places an image on a slide.

    Based on the `p:pic` element.
    """

    def replace_with(self, builder, *, padding=0):
        """Delete this picture and call ``builder(slide, bbox)`` in its place.

        The picture's current bounding box is snapshotted (minus an
        optional ``padding`` inset), then the picture is removed from
        the slide.  ``builder`` is invoked with ``(slide, bbox)`` where
        ``bbox`` is a :class:`~power_pptx.geometry.BBox` — the typical
        usage is to draw native shapes in the area a broken /
        suboptimal picture used to occupy::

            def diagram(slide, bbox):
                left, right = bbox.split_h([1, 1], gap=Inches(0.1))
                slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *left)
                slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *right)

            picture.replace_with(diagram, padding=Inches(0.1))

        ``padding`` is an integer EMU (or :class:`~power_pptx.util.Length`)
        applied as a uniform inset on all four sides.  Negative values
        expand the area outward.

        Returns whatever ``builder`` returned.
        """
        from power_pptx.geometry import BBox

        bbox = BBox.from_shape(self)
        if padding:
            bbox = bbox.inset(all=int(padding))
        # Walk up through the proxy to find the owning slide.
        try:
            slide = self.part.slide
        except AttributeError as exc:
            raise ValueError(
                "replace_with() requires the picture to be on a slide"
            ) from exc
        self.delete()
        return builder(slide, bbox)

    def enclosing_container(
        self,
        *,
        exclude_text: bool = True,
        shrink_around: bool = True,
    ):
        """Return the smallest rectangle on the slide enclosing this picture.

        Useful when a picture sits inside a "card" rectangle plus a
        heading — replacing the picture's own bbox would lose the
        heading; replacing the enclosing container area keeps the
        layout intact.

        * ``exclude_text=True`` (default) skips other shapes that hold
          live text — those are content, not chrome.
        * ``shrink_around=True`` (default) trims the returned box so it
          doesn't overlap any sibling content-bearing shape; the
          biggest empty sub-rectangle of the enclosing card is returned.

        Returns a :class:`~power_pptx.geometry.BBox` or ``None`` when no
        enclosing shape (other than the slide itself) is found.
        """
        from power_pptx.geometry import BBox

        try:
            slide = self.part.slide
        except AttributeError:
            return None

        my_box = BBox.from_shape(self)
        candidates: list[tuple[int, BaseShape, BBox]] = []
        for shape in slide.shapes:
            if shape is self:
                continue
            try:
                box = BBox.from_shape(shape)
            except Exception:
                continue
            if box.area <= my_box.area:
                continue
            # Skip if this shape is itself a placeholder for text we
            # want to keep visible.
            if exclude_text and getattr(shape, "has_text_frame", False):
                tf = getattr(shape, "text_frame", None)
                if tf is not None and tf.text.strip():
                    continue
            if box.contains(my_box):
                candidates.append((box.area, shape, box))
        if not candidates:
            return None
        # Smallest enclosing box.
        candidates.sort(key=lambda t: t[0])
        _, _container, container_box = candidates[0]
        if not shrink_around:
            return container_box

        # Trim around other content shapes that sit inside the container.
        # For each obstacle, try the four edge-pushes that would exclude
        # it (top edge down past obstacle.bottom, bottom edge up past
        # obstacle.top, etc.) and pick the smallest waste that still
        # keeps the picture (``my_box``) inside the trimmed result.
        trimmed = container_box
        for shape in slide.shapes:
            if shape is self or shape is _container:
                continue
            try:
                box = BBox.from_shape(shape)
            except Exception:
                continue
            if not trimmed.contains(box):
                continue
            trimmed = _exclude_obstacle(trimmed, box, must_contain=my_box)
        return trimmed

    @property
    def auto_shape_type(self) -> MSO_SHAPE | None:
        """Member of MSO_SHAPE indicating masking shape.

        A picture can be masked by any of the so-called "auto-shapes" available in PowerPoint,
        such as an ellipse or triangle. When a picture is masked by a shape, the shape assumes the
        same dimensions as the picture and the portion of the picture outside the shape boundaries
        does not appear. Note the default value for a newly-inserted picture is
        `MSO_AUTO_SHAPE_TYPE.RECTANGLE`, which performs no cropping because the extents of the
        rectangle exactly correspond to the extents of the picture.

        The available shapes correspond to the members of :ref:`MsoAutoShapeType`.

        The return value can also be |None|, indicating the picture either has no geometry (not
        expected) or has custom geometry, like a freeform shape. A picture with no geometry will
        have no visible representation on the slide, although it can be selected. This is because
        without geometry, there is no "inside-the-shape" for it to appear in.
        """
        prstGeom = self._pic.spPr.prstGeom
        if prstGeom is None:  # ---generally means cropped with freeform---
            return None
        return prstGeom.prst

    @auto_shape_type.setter
    def auto_shape_type(self, member: MSO_SHAPE):
        MSO_SHAPE.validate(member)
        spPr = self._pic.spPr
        prstGeom = spPr.prstGeom
        if prstGeom is None:
            spPr._remove_custGeom()  # pyright: ignore[reportPrivateUsage]
            prstGeom = spPr._add_prstGeom()  # pyright: ignore[reportPrivateUsage]
        prstGeom.prst = member

    @lazyproperty
    def effects(self) -> PictureEffects:
        """Provides access to image-level effects: transparency, brightness, contrast, recolor.

        The underlying ``<a:blip>`` element must be present (which it always is for a
        normal embedded-image picture).
        """
        blip = self._pic.blipFill.blip
        if blip is None:
            raise ValueError("picture has no embedded image blip element")
        return PictureEffects(blip)

    @property
    def image(self):
        """The |Image| object for this picture.

        Provides access to the properties and bytes of the image in this picture shape.
        """
        slide_part, rId = self.part, self._pic.blip_rId
        if rId is None:
            raise ValueError("no embedded image")
        return slide_part.get_image(rId)

    @property
    def shape_type(self) -> MSO_SHAPE_TYPE:
        """Unconditionally `MSO_SHAPE_TYPE.PICTURE` in this case."""
        return MSO_SHAPE_TYPE.PICTURE


def _exclude_obstacle(trimmed, obstacle, *, must_contain):
    """Shrink *trimmed* to exclude *obstacle* while still containing *must_contain*.

    Tries each of the four edge-trims (push top down past obstacle,
    push bottom up past obstacle, etc.), discards any that would also
    exclude *must_contain*, and returns the candidate with the least
    area lost.  Returns *trimmed* unchanged when no valid trim exists.

    Earlier versions of ``Picture.enclosing_container(shrink_around=
    True)`` used a different heuristic that could collapse the
    container onto the obstacle (e.g. a title strip above the picture
    caused the bottom edge to be chosen, returning the top strip
    instead).  This helper picks the right edge by construction: it
    only emits a candidate that excludes the obstacle *and* keeps the
    picture inside.
    """
    from power_pptx.geometry import BBox
    from power_pptx.util import Emu

    candidates: list[tuple[int, BBox]] = []
    # Push TOP edge down past obstacle.bottom
    new_top = int(obstacle.bottom)
    if (
        new_top > int(trimmed.top)
        and new_top <= int(must_contain.top)
        and new_top < int(trimmed.bottom)
    ):
        cost = new_top - int(trimmed.top)
        candidates.append(
            (
                cost,
                BBox(
                    trimmed.left, Emu(new_top), trimmed.width,
                    Emu(int(trimmed.bottom) - new_top),
                ),
            )
        )
    # Push BOTTOM edge up past obstacle.top
    new_bottom = int(obstacle.top)
    if (
        new_bottom < int(trimmed.bottom)
        and new_bottom >= int(must_contain.bottom)
        and new_bottom > int(trimmed.top)
    ):
        cost = int(trimmed.bottom) - new_bottom
        candidates.append(
            (
                cost,
                BBox(
                    trimmed.left, trimmed.top, trimmed.width,
                    Emu(new_bottom - int(trimmed.top)),
                ),
            )
        )
    # Push LEFT edge right past obstacle.right
    new_left = int(obstacle.right)
    if (
        new_left > int(trimmed.left)
        and new_left <= int(must_contain.left)
        and new_left < int(trimmed.right)
    ):
        cost = new_left - int(trimmed.left)
        candidates.append(
            (
                cost,
                BBox(
                    Emu(new_left), trimmed.top,
                    Emu(int(trimmed.right) - new_left), trimmed.height,
                ),
            )
        )
    # Push RIGHT edge left past obstacle.left
    new_right = int(obstacle.left)
    if (
        new_right < int(trimmed.right)
        and new_right >= int(must_contain.right)
        and new_right > int(trimmed.left)
    ):
        cost = int(trimmed.right) - new_right
        candidates.append(
            (
                cost,
                BBox(
                    trimmed.left, trimmed.top,
                    Emu(new_right - int(trimmed.left)), trimmed.height,
                ),
            )
        )
    if not candidates:
        return trimmed
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


class _MediaFormat(ParentedElementProxy):
    """Provides access to formatting properties for a Media object.

    Media format properties are things like start point, volume, and
    compression type.
    """
