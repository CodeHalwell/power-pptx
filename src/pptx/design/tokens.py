"""Design tokens — palette, typography, radii, shadows, spacings.

A :class:`DesignTokens` object is an opinionated, source-agnostic
container for the design decisions that recur across a deck.  It is the
foundation of the "design system layer" described in Phase 9 of the
roadmap; recipes and the :attr:`shape.style` facade resolve their inputs
through tokens rather than naming raw EMU/RGB values inline.

Tokens can be built three ways:

* :meth:`DesignTokens.from_dict` — a plain Python dict (the canonical form).
* :meth:`DesignTokens.from_yaml` — a YAML brand file (requires ``pyyaml``).
* :meth:`DesignTokens.from_pptx` — extract palette + fonts from an
  existing ``.pptx`` / ``.potx`` file's theme.

Example::

    from pptx.design.tokens import DesignTokens
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    tokens = DesignTokens.from_dict({
        "palette": {
            "primary":   RGBColor(0x3C, 0x2F, 0x80),
            "secondary": "#FF6600",
            "neutral":   (0x33, 0x33, 0x33),
        },
        "typography": {
            "heading": {"family": "Inter", "size": Pt(36)},
            "body":    {"family": "Inter", "size": Pt(14)},
        },
        "radii":    {"sm": Pt(4), "md": Pt(8), "lg": Pt(16)},
        "spacings": {"xs": Pt(4), "sm": Pt(8), "md": Pt(16), "lg": Pt(32)},
        "shadows": {
            "card": {"blur_radius": Pt(8), "distance": Pt(2),
                      "direction": 90, "color": RGBColor(0, 0, 0),
                      "alpha": 0.25},
        },
    })

    print(tokens.palette["primary"])      # RGBColor(0x3C, 0x2F, 0x80)
    print(tokens.typography["body"].family)  # "Inter"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, MutableMapping, Optional, Union

from pptx.dml.color import RGBColor
from pptx.util import Emu, Length, Pt

if TYPE_CHECKING:
    from pptx.theme import Theme


ColorSpec = Union[RGBColor, str, tuple]


# ---------------------------------------------------------------------------
# Sub-token value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TypographyToken:
    """A typography token: font family, size, weight, optional color.

    Only :attr:`family` is required; the other fields fall back to
    PowerPoint defaults when unset.
    """

    family: str
    size: Optional[Length] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    color: Optional[RGBColor] = None

    @classmethod
    def from_value(cls, value: Any) -> "TypographyToken":
        """Coerce a dict / string / existing token into a :class:`TypographyToken`.

        A bare string is interpreted as a font family with no other
        attributes set; a mapping is unpacked through :meth:`__init__`.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(family=value)
        if isinstance(value, Mapping):
            family = value.get("family")
            if not isinstance(family, str) or not family:
                raise ValueError(
                    "typography token requires a non-empty 'family' string"
                )
            size = value.get("size")
            if size is not None and not isinstance(size, Length):
                size = Emu(int(size))
            color = value.get("color")
            if color is not None:
                color = _coerce_color(color)
            return cls(
                family=family,
                size=size,
                bold=value.get("bold"),
                italic=value.get("italic"),
                color=color,
            )
        raise TypeError(
            f"cannot build TypographyToken from {type(value).__name__}"
        )


@dataclass(frozen=True)
class ShadowToken:
    """A shadow token, mirroring :class:`pptx.dml.effect.ShadowFormat`."""

    blur_radius: Optional[Length] = None
    distance: Optional[Length] = None
    direction: Optional[float] = None
    color: Optional[RGBColor] = None
    alpha: Optional[float] = None

    @classmethod
    def from_value(cls, value: Any) -> "ShadowToken":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError(
                f"cannot build ShadowToken from {type(value).__name__}"
            )
        blur = value.get("blur_radius")
        if blur is not None and not isinstance(blur, Length):
            blur = Emu(int(blur))
        distance = value.get("distance")
        if distance is not None and not isinstance(distance, Length):
            distance = Emu(int(distance))
        direction = value.get("direction")
        if direction is not None:
            direction = float(direction)
        alpha = value.get("alpha")
        if alpha is not None:
            alpha = float(alpha)
            if not 0.0 <= alpha <= 1.0:
                raise ValueError("shadow alpha must be in [0.0, 1.0]")
        color = value.get("color")
        if color is not None:
            color = _coerce_color(color)
        return cls(
            blur_radius=blur,
            distance=distance,
            direction=direction,
            color=color,
            alpha=alpha,
        )


# ---------------------------------------------------------------------------
# DesignTokens
# ---------------------------------------------------------------------------


