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

Length units
------------

Every length-valued token field (typography ``size``, ``radii``,
``spacings``, shadow ``blur_radius`` / ``distance``) accepts either a
:class:`~power_pptx.util.Length` (``Pt(8)``, ``Emu(101600)``,
``Inches(0.1)``), which is kept exactly, or a **bare number, which is
read as points**.  ``36`` and ``36.0`` therefore mean the same thing, so a
JSON or YAML brand file — where a serialiser may write either — behaves
the same as the Python dict above.

One backward-compatibility exception: a bare *integer* of ``12700`` or
more is read as EMU, which is what every bare integer used to mean.
``12700`` EMU is one point, so no realistic point size is that large and
no realistic EMU value is smaller.  Pass ``Pt(...)`` when a value that
large really is in points.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, MutableMapping, Optional, Union

from power_pptx.dml.color import RGBColor
from power_pptx.util import Emu, Length, Pt

if TYPE_CHECKING:
    from power_pptx.theme import Theme


ColorSpec = Union[RGBColor, str, tuple]

#: The token categories, in the order :class:`DesignTokens` declares them.
_SECTIONS = ("palette", "typography", "radii", "shadows", "spacings")

#: Field names of a typography / shadow token, as accepted in a mapping.
_TYPOGRAPHY_FIELDS = ("family", "size", "bold", "italic", "color")
_SHADOW_FIELDS = ("blur_radius", "distance", "direction", "color", "alpha")

#: Friendlier spellings accepted for a shadow field.  ``blur`` is what the
#: CSS ``box-shadow`` vocabulary (and this project's own docs and examples)
#: call the blur radius.
_SHADOW_ALIASES = {"blur": "blur_radius"}

#: One point, in EMU.  A bare integer at or above this is read as EMU (what
#: every bare integer used to mean); anything smaller is read as points.
_EMU_INT_THRESHOLD = 12700

