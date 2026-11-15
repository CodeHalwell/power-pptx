"""Utility functions and classes."""

from __future__ import annotations

import functools
from typing import Any, Callable, Generic, NamedTuple, TypeVar, cast


def _coerce_emu(value):
    """Internal: coerce a coordinate value to integer EMU.

    Accepts int / Length passes through unchanged, floats are rounded
    half-to-even, and ``None`` is passed through (callers may use ``None``
    for "don't set"). ``bool`` is rejected — booleans are an int subclass
    in Python but a boolean coordinate is always a programming error.

    OOXML's ``CT_Point2D`` (``<a:off>``) requires ``x``/``y`` to be
    ``xs:long`` and ``CT_PositiveSize2D`` (``<a:ext>``) requires
    ``cx``/``cy`` to be ``xs:nonNegativeInteger``. Float-valued strings
    in those attributes are schema-invalid; PowerPoint's strict
    open-time validator rejects them with the "Repair?" dialog even
    though python-pptx, the OOXML XSDs, and LibreOffice all accept
    them silently. Coercing at constructor entry catches the common
    case of ``(Inches(N) - gutter) / 2`` producing a float.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("bool is not a valid EMU coordinate")
    if isinstance(value, int):
        return value
    # Reject str/bytes explicitly — they're convertible via float() but
    # passing a coordinate as a string is always a programming error,
    # not a unit-conversion case we want to silently accept.
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError(
            f"Expected int, float, or Emu-derived length; got "
            f"{type(value).__name__}: {value!r}"
        )
    if isinstance(value, float):
        try:
            return int(round(value))
        except (OverflowError, ValueError) as exc:
            # NaN → ValueError, ±inf → OverflowError. Normalise to
            # TypeError so callers get a single, informative exception.
            raise TypeError(
                f"Cannot coerce non-finite float to EMU: {value!r}"
            ) from exc
    try:
        return int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        raise TypeError(
            f"Expected int, float, or Emu-derived length; got "
            f"{type(value).__name__}: {value!r}"
        )


class Length(int):
    """Base class for length classes Inches, Emu, Cm, Mm, and Pt.

    Provides properties for converting length values to convenient units.
    """

    _EMUS_PER_INCH = 914400
    _EMUS_PER_CENTIPOINT = 127
    _EMUS_PER_CM = 360000
    _EMUS_PER_MM = 36000
    _EMUS_PER_PT = 12700

    def __new__(cls, emu: int):
        return int.__new__(cls, emu)

    @property
    def inches(self) -> float:
        """Floating point length in inches."""
        return self / float(self._EMUS_PER_INCH)

    @property
    def centipoints(self) -> int:
        """Integer length in hundredths of a point (1/7200 inch).

        Used internally because PowerPoint stores font size in centipoints.
        """
        return self // self._EMUS_PER_CENTIPOINT

    @property
    def cm(self) -> float:
        """Floating point length in centimeters."""
        return self / float(self._EMUS_PER_CM)

    @property
    def emu(self) -> int:
        """Integer length in English Metric Units."""
        return self

    @property
    def mm(self) -> float:
        """Floating point length in millimeters."""
        return self / float(self._EMUS_PER_MM)

    @property
    def pt(self) -> float:
        """Floating point length in points."""
        return self / float(self._EMUS_PER_PT)


class Inches(Length):
    """Convenience constructor for length in inches."""

    def __new__(cls, inches: float):
        emu = int(inches * Length._EMUS_PER_INCH)
        return Length.__new__(cls, emu)


class Centipoints(Length):
    """Convenience constructor for length in hundredths of a point."""

    def __new__(cls, centipoints: int):
        emu = int(centipoints * Length._EMUS_PER_CENTIPOINT)
        return Length.__new__(cls, emu)


class Cm(Length):
    """Convenience constructor for length in centimeters."""

    def __new__(cls, cm: float):
        emu = int(cm * Length._EMUS_PER_CM)
        return Length.__new__(cls, emu)


class Emu(Length):
    """Convenience constructor for length in english metric units."""

    def __new__(cls, emu: int):
        return Length.__new__(cls, int(emu))


class Mm(Length):
    """Convenience constructor for length in millimeters."""

    def __new__(cls, mm: float):
        emu = int(mm * Length._EMUS_PER_MM)
        return Length.__new__(cls, emu)


class Pt(Length):
    """Convenience value class for specifying a length in points."""

    def __new__(cls, points: float):
        emu = int(points * Length._EMUS_PER_PT)
        return Length.__new__(cls, emu)


#: The smallest width or height a slide can have: one inch. PowerPoint's own
#: limit, and the lower bound of ``ST_SlideSizeCoordinate`` in the file format.
MIN_SLIDE_SIZE = Inches(1)

#: The largest width or height a slide can have: 56 inches (142.24 cm).
#: PowerPoint's own limit, and the upper bound of ``ST_SlideSizeCoordinate``
#: in the file format.
MAX_SLIDE_SIZE = Inches(56)


class SlideSize(NamedTuple):
    """A slide width and height, and the factor that brought them inside the limits.

    Returned by :func:`fit_slide_size` and
    :meth:`Presentation.set_slide_size
    <power_pptx.presentation.Presentation.set_slide_size>`. It unpacks like
    the tuple it is::

        width, height, scale = fit_slide_size(Inches(80), Inches(11.25))
    """

    #: Slide width, a |Length|.
    width: Length
    #: Slide height, a |Length|.
    height: Length
    #: What the requested size was multiplied by: ``1.0`` when it already fit,
    #: less when it had to shrink, more when it had to grow. Multiply content
    #: coordinates laid out for the requested size by this to match.
    scale: float


def _inches_str(emu: int) -> str:
    """`emu` as a short number of inches for a message, like ``56`` or ``7.875``."""
    return "%g" % Length(emu).inches


def fit_slide_size(width: float, height: float) -> SlideSize:
    """Return the size nearest `width` x `height`, in the same proportions, a slide can have.

    A slide can be no smaller than :data:`MIN_SLIDE_SIZE` (1 inch) and no
    larger than :data:`MAX_SLIDE_SIZE` (56 inches) in either direction, which
    a video wall specified in pixels easily exceeds. This scales such a size
    down to the largest one that fits, keeping its aspect ratio::

        from power_pptx.util import Inches, fit_slide_size

        # a 7680 x 1080 px wall, at 96 px to the inch, is 80" x 11.25"
        width, height, scale = fit_slide_size(Inches(7680 / 96), Inches(1080 / 96))
        # width == Inches(56), height == Inches(7.875), scale == 0.7

    `width` and `height` are lengths (anything :class:`Inches`, :class:`Cm`,
    :class:`Pt` and the rest produce, or the result of arithmetic on them).
    The result is a :class:`SlideSize`:

    * A size already inside the limits comes back unchanged with ``scale``
      ``1.0``. It is never enlarged because there is room; to get the largest
      slide of some shape, ask for one that is too big.
    * A size that is too large is scaled down until its longer side is
      exactly the maximum (``scale`` below 1).
    * A size that is too small is scaled up until its shorter side is exactly
      the minimum (``scale`` above 1).

    ``scale`` is what the requested size was multiplied by, so content laid
    out for that size lands in the same place when its coordinates are
    multiplied by it too.

    Raises |ValueError| if `width` or `height` is not positive, or if the
    shape is more elongated than 56:1 — the longer side would have to exceed
    the maximum for the shorter one to reach the minimum, so no slide has
    those proportions.
    """
    w, h = _coerce_emu(width), _coerce_emu(height)
    if w is None or h is None:
        raise TypeError("width and height are both required, got %r and %r" % (width, height))
    if w <= 0 or h <= 0:
        raise ValueError("slide width and height must be positive, got %d and %d EMU" % (w, h))

    lo, hi = int(MIN_SLIDE_SIZE), int(MAX_SLIDE_SIZE)
    longer, shorter = max(w, h), min(w, h)

    # -- compared as integers, so a shape of exactly 56:1 is not lost to rounding --
    if longer * lo > shorter * hi:
        raise ValueError(
            "no slide can be %s x %s inches or any size in those proportions (%.4g:1): "
            "the sides of a slide must be between %s and %s inches, so the most elongated "
            "one is %d:1"
            % (
                _inches_str(w),
                _inches_str(h),
                longer / float(shorter),
                _inches_str(lo),
                _inches_str(hi),
                hi // lo,
            )
        )

    if longer > hi:
        # -- too large: the longer side lands exactly on the maximum --
        fitted_longer, fitted_shorter = hi, _nearest_int(shorter * hi, longer)
        scale = hi / float(longer)
    elif shorter < lo:
        # -- too small: the shorter side lands exactly on the minimum --
        fitted_longer, fitted_shorter = _nearest_int(longer * lo, shorter), lo
        scale = lo / float(shorter)
    else:
        return SlideSize(Emu(w), Emu(h), 1.0)

    if w >= h:
        return SlideSize(Emu(fitted_longer), Emu(fitted_shorter), scale)
    return SlideSize(Emu(fitted_shorter), Emu(fitted_longer), scale)


def _nearest_int(numerator: int, denominator: int) -> int:
    """The integer nearest `numerator` / `denominator`, both positive, without floats."""
    return (2 * numerator + denominator) // (2 * denominator)


_T = TypeVar("_T")


class lazyproperty(Generic[_T]):
    """Decorator like @property, but evaluated only on first access.

    Like @property, this can only be used to decorate methods having only a `self` parameter, and
    is accessed like an attribute on an instance, i.e. trailing parentheses are not used. Unlike
    @property, the decorated method is only evaluated on first access; the resulting value is
    cached and that same value returned on second and later access without re-evaluation of the
    method.

    Like @property, this class produces a *data descriptor* object, which is stored in the __dict__
    of the *class* under the name of the decorated method ('fget' nominally). The cached value is
    stored in the __dict__ of the *instance* under that same name.

    Because it is a data descriptor (as opposed to a *non-data descriptor*), its `__get__()` method
    is executed on each access of the decorated attribute; the __dict__ item of the same name is
    "shadowed" by the descriptor.

    While this may represent a performance improvement over a property, its greater benefit may be
    its other characteristics. One common use is to construct collaborator objects, removing that
    "real work" from the constructor, while still only executing once. It also de-couples client
    code from any sequencing considerations; if it's accessed from more than one location, it's
    assured it will be ready whenever needed.

    Loosely based on: https://stackoverflow.com/a/6849299/1902513.

    A lazyproperty is read-only. There is no counterpart to the optional "setter" (or deleter)
    behavior of an @property. This is critically important to maintaining its immutability and
    idempotence guarantees. Attempting to assign to a lazyproperty raises AttributeError
    unconditionally.

    The parameter names in the methods below correspond to this usage example::

        class Obj(object)

            @lazyproperty
            def fget(self):
                return 'some result'

        obj = Obj()

    Not suitable for wrapping a function (as opposed to a method) because it is not callable.
    """

    def __init__(self, fget: Callable[..., _T]) -> None:
        """*fget* is the decorated method (a "getter" function).

        A lazyproperty is read-only, so there is only an *fget* function (a regular
        @property can also have an fset and fdel function). This name was chosen for
        consistency with Python's `property` class which uses this name for the
        corresponding parameter.
        """
        # --- maintain a reference to the wrapped getter method
        self._fget = fget
        # --- and store the name of that decorated method
        self._name = fget.__name__
        # --- adopt fget's __name__, __doc__, and other attributes
        functools.update_wrapper(self, fget)  # pyright: ignore

    def __get__(self, obj: Any, type: Any = None) -> _T:
        """Called on each access of 'fget' attribute on class or instance.

        *self* is this instance of a lazyproperty descriptor "wrapping" the property
        method it decorates (`fget`, nominally).

        *obj* is the "host" object instance when the attribute is accessed from an
        object instance, e.g. `obj = Obj(); obj.fget`. *obj* is None when accessed on
        the class, e.g. `Obj.fget`.

        *type* is the class hosting the decorated getter method (`fget`) on both class
        and instance attribute access.
        """
        # --- when accessed on class, e.g. Obj.fget, just return this descriptor
        # --- instance (patched above to look like fget).
        if obj is None:
            return self  # type: ignore

        # --- when accessed on instance, start by checking instance __dict__ for
        # --- item with key matching the wrapped function's name
        value = obj.__dict__.get(self._name)
        if value is None:
            # --- on first access, the __dict__ item will be absent. Evaluate fget()
            # --- and store that value in the (otherwise unused) host-object
            # --- __dict__ value of same name ('fget' nominally)
            value = self._fget(obj)
            obj.__dict__[self._name] = value
        return cast(_T, value)

    def __set__(self, obj: Any, value: Any) -> None:
        """Raises unconditionally, to preserve read-only behavior.

        This decorator is intended to implement immutable (and idempotent) object
        attributes. For that reason, assignment to this property must be explicitly
        prevented.

        If this __set__ method was not present, this descriptor would become a
        *non-data descriptor*. That would be nice because the cached value would be
        accessed directly once set (__dict__ attrs have precedence over non-data
        descriptors on instance attribute lookup). The problem is, there would be
        nothing to stop assignment to the cached value, which would overwrite the result
        of `fget()` and break both the immutability and idempotence guarantees of this
        decorator.

        The performance with this __set__() method in place was roughly 0.4 usec per
        access when measured on a 2.8GHz development machine; so quite snappy and
        probably not a rich target for optimization efforts.
        """
        raise AttributeError("can't set attribute")