@dataclass
class DesignTokens:
    """A bag of design tokens — palette, typography, radii, shadows, spacings.

    Tokens are mutable so callers can layer overrides on top of a loaded
    base set::

        tokens = DesignTokens.from_pptx("brand.pptx")
        tokens.palette["primary"] = RGBColor(0xFF, 0x00, 0x00)
    """

    palette: MutableMapping[str, RGBColor] = field(default_factory=dict)
    typography: MutableMapping[str, TypographyToken] = field(default_factory=dict)
    radii: MutableMapping[str, Length] = field(default_factory=dict)
    shadows: MutableMapping[str, ShadowToken] = field(default_factory=dict)
    spacings: MutableMapping[str, Length] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, spec: Mapping[str, Any]) -> "DesignTokens":
        """Build a token set from a plain dict.

        Unknown top-level keys are ignored so a single brand-spec file
        can carry extra application-specific data alongside the design
        tokens.
        """
        palette = {
            name: _coerce_color(value)
            for name, value in (spec.get("palette") or {}).items()
        }
        typography = {
            name: TypographyToken.from_value(value)
            for name, value in (spec.get("typography") or {}).items()
        }
        radii = {
            name: _coerce_length(value)
            for name, value in (spec.get("radii") or {}).items()
        }
        spacings = {
            name: _coerce_length(value)
            for name, value in (spec.get("spacings") or {}).items()
        }
        shadows = {
            name: ShadowToken.from_value(value)
            for name, value in (spec.get("shadows") or {}).items()
        }
        return cls(
            palette=palette,
            typography=typography,
            radii=radii,
            shadows=shadows,
            spacings=spacings,
        )

    @classmethod
    def from_yaml(cls, path: str) -> "DesignTokens":
        """Load a token set from a YAML brand file.

        Requires ``pyyaml``; raises :class:`ImportError` with a clear
        installation hint when the dependency is missing.
        """
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "DesignTokens.from_yaml requires pyyaml; install with "
                "`pip install pyyaml`"
            ) from exc
        with open(path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        if not isinstance(spec, Mapping):
            raise ValueError(
                f"YAML at {path!r} did not parse to a mapping"
            )
        return cls.from_dict(spec)

    @classmethod
    def from_pptx(cls, path_or_prs: Any) -> "DesignTokens":
        """Extract palette and typography tokens from a deck's theme.

        *path_or_prs* may be a path to a ``.pptx`` / ``.potx`` file or
        an already-opened :class:`pptx.presentation.Presentation`.  The
        slots populated are::

            palette:    accent1..accent6, dk1, dk2, lt1, lt2, hyperlink,
                        followed_hyperlink (under their canonical names)
            typography: 'heading' (theme major font),
                        'body'    (theme minor font)

        Radii, spacings, and shadows are not encoded in the OOXML theme;
        callers should layer those in via :meth:`from_dict` overrides.
        """
        from pptx.api import Presentation
        from pptx.enum.dml import MSO_THEME_COLOR

        if isinstance(path_or_prs, str):
            prs = Presentation(path_or_prs)
        else:
            prs = path_or_prs

        theme: "Theme" = prs.theme
        slot_names = {
            MSO_THEME_COLOR.ACCENT_1: "accent1",
            MSO_THEME_COLOR.ACCENT_2: "accent2",
            MSO_THEME_COLOR.ACCENT_3: "accent3",
            MSO_THEME_COLOR.ACCENT_4: "accent4",
            MSO_THEME_COLOR.ACCENT_5: "accent5",
            MSO_THEME_COLOR.ACCENT_6: "accent6",
            MSO_THEME_COLOR.DARK_1: "dk1",
            MSO_THEME_COLOR.DARK_2: "dk2",
            MSO_THEME_COLOR.LIGHT_1: "lt1",
            MSO_THEME_COLOR.LIGHT_2: "lt2",
            MSO_THEME_COLOR.HYPERLINK: "hyperlink",
            MSO_THEME_COLOR.FOLLOWED_HYPERLINK: "followed_hyperlink",
        }
        palette: dict[str, RGBColor] = {}
        for slot, name in slot_names.items():
            try:
                rgb = theme.colors[slot]
            except (KeyError, AttributeError):
                continue
            if rgb is not None:
                palette[name] = rgb

        typography: dict[str, TypographyToken] = {}
        major = theme.fonts.major
        minor = theme.fonts.minor
        if major:
            typography["heading"] = TypographyToken(family=major)
        if minor:
            typography["body"] = TypographyToken(family=minor)

        return cls(palette=palette, typography=typography)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def merge(self, other: "DesignTokens") -> "DesignTokens":
        """Return a new :class:`DesignTokens` with *other*'s values layered over self.

        Each named slot in *other* overrides this token set's value for
        the same name; slots that *other* doesn't define are kept.
        """
        return DesignTokens(
            palette={**self.palette, **other.palette},
            typography={**self.typography, **other.typography},
            radii={**self.radii, **other.radii},
            shadows={**self.shadows, **other.shadows},
            spacings={**self.spacings, **other.spacings},
        )


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _coerce_color(value: Any) -> RGBColor:
    if isinstance(value, RGBColor):
        return value
    if isinstance(value, str):
        s = value.lstrip("#")
        if len(s) != 6:
            raise ValueError(
                f"hex color string must be 6 hex digits, got {value!r}"
            )
        return RGBColor(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    if isinstance(value, tuple) and len(value) == 3:
        return RGBColor(int(value[0]), int(value[1]), int(value[2]))
    raise TypeError(
        f"cannot coerce {value!r} to RGBColor; "
        "expected RGBColor, hex string, or 3-tuple"
    )


def _coerce_length(value: Any) -> Length:
    if isinstance(value, Length):
        return value
    if isinstance(value, int):
        return Emu(value)
    if isinstance(value, float):
        # Treat bare floats as points — the most common authoring unit.
        return Pt(value)
    raise TypeError(
        f"cannot coerce {value!r} to Length; "
        "expected Length, int (EMU), or float (points)"
    )
