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

    from power_pptx.design.tokens import DesignTokens
    from power_pptx.dml.color import RGBColor
    from power_pptx.util import Pt

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

from power_pptx.dml.color import RGBColor
from power_pptx.util import Emu, Length, Pt

if TYPE_CHECKING:
    from power_pptx.theme import Theme


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
            if size is not None:
                size = _coerce_length(size)
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
    """A shadow token, mirroring :class:`power_pptx.dml.effect.ShadowFormat`."""

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
        if blur is not None:
            blur = _coerce_length(blur)
        distance = value.get("distance")
        if distance is not None:
            distance = _coerce_length(distance)
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
    def from_preset(cls, name: str) -> "DesignTokens":
        """Load a built-in token preset by *name*.

        The presets are intentionally small and opinionated — they
        cover the styles most decks reach for first so callers don't
        have to invent a palette from scratch.  Available presets:

        * ``"modern_light"`` — clean, neutral background with a single
          accent.  Good default for product / engineering decks.
        * ``"modern_dark"`` — same shape as modern_light, dark canvas.
        * ``"corporate_navy"`` — navy + warm accent, banded surfaces;
          reads as conservative / formal.
        * ``"vibrant"`` — saturated palette for marketing / launch
          decks.

        Each preset populates ``palette``, ``typography``, ``radii``,
        ``shadows``, and ``spacings``.  Callers can layer overrides on
        top with ``DesignTokens.from_preset("modern_light").merge(...)``
        or simply mutate the returned instance — the dataclass fields
        are mutable.
        """
        spec = _PRESETS.get(name)
        if spec is None:
            raise ValueError(
                f"Unknown preset {name!r}; choose from {sorted(_PRESETS)}"
            )
        return cls.from_dict(spec)

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
        an already-opened :class:`power_pptx.presentation.Presentation`.  The
        slots populated are::

            palette:    accent1..accent6, dk1, dk2, lt1, lt2, hyperlink,
                        followed_hyperlink (under their canonical names)
            typography: 'heading' (theme major font),
                        'body'    (theme minor font)

        Radii, spacings, and shadows are not encoded in the OOXML theme;
        callers should layer those in via :meth:`from_dict` overrides.
        """
        from power_pptx.api import Presentation
        from power_pptx.enum.dml import MSO_THEME_COLOR

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

    def with_overrides(
        self, overrides: Mapping[str, Any]
    ) -> "DesignTokens":
        """Return a new :class:`DesignTokens` with dotted-path *overrides* layered on.

        *overrides* is a flat mapping of dotted keys to values, e.g.::

            tokens.with_overrides({
                "palette.primary": "#FF6600",
                "typography.heading.size": Pt(40),
                "radii.md": Pt(12),
            })

        The leading segment is the token category (``palette`` /
        ``typography`` / ``radii`` / ``shadows`` / ``spacings``), the
        next segment is the slot name, and any further segments
        navigate into a typography or shadow token (e.g.
        ``typography.heading.size`` updates only the ``size`` field of
        the existing heading token).

        Useful for per-call recipe overrides::

            kpi_slide(prs, ..., tokens=tokens.with_overrides({
                "palette.primary": "#FF6600",
            }))

        without forking the base token set.
        """
        # Deep-copy at the dict level so callers don't accidentally
        # mutate the base.  Token dataclasses themselves are frozen.
        palette = dict(self.palette)
        typography = dict(self.typography)
        radii = dict(self.radii)
        shadows = dict(self.shadows)
        spacings = dict(self.spacings)

        bins: dict[str, MutableMapping[str, Any]] = {
            "palette": palette,
            "typography": typography,
            "radii": radii,
            "shadows": shadows,
            "spacings": spacings,
        }

        for key, value in overrides.items():
            parts = key.split(".")
            if len(parts) < 2:
                raise ValueError(
                    f"override key {key!r} must be dotted, e.g. "
                    "'palette.primary' or 'typography.heading.size'"
                )
            category = parts[0]
            target = bins.get(category)
            if target is None:
                raise ValueError(
                    f"unknown override category {category!r}; choose "
                    f"from {sorted(bins)}"
                )
            if len(parts) == 2:
                slot = parts[1]
                if category == "palette":
                    target[slot] = _coerce_color(value)
                elif category in ("radii", "spacings"):
                    target[slot] = _coerce_length(value)
                elif category == "typography":
                    target[slot] = TypographyToken.from_value(value)
                elif category == "shadows":
                    target[slot] = ShadowToken.from_value(value)
            else:
                # Sub-field override — merge into an existing token.
                slot = parts[1]
                field_name = parts[2]
                existing = target.get(slot)
                if category == "typography":
                    base = (
                        existing
                        if isinstance(existing, TypographyToken)
                        else TypographyToken(family="Calibri")
                    )
                    target[slot] = _typography_with_field(base, field_name, value)
                elif category == "shadows":
                    base = (
                        existing if isinstance(existing, ShadowToken) else ShadowToken()
                    )
                    target[slot] = _shadow_with_field(base, field_name, value)
                else:
                    raise ValueError(
                        f"sub-field override {key!r} only supported on "
                        "typography and shadows"
                    )

        return DesignTokens(
            palette=palette,
            typography=typography,
            radii=radii,
            shadows=shadows,
            spacings=spacings,
        )

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


def _typography_with_field(
    base: TypographyToken, field_name: str, value: Any
) -> TypographyToken:
    """Return a copy of *base* with ``field_name`` set to *value*."""
    fields = {
        "family": base.family,
        "size": base.size,
        "bold": base.bold,
        "italic": base.italic,
        "color": base.color,
    }
    if field_name not in fields:
        raise ValueError(
            f"unknown typography field {field_name!r}; choose from "
            f"{sorted(fields)}"
        )
    if field_name == "size" and value is not None:
        value = _coerce_length(value)
    elif field_name == "color" and value is not None:
        value = _coerce_color(value)
    fields[field_name] = value
    return TypographyToken(**fields)


def _shadow_with_field(
    base: ShadowToken, field_name: str, value: Any
) -> ShadowToken:
    """Return a copy of *base* with ``field_name`` set to *value*."""
    fields = {
        "blur_radius": base.blur_radius,
        "distance": base.distance,
        "direction": base.direction,
        "color": base.color,
        "alpha": base.alpha,
    }
    if field_name not in fields:
        raise ValueError(
            f"unknown shadow field {field_name!r}; choose from "
            f"{sorted(fields)}"
        )
    if field_name in ("blur_radius", "distance") and value is not None:
        value = _coerce_length(value)
    elif field_name == "color" and value is not None:
        value = _coerce_color(value)
    elif field_name in ("direction", "alpha") and value is not None:
        value = float(value)
    fields[field_name] = value
    return ShadowToken(**fields)


# ---------------------------------------------------------------------------
# Built-in presets — small, opinionated palettes that cover the most-common
# deck styles so callers don't have to invent a brand from scratch.
# ---------------------------------------------------------------------------

_PRESETS: Mapping[str, Mapping[str, Any]] = {
    "modern_light": {
        "palette": {
            "primary":   "#3B5BDB",
            "neutral":   "#1F2933",
            "muted":     "#7B8794",
            "surface":   "#F5F7FA",
            "on_primary": "#FFFFFF",
            "lt1":       "#FFFFFF",
            "lt2":       "#E4E7EB",
            "positive":  "#0CA678",
            "negative":  "#E03131",
            "success":   "#0CA678",
            "danger":    "#E03131",
        },
        "typography": {
            "heading": {"family": "Inter", "size": Pt(32), "bold": True},
            "body":    {"family": "Inter", "size": Pt(16)},
        },
        "radii":    {"sm": Pt(4), "md": Pt(8), "lg": Pt(16)},
        "spacings": {"xs": Pt(4), "sm": Pt(8), "md": Pt(16), "lg": Pt(32)},
        "shadows": {
            "card": {
                "blur_radius": Pt(8),
                "distance":    Pt(2),
                "direction":   90.0,
                "color":       "#000000",
                "alpha":       0.18,
            },
        },
    },
    "modern_dark": {
        "palette": {
            "primary":   "#7C5CFF",
            "neutral":   "#E4E7EB",
            "muted":     "#7B8794",
            "surface":   "#1F2933",
            "on_primary": "#0B0F19",
            "lt1":       "#323F4B",
            "lt2":       "#3E4C59",
            "positive":  "#3DD68C",
            "negative":  "#FF6B6B",
            "success":   "#3DD68C",
            "danger":    "#FF6B6B",
        },
        "typography": {
            "heading": {"family": "Inter", "size": Pt(32), "bold": True},
            "body":    {"family": "Inter", "size": Pt(16)},
        },
        "radii":    {"sm": Pt(4), "md": Pt(8), "lg": Pt(16)},
        "spacings": {"xs": Pt(4), "sm": Pt(8), "md": Pt(16), "lg": Pt(32)},
        "shadows": {
            "card": {
                "blur_radius": Pt(12),
                "distance":    Pt(3),
                "direction":   90.0,
                "color":       "#000000",
                "alpha":       0.45,
            },
        },
    },
    "corporate_navy": {
        "palette": {
            "primary":   "#0B2545",
            "neutral":   "#13315C",
            "muted":     "#8DA9C4",
            "surface":   "#EEF4ED",
            "on_primary": "#FFFFFF",
            "lt1":       "#FFFFFF",
            "lt2":       "#D6DDE0",
            "positive":  "#247B7B",
            "negative":  "#A23B3B",
            "success":   "#247B7B",
            "danger":    "#A23B3B",
        },
        "typography": {
            "heading": {"family": "Source Serif Pro", "size": Pt(34), "bold": True},
            "body":    {"family": "Source Sans Pro", "size": Pt(16)},
        },
        "radii":    {"sm": Pt(2), "md": Pt(4), "lg": Pt(8)},
        "spacings": {"xs": Pt(4), "sm": Pt(8), "md": Pt(16), "lg": Pt(32)},
        "shadows": {
            "card": {
                "blur_radius": Pt(6),
                "distance":    Pt(1),
                "direction":   90.0,
                "color":       "#000000",
                "alpha":       0.12,
            },
        },
    },
    "vibrant": {
        "palette": {
            "primary":   "#FF3366",
            "neutral":   "#22223B",
            "muted":     "#9A8C98",
            "surface":   "#FFF8F0",
            "on_primary": "#FFFFFF",
            "lt1":       "#FFFFFF",
            "lt2":       "#FFE5D9",
            "positive":  "#06D6A0",
            "negative":  "#EF233C",
            "success":   "#06D6A0",
            "danger":    "#EF233C",
        },
        "typography": {
            "heading": {"family": "Poppins", "size": Pt(36), "bold": True},
            "body":    {"family": "Poppins", "size": Pt(16)},
        },
        "radii":    {"sm": Pt(6), "md": Pt(12), "lg": Pt(24)},
        "spacings": {"xs": Pt(4), "sm": Pt(8), "md": Pt(16), "lg": Pt(32)},
        "shadows": {
            "card": {
                "blur_radius": Pt(14),
                "distance":    Pt(4),
                "direction":   90.0,
                "color":       "#000000",
                "alpha":       0.20,
            },
        },
    },
}