#: The font-size range OOXML can store (``ST_TextFontSize``: 1pt to 4000pt).
_MIN_FONT_SIZE = Pt(1)
_MAX_FONT_SIZE = Pt(4000)


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

        A mapping may carry ``family`` (required), ``size``, ``bold``,
        ``italic`` and ``color``.  Any other key raises :class:`ValueError`
        (with a did-you-mean hint) rather than being dropped, so a typo
        such as ``"sise"`` cannot silently lose the size.  A bare number
        for ``size`` is points; see the module docstring for the rule.
        """
        return _typography_from_value(value, "typography token")


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
        """Coerce a mapping / existing token into a :class:`ShadowToken`.

        A mapping may carry ``blur_radius`` (``blur`` is accepted as an
        alias), ``distance``, ``direction`` (degrees), ``color`` and
        ``alpha`` (0.0–1.0).  Any other key raises :class:`ValueError` with
        a did-you-mean hint rather than being dropped.  Bare numbers for
        ``blur_radius`` / ``distance`` are points; see the module docstring.
        """
        return _shadow_from_value(value, "shadow token")


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

        The recognised top-level sections are ``palette``, ``typography``,
        ``radii``, ``shadows`` and ``spacings``.  Other top-level keys are
        ignored so a single brand-spec file can carry extra
        application-specific data alongside the design tokens — except a
        key that is a near-miss of a section name (``"palete"``,
        ``"shadow"``), which raises :class:`ValueError`: that is a typo, and
        ignoring it would silently produce an unstyled deck.

        Inside a section nothing is ignored: an unknown typography or
        shadow field raises, and every error names the token it came from
        (``typography.heading.size: ...``).  Bare numbers in length fields
        are points; see the module docstring.
        """
        if not isinstance(spec, Mapping):
            raise TypeError(
                f"design tokens must be a mapping; got {type(spec).__name__}"
            )
        for key in spec:
            if key in _SECTIONS or not isinstance(key, str):
                continue
            hint = _did_you_mean(key, _SECTIONS, cutoff=0.8)
            if hint:
                raise ValueError(
                    f"unknown token section {key!r}{hint}. "
                    f"Sections: {list(_SECTIONS)}"
                )
        palette = {
            name: _coerce_color(value, f"palette.{name}")
            for name, value in _section(spec, "palette").items()
        }
        typography = {
            name: _typography_from_value(value, f"typography.{name}")
            for name, value in _section(spec, "typography").items()
        }
        radii = {
            name: _coerce_length(value, f"radii.{name}")
            for name, value in _section(spec, "radii").items()
        }
        spacings = {
            name: _coerce_length(value, f"spacings.{name}")
            for name, value in _section(spec, "spacings").items()
        }
        shadows = {
            name: _shadow_from_value(value, f"shadows.{name}")
            for name, value in _section(spec, "shadows").items()
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
        spec = _PRESETS.get(name) if isinstance(name, str) else None
        if spec is None:
            hint = (
                _did_you_mean(name.replace("-", "_").lower(), _PRESETS)
                if isinstance(name, str)
                else ""
            )
            raise ValueError(
                f"Unknown preset {name!r}{hint}; choose from {sorted(_PRESETS)}"
            )
        return cls.from_dict(spec)

    @classmethod
    def from_seed(
        cls, seed: ColorSpec, harmony: str = "complementary"
    ) -> "DesignTokens":
        """Generate a full palette from a single *seed* color.

        Uses HSL color-wheel harmony math to derive a coherent set of
        brand colors from one seed, so brand onboarding needs only a
        single hex value.  The output is **deterministic** — the same
        seed and harmony always yield the same palette.

        *seed* accepts the same forms as every color input in this
        module (``RGBColor`` / ``"#RRGGBB"`` / ``(r, g, b)``).

        *harmony* selects how the secondary/accent hues relate to the
        seed on the color wheel:

        * ``"complementary"`` — secondary at +180°, accent at +150°.
        * ``"analogous"``     — secondary at +30°, accent at -30°.
        * ``"triadic"``       — secondary at +120°, accent at +240°.
        * ``"monochromatic"`` — same hue throughout; secondary/accent
          differ only in lightness.

        The returned :class:`DesignTokens` populates the same ``palette``
        keys the built-in presets use (``primary``, ``secondary``,
        ``accent``, ``neutral``, ``muted``, ``surface``, ``background``,
        ``text``, ``on_primary``, ``lt1``, ``lt2``, ``positive``,
        ``negative``, ``success``, ``danger``), so it drops into recipes
        that expect a preset.  Typography, radii, spacings, and shadows
        are left empty for the caller to layer in.
        """
        import colorsys

        valid = ("complementary", "analogous", "triadic", "monochromatic")
        if harmony not in valid:
            raise ValueError(
                f"unknown harmony {harmony!r}; choose from {list(valid)}"
            )

        seed_rgb = _coerce_color(seed)
        h, light, s = colorsys.rgb_to_hls(
            seed_rgb[0] / 255.0, seed_rgb[1] / 255.0, seed_rgb[2] / 255.0
        )

        def from_hsl(hue: float, lightness: float, sat: float) -> RGBColor:
            r, g, b = colorsys.hls_to_rgb(
                hue % 1.0, _clamp01(lightness), _clamp01(sat)
            )
            return RGBColor(round(r * 255), round(g * 255), round(b * 255))

        def shift(deg: float, lightness: float, sat: float) -> RGBColor:
            return from_hsl(h + deg / 360.0, lightness, sat)

        if harmony == "complementary":
            sec_off, acc_off = 180.0, 150.0
        elif harmony == "analogous":
            sec_off, acc_off = 30.0, -30.0
        elif harmony == "triadic":
            sec_off, acc_off = 120.0, 240.0
        else:  # monochromatic
            sec_off, acc_off = 0.0, 0.0

        primary = seed_rgb
        if harmony == "monochromatic":
            secondary = from_hsl(h, light + 0.18, s)
            accent = from_hsl(h, light - 0.18, s)
        else:
            secondary = shift(sec_off, light, s)
            accent = shift(acc_off, light, s)

        # Neutral / muted: desaturate the seed hue toward grey.
        neutral = from_hsl(h, 0.16, s * 0.18)
        muted = from_hsl(h, 0.55, s * 0.25)
        # Surfaces: a near-white tint and a slightly darker band.
        surface = from_hsl(h, 0.97, s * 0.10)
        lt1 = RGBColor(0xFF, 0xFF, 0xFF)
        lt2 = from_hsl(h, 0.92, s * 0.15)
        background = lt1
        text = neutral

        # Foreground over the primary: white over a dark seed, near-black
        # over a light one.
        on_primary = (
            RGBColor(0xFF, 0xFF, 0xFF)
            if _luminance(primary) < 0.5
            else RGBColor(0x10, 0x10, 0x10)
        )

        # Semantic colors are hue-anchored (green / red) so meaning stays
        # legible regardless of brand hue.
        positive = from_hsl(120.0 / 360.0, 0.40, 0.55)
        negative = from_hsl(0.0, 0.48, 0.65)

        palette: dict[str, RGBColor] = {
            "primary": primary,
            "secondary": secondary,
            "accent": accent,
            "neutral": neutral,
            "muted": muted,
            "surface": surface,
            "background": background,
            "text": text,
            "on_primary": on_primary,
            "lt1": lt1,
            "lt2": lt2,
            "positive": positive,
            "negative": negative,
            "success": positive,
            "danger": negative,
        }
        return cls(palette=palette)

    def validate_color_blindness(self, kind: str) -> list[tuple[str, str]]:
        """Return palette color pairs likely confusable under *kind*.

        Simulates one of the common color-vision deficiencies and reports
        every pair of *named* palette colors that the deficiency
        *collapses together* — distinguishable to typical vision, but
        whose sRGB separation drops to under half (and small in absolute
        terms) once the simulation is applied.

        *kind* is one of ``"deuteranopia"``, ``"protanopia"``, or
        ``"tritanopia"``.  The returned list contains ``(name_a, name_b)``
        tuples (each pair once, alphabetically ordered) — an empty list
        means no confusable pairs were found.  A heuristic aid, not a
        clinical tool.
        """
        valid = ("deuteranopia", "protanopia", "tritanopia")
        if kind not in valid:
            raise ValueError(
                f"unknown kind {kind!r}; choose from {list(valid)}"
            )

        names = sorted(self.palette)
        confusable: list[tuple[str, str]] = []
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                ra, rb = self.palette[a], self.palette[b]
                normal = _rgb_distance(ra, rb)
                # Skip pairs already near-identical to normal vision —
                # they're "confusable" by being the same color, not the CVD.
                if normal < 24.0:
                    continue
                sim = _rgb_distance(
                    _simulate_cvd(ra, kind), _simulate_cvd(rb, kind)
                )
                # Flag the pair when the deficiency *collapses* their
                # separation: the simulated distance drops to under half
                # the normal-vision distance and is itself small in
                # absolute terms.  Both conditions matter — a large
                # well-separated pair that merely shrinks proportionally
                # is still distinguishable.
                if sim <= 0.5 * normal and sim < 120.0:
                    confusable.append((a, b))
        return confusable

    @classmethod
    def from_yaml(cls, path: "Union[str, os.PathLike[str]]") -> "DesignTokens":
        """Load a token set from a YAML brand file.

        Requires ``pyyaml``; raises :class:`ImportError` with a clear
        installation hint when the dependency is missing.

        YAML has no ``Pt()``, so write lengths as plain numbers of points
        (``size: 36``, ``radii: {md: 8}``); integers and floats mean the
        same thing.  See the module docstring for the full rule.
        """
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "DesignTokens.from_yaml requires pyyaml; install with "
                "`pip install pyyaml`"
            ) from exc
        with open(path, encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        if not isinstance(spec, Mapping):
            raise ValueError(
                f"YAML at {path!r} did not parse to a mapping"
            )
        return cls.from_dict(spec)

    @classmethod
    def from_pptx(cls, path_or_prs: Any) -> "DesignTokens":
        """Extract palette and typography tokens from a deck's theme.

        *path_or_prs* may be a path to a ``.pptx`` / ``.potx`` file (a
        string or any :class:`os.PathLike`, e.g. :class:`pathlib.Path`), a
        binary file-like object, or an already-opened
        :class:`power_pptx.presentation.Presentation`.  The
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

        if isinstance(path_or_prs, (str, os.PathLike)):
            prs = Presentation(os.fspath(path_or_prs))
        elif hasattr(path_or_prs, "read") and not hasattr(path_or_prs, "theme"):
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
        """Return a new :class:`DesignTokens` with *overrides* layered on.

        Two equivalent input shapes are accepted:

        * **Dotted-path keys** — flat mapping where each key is a
          dotted path through the token tree::

              tokens.with_overrides({
                  "palette.primary": "#FF6600",
                  "typography.heading.size": Pt(40),
                  "radii.md": Pt(12),
              })

        * **Nested dicts** — the same structure expressed as nested
          mappings (matches the README's earlier examples)::

              tokens.with_overrides({
                  "palette": {"primary": "#FF6600"},
                  "typography": {"heading": {"size": Pt(40)}},
                  "radii": {"md": Pt(12)},
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

        Values follow the same rules as :meth:`from_dict`: a bare number in
        a length field is points (``"typography.heading.size": 40`` is
        40pt), and an unknown category, field or over-long path raises
        :class:`ValueError` naming the key.
        """
        if not isinstance(overrides, Mapping):
            raise ValueError(
                "token overrides must be a mapping of dotted paths (or nested "
                f"dicts) to values; got {type(overrides).__name__}"
            )
        overrides = _flatten_overrides(overrides)
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
            _apply_override(bins, key, value)

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


def _flatten_overrides(
    overrides: Mapping[str, Any], _prefix: str = ""
) -> dict[str, Any]:
    """Flatten a nested-dict override spec into dotted-key form.

    Dotted-key inputs round-trip unchanged.  Nested dicts are walked
    recursively, joining segments with ``"."``.  Mixing both styles in
    the same input is allowed — e.g. ``{"palette.primary": ...,
    "typography": {"heading": {"size": ...}}}``.

    Stops descending at non-mapping values; in particular, dataclasses
    like :class:`TypographyToken` and :class:`ShadowToken` are passed
    through whole rather than walked, so callers can supply a token
    instance for a slot.
    """
    flat: dict[str, Any] = {}
    for key, value in overrides.items():
        path = _override_path(_prefix, key)
        if _is_nested_override(value):
            flat.update(_flatten_overrides(value, path))
        else:
            flat[path] = value
    return flat


def _override_path(prefix: str, key: Any) -> str:
    """Join override *key* onto the dotted *prefix*, rejecting non-string keys."""
    if not isinstance(key, str) or not key:
        where = f" under {prefix!r}" if prefix else ""
        raise ValueError(f"override keys must be non-empty strings; got {key!r}{where}")
    return f"{prefix}.{key}" if prefix else key


def _is_nested_override(value: Any) -> bool:
    """True if *value* is a mapping of further overrides to walk, not a slot value.

    Token instances (:class:`TypographyToken`, :class:`ShadowToken`, ...) are
    slot values and are passed through whole.
    """
    return (
        isinstance(value, Mapping)
        and not isinstance(value, RGBColor)
        and not _is_token_value(value)
    )


def _is_token_value(value: Any) -> bool:
    """True if *value* is a typography/shadow/length token shouldn't be flattened."""
    return isinstance(value, (TypographyToken, ShadowToken, Length, RGBColor))


def _apply_override(bins: Mapping[str, MutableMapping[str, Any]], key: str, value: Any) -> None:
    """Apply one dotted-path override *key* to the token *bins*, by category.

    ``category.slot`` replaces the slot with *value* coerced for its
    category; ``category.slot.field`` merges one field into the slot's
    existing typography or shadow token.
    """
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
    if len(parts) > 3:
        raise ValueError(
            f"override key {key!r} is too deep; expected "
            "'category.slot' or 'category.slot.field'"
        )
    if len(parts) == 2:
        target[parts[1]] = _SLOT_COERCERS[category](value, key)
    else:
        target[parts[1]] = _with_override_field(
            category, target.get(parts[1]), parts[2], value, key
        )


def _with_override_field(
    category: str, existing: Any, field_name: str, value: Any, key: str
) -> Any:
    """Return the *existing* slot token with one field replaced by *value*.

    A slot that holds no token of the category's type starts from the
    defaults (Calibri for typography).  Only typography and shadow tokens
    have fields.
    """
    if category == "typography":
        base = (
            existing
            if isinstance(existing, TypographyToken)
            else TypographyToken(family="Calibri")
        )
        return _typography_with_field(base, field_name, value, key)
    if category == "shadows":
        base = existing if isinstance(existing, ShadowToken) else ShadowToken()
        return _shadow_with_field(base, field_name, value, key)
    raise ValueError(
        f"sub-field override {key!r} only supported on "
        "typography and shadows"
    )


def _clamp01(x: float) -> float:
    """Clamp *x* into the inclusive [0.0, 1.0] range."""
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _luminance(rgb: RGBColor) -> float:
    """Perceived relative luminance (0..1) of *rgb* — quick Rec.709 weighting."""
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0


def _rgb_distance(a: RGBColor, b: RGBColor) -> float:
    """Euclidean distance between two colors in sRGB space (0..~441)."""
    return (
        (int(a[0]) - int(b[0])) ** 2
        + (int(a[1]) - int(b[1])) ** 2
        + (int(a[2]) - int(b[2])) ** 2
    ) ** 0.5


# Linearized-RGB confusion-line matrices (Brettel/Viénot-style approximations,
# applied in plain sRGB for a fast heuristic).  Each maps an RGB triple to the
# color a person with that deficiency is estimated to perceive.
_CVD_MATRICES: dict[str, tuple[tuple[float, float, float], ...]] = {
    "protanopia": (
        (0.567, 0.433, 0.000),
        (0.558, 0.442, 0.000),
        (0.000, 0.242, 0.758),
    ),
    "deuteranopia": (
        (0.625, 0.375, 0.000),
        (0.700, 0.300, 0.000),
        (0.000, 0.300, 0.700),
    ),
    "tritanopia": (
        (0.950, 0.050, 0.000),
        (0.000, 0.433, 0.567),
        (0.000, 0.475, 0.525),
    ),
}


def _simulate_cvd(rgb: RGBColor, kind: str) -> RGBColor:
    """Return *rgb* as estimated to be perceived under deficiency *kind*."""
    m = _CVD_MATRICES[kind]
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])

    def chan(row: tuple[float, float, float]) -> int:
        v = row[0] * r + row[1] * g + row[2] * b
        return int(max(0, min(255, round(v))))

    return RGBColor(chan(m[0]), chan(m[1]), chan(m[2]))


def _did_you_mean(word: str, candidates: Iterable[str], *, cutoff: float = 0.6) -> str:
    """Return a ``" (did you mean 'x'?)"`` suffix for the closest candidate, or ``""``."""
    import difflib

    matches = difflib.get_close_matches(word, list(candidates), n=1, cutoff=cutoff)
    return f" (did you mean {matches[0]!r}?)" if matches else ""


def _section(spec: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """Return token section *name* of *spec* as a mapping (empty when absent)."""
    value = spec.get(name)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{name}: expected a mapping of token names to values; "
            f"got {type(value).__name__}"
        )
    return value


def _reject_unknown_keys(
    value: Mapping[str, Any], known: Iterable[str], path: str, what: str
) -> None:
    """Raise ``ValueError`` naming every key of *value* not in *known*."""
    known = list(known)
    unknown = [k for k in value if k not in known]
    if not unknown:
        return
    described = "; ".join(
        f"{k!r}{_did_you_mean(k, known) if isinstance(k, str) else ''}" for k in unknown
    )
    raise ValueError(
        f"{path}: unknown {what} key(s) {described}. Valid keys: {sorted(known)}"
    )


def _coerce_color(value: Any, path: str = "") -> RGBColor:
    where = f"{path}: " if path else ""
    if isinstance(value, RGBColor):
        return value
    if isinstance(value, str):
        s = value.strip().lstrip("#")
        if len(s) != 6:
            raise ValueError(
                f"{where}hex color string must be 6 hex digits, got {value!r}"
            )
        try:
            return RGBColor(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except ValueError:
            raise ValueError(
                f"{where}hex color string must be 6 hex digits, got {value!r}"
            ) from None
    # A list is what a JSON or YAML document produces for ``[r, g, b]``.
    if isinstance(value, (tuple, list)) and len(value) == 3:
        try:
            return RGBColor(int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{where}color components must be integers in 0-255, got {value!r}"
            ) from exc
    raise TypeError(
        f"{where}cannot coerce {value!r} to RGBColor; "
        "expected RGBColor, hex string, or 3-tuple"
    )


def _coerce_length(value: Any, path: str = "") -> Length:
    """Return *value* as a :class:`Length`.

    A :class:`Length` is returned unchanged.  A bare number is points,
    except that an integer of ``_EMU_INT_THRESHOLD`` or more keeps its
    historical meaning of EMU.  *path* names the token in error messages.
    """
    where = f"{path}: " if path else ""
    if isinstance(value, Length):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"{where}cannot coerce {value!r} to Length; expected a number of "
            "points or a Length such as Pt(12), Emu(152400) or Inches(0.1)"
        )
    if not math.isfinite(value) or value < 0:
        raise ValueError(
            f"{where}a length must be a finite, non-negative number of points; "
            f"got {value!r}"
        )
    if isinstance(value, int) and value >= _EMU_INT_THRESHOLD:
        # Backward compatibility: every bare integer used to be EMU.
        return Emu(value)
    return Pt(value)


def _coerce_font_size(value: Any, path: str) -> Length:
    """Return *value* as a font-size :class:`Length`, range-checked."""
    size = _coerce_length(value, path)
    if not _MIN_FONT_SIZE <= size <= _MAX_FONT_SIZE:
        raise ValueError(
            f"{path}: font size must be between 1 and 4000 points; got "
            f"{value!r}, which is {size.pt:g}pt ({int(size)} EMU). A bare number "
            "is read as points (an integer of 12700 or more as EMU); pass "
            "Pt(...) or Emu(...) to state the unit."
        )
    return size


def _coerce_flag(value: Any, path: str) -> Optional[bool]:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError(f"{path}: expected true, false or null; got {value!r}")


def _coerce_number(value: Any, path: str) -> float:
    try:
        if isinstance(value, bool):
            raise TypeError
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{path}: expected a number; got {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"{path}: expected a finite number; got {value!r}")
    return number


def _coerce_typography_field(field_name: str, value: Any, path: str) -> Any:
    """Coerce one typography field; *path* already names the field."""
    if field_name == "family":
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"{path}: typography token requires a non-empty 'family' string; "
                f"got {value!r}"
            )
        return value
    if value is None:
        return None
    if field_name == "size":
        return _coerce_font_size(value, path)
    if field_name == "color":
        return _coerce_color(value, path)
    return _coerce_flag(value, path)


def _coerce_shadow_field(field_name: str, value: Any, path: str) -> Any:
    """Coerce one shadow field; *path* already names the field."""
    if value is None:
        return None
    if field_name in ("blur_radius", "distance"):
        return _coerce_length(value, path)
    if field_name == "color":
        return _coerce_color(value, path)
    number = _coerce_number(value, path)
    if field_name == "alpha" and not 0.0 <= number <= 1.0:
        raise ValueError(f"{path}: shadow alpha must be in [0.0, 1.0]; got {value!r}")
    return number


def _typography_from_value(value: Any, path: str) -> TypographyToken:
    """Build a :class:`TypographyToken` from *value*; *path* names it in errors."""
    if isinstance(value, TypographyToken):
        return value
    if isinstance(value, str):
        return TypographyToken(family=_coerce_typography_field("family", value, path))
    if isinstance(value, Mapping):
        _reject_unknown_keys(value, _TYPOGRAPHY_FIELDS, path, "typography")
        if "family" not in value:
            raise ValueError(
                f"{path}: typography token requires a non-empty 'family' string"
            )
        return TypographyToken(
            **{
                name: _coerce_typography_field(name, value[name], f"{path}.{name}")
                for name in _TYPOGRAPHY_FIELDS
                if name in value
            }
        )
    raise TypeError(
        f"{path}: cannot build TypographyToken from {type(value).__name__}"
    )


def _shadow_from_value(value: Any, path: str) -> ShadowToken:
    """Build a :class:`ShadowToken` from *value*; *path* names it in errors."""
    if isinstance(value, ShadowToken):
        return value
    if not isinstance(value, Mapping):
        raise TypeError(
            f"{path}: cannot build ShadowToken from {type(value).__name__}"
        )
    _reject_unknown_keys(
        value, (*_SHADOW_FIELDS, *_SHADOW_ALIASES), path, "shadow"
    )
    fields: dict[str, Any] = {}
    for alias, name in _SHADOW_ALIASES.items():
        if alias in value and name in value:
            raise ValueError(
                f"{path}: {alias!r} and {name!r} are the same field; give only one"
            )
    for key, raw in value.items():
        name = _SHADOW_ALIASES.get(key, key)
        fields[name] = _coerce_shadow_field(name, raw, f"{path}.{key}")
    return ShadowToken(**fields)


# How a ``category.slot`` override value is coerced, per token category.
_SLOT_COERCERS: Mapping[str, Callable[[Any, str], Any]] = {
    "palette": _coerce_color,
    "typography": _typography_from_value,
    "radii": _coerce_length,
    "shadows": _shadow_from_value,
    "spacings": _coerce_length,
}


def _typography_with_field(
    base: TypographyToken, field_name: str, value: Any, path: str = ""
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
            f"unknown typography field {field_name!r}"
            f"{_did_you_mean(field_name, fields)}; choose from {sorted(fields)}"
        )
    fields[field_name] = _coerce_typography_field(
        field_name, value, path or f"typography.{field_name}"
    )
    return TypographyToken(**fields)


def _shadow_with_field(
    base: ShadowToken, field_name: str, value: Any, path: str = ""
) -> ShadowToken:
    """Return a copy of *base* with ``field_name`` set to *value*."""
    fields = {
        "blur_radius": base.blur_radius,
        "distance": base.distance,
        "direction": base.direction,
        "color": base.color,
        "alpha": base.alpha,
    }
    canonical = _SHADOW_ALIASES.get(field_name, field_name)
    if canonical not in fields:
        raise ValueError(
            f"unknown shadow field {field_name!r}"
            f"{_did_you_mean(field_name, (*fields, *_SHADOW_ALIASES))}; "
            f"choose from {sorted(fields)}"
        )
    fields[canonical] = _coerce_shadow_field(
        canonical, value, path or f"shadows.{field_name}"
    )
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
