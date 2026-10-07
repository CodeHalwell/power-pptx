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
    def from_value(cls, value: Any, _path: str = "typography") -> "TypographyToken":
        """Coerce a dict / string / existing token into a :class:`TypographyToken`.

        A bare string is interpreted as a font family with no other
        attributes set; a mapping is unpacked through :meth:`__init__`.

        ``size`` follows the token unit rule — a ``float`` is points, a
        :class:`~power_pptx.util.Length` (``Pt(...)``) is taken as is, a
        bare ``int`` is EMU — and must land between 1 pt and 4000 pt.
        A bare ``36`` is therefore rejected (it is 36 EMU) rather than
        stored and failing later inside a recipe.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(family=value)
        if isinstance(value, Mapping):
            family = value.get("family")
            if not isinstance(family, str) or not family:
                raise ValueError("typography token requires a non-empty 'family' string")
            size = value.get("size")
            if size is not None:
                size = _coerce_font_size(size, f"{_path}.size")
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
        raise TypeError(f"cannot build TypographyToken from {type(value).__name__}")


@dataclass(frozen=True)
class ShadowToken:
    """A shadow token, mirroring :class:`power_pptx.dml.effect.ShadowFormat`."""

    blur_radius: Optional[Length] = None
    distance: Optional[Length] = None
    direction: Optional[float] = None
    color: Optional[RGBColor] = None
    alpha: Optional[float] = None

    @classmethod
    def from_value(cls, value: Any, _path: str = "shadow") -> "ShadowToken":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError(f"cannot build ShadowToken from {type(value).__name__}")
        blur = value.get("blur_radius")
        if blur is not None:
            blur = _coerce_extent(blur, f"{_path}.blur_radius")
        distance = value.get("distance")
        if distance is not None:
            distance = _coerce_extent(distance, f"{_path}.distance")
        direction = value.get("direction")
        if direction is not None:
            direction = float(direction)
        alpha = value.get("alpha")
        if alpha is not None:
            alpha = _coerce_alpha(alpha, f"{_path}.alpha")
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
        tokens.  Each of ``palette`` / ``typography`` / ``radii`` /
        ``spacings`` / ``shadows`` must be a mapping (``None`` means
        empty).

        Colours may be an :class:`RGBColor`, a hex string, or a 3-item
        list or tuple of ints (JSON and YAML have no tuples).  Lengths
        follow one unit rule: a ``float`` is **points**, a
        :class:`~power_pptx.util.Length` (``Pt(8)``) is taken as is, and a
        bare ``int`` is **EMU**.  So that ``{"size": 36}`` does not silently
        become 36 EMU, a font size outside 1-4000 pt and a radius, spacing
        or shadow extent given as a bare int of 1-99 EMU raise
        :class:`ValueError` naming the token (``tokens.typography.heading.size``).
        """
        if not isinstance(spec, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError(f"tokens must be a mapping; got {type(spec).__name__!r}")
        palette = {name: _coerce_color(value) for name, value in _section(spec, "palette").items()}
        typography = {
            name: TypographyToken.from_value(value, _path=f"tokens.typography.{name}")
            for name, value in _section(spec, "typography").items()
        }
        radii = {
            name: _coerce_extent(value, f"tokens.radii.{name}")
            for name, value in _section(spec, "radii").items()
        }
        spacings = {
            name: _coerce_extent(value, f"tokens.spacings.{name}")
            for name, value in _section(spec, "spacings").items()
        }
        shadows = {
            name: ShadowToken.from_value(value, _path=f"tokens.shadows.{name}")
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
        spec = (
            _PRESETS.get(name)
            if isinstance(name, str)  # pyright: ignore[reportUnnecessaryIsInstance]
            else None
        )
        if spec is None:
            raise ValueError(f"Unknown preset {name!r}; choose from {sorted(_PRESETS)}")
        return cls.from_dict(spec)

    @classmethod
    def from_seed(cls, seed: ColorSpec, harmony: str = "complementary") -> "DesignTokens":
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
            raise ValueError(f"unknown harmony {harmony!r}; choose from {list(valid)}")

        seed_rgb = _coerce_color(seed)
        h, light, s = colorsys.rgb_to_hls(
            seed_rgb[0] / 255.0, seed_rgb[1] / 255.0, seed_rgb[2] / 255.0
        )

        def from_hsl(hue: float, lightness: float, sat: float) -> RGBColor:
            r, g, b = colorsys.hls_to_rgb(hue % 1.0, _clamp01(lightness), _clamp01(sat))
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
            RGBColor(0xFF, 0xFF, 0xFF) if _luminance(primary) < 0.5 else RGBColor(0x10, 0x10, 0x10)
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
            raise ValueError(f"unknown kind {kind!r}; choose from {list(valid)}")

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
                sim = _rgb_distance(_simulate_cvd(ra, kind), _simulate_cvd(rb, kind))
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
    def from_yaml(cls, path: str) -> "DesignTokens":
        """Load a token set from a YAML brand file.

        Requires ``pyyaml``; raises :class:`ImportError` with a clear
        installation hint when the dependency is missing.
        """
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "DesignTokens.from_yaml requires pyyaml; install with `pip install pyyaml`"
            ) from exc
        with open(path, encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        if not isinstance(spec, Mapping):
            raise ValueError(f"YAML at {path!r} did not parse to a mapping")
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

        prs = Presentation(path_or_prs) if isinstance(path_or_prs, str) else path_or_prs

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

    def with_overrides(self, overrides: Mapping[str, Any]) -> "DesignTokens":
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
        next segment is the slot name, and a third segment navigates
        into a typography or shadow token (e.g.
        ``typography.heading.size`` updates only the ``size`` field of
        the existing heading token).  Deeper keys are rejected.

        Values are validated exactly as :meth:`from_dict` validates them
        (the unit rule for lengths, the ``[0, 1]`` range for shadow
        ``alpha``), and a rejected value raises :class:`ValueError`
        naming the token path — ``self`` is never modified.

        Useful for per-call recipe overrides::

            kpi_slide(prs, ..., tokens=tokens.with_overrides({
                "palette.primary": "#FF6600",
            }))

        without forking the base token set.
        """
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
                    f"unknown override category {category!r}; choose from {sorted(bins)}"
                )
            if len(parts) > 3:
                raise ValueError(
                    f"override key {key!r} has too many segments; the deepest form is "
                    "'typography.<slot>.<field>' / 'shadows.<slot>.<field>'"
                )
            slot_path = f"tokens.{category}.{parts[1]}"
            if len(parts) == 2:
                slot = parts[1]
                if category == "palette":
                    target[slot] = _coerce_color(value)
                elif category in ("radii", "spacings"):
                    target[slot] = _coerce_extent(value, slot_path)
                elif category == "typography":
                    target[slot] = TypographyToken.from_value(value, _path=slot_path)
                elif category == "shadows":
                    target[slot] = ShadowToken.from_value(value, _path=slot_path)
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
                    target[slot] = _typography_with_field(base, field_name, value, slot_path)
                elif category == "shadows":
                    base = existing if isinstance(existing, ShadowToken) else ShadowToken()
                    target[slot] = _shadow_with_field(base, field_name, value, slot_path)
                else:
                    raise ValueError(
                        f"sub-field override {key!r} only supported on typography and shadows"
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


def _flatten_overrides(overrides: Mapping[str, Any], _prefix: str = "") -> dict[str, Any]:
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
        full = f"{_prefix}.{key}" if _prefix else key
        # Mappings whose values are themselves token instances
        # (TypographyToken, ShadowToken) shouldn't be walked.
        if (
            isinstance(value, Mapping)
            and not isinstance(value, RGBColor)
            and not _is_token_value(value)
        ):
            flat.update(_flatten_overrides(value, full))
            continue
        flat[full] = value
    return flat


def _is_token_value(value: Any) -> bool:
    """True if *value* is a typography/shadow/length token shouldn't be flattened."""
    return isinstance(value, (TypographyToken, ShadowToken, Length, RGBColor))


def _clamp01(x: float) -> float:
    """Clamp *x* into the inclusive [0.0, 1.0] range."""
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _luminance(rgb: RGBColor) -> float:
    """Perceived relative luminance (0..1) of *rgb* — quick Rec.709 weighting."""
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0


def _rgb_distance(a: RGBColor, b: RGBColor) -> float:
    """Euclidean distance between two colors in sRGB space (0..~441)."""
    return (
        (int(a[0]) - int(b[0])) ** 2 + (int(a[1]) - int(b[1])) ** 2 + (int(a[2]) - int(b[2])) ** 2
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


def _coerce_color(value: Any) -> RGBColor:
    if isinstance(value, RGBColor):
        return value
    if isinstance(value, str):
        s = value.lstrip("#")
        if len(s) != 6:
            raise ValueError(f"hex color string must be 6 hex digits, got {value!r}")
        return RGBColor(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    # JSON and YAML have no tuples, so a decoded ``[r, g, b]`` arrives as a list.
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return RGBColor(int(value[0]), int(value[1]), int(value[2]))
    raise TypeError(
        f"cannot coerce {value!r} to RGBColor; "
        "expected RGBColor, hex string, or a 3-item list/tuple of ints"
    )


def _coerce_length(value: Any) -> Length:
    """Turn *value* into a :class:`Length`: a ``float`` is points, an ``int`` is EMU.

    A :class:`Length` (``Pt(8)``, ``Emu(100)``) passes through untouched.  The
    bare-int-is-EMU rule is kept for backwards compatibility; use
    :func:`_coerce_font_size` / :func:`_coerce_extent` where a unit slip
    (``36`` for ``36.0``) should be caught rather than stored.
    """
    if isinstance(value, Length):
        return value
    # ``bool`` is an ``int`` subclass; ``True`` is not a one-EMU length.
    if isinstance(value, int) and not isinstance(value, bool):
        return Emu(value)
    if isinstance(value, float):
        # Treat bare floats as points — the most common authoring unit.
        return Pt(value)
    raise TypeError(
        f"cannot coerce {value!r} to Length; expected Length, int (EMU), or float (points)"
    )


# The OOXML ``sz`` attribute stores hundredths of a point and only allows 100..400000.
_MIN_FONT_SIZE = Pt(1)
_MAX_FONT_SIZE = Pt(4000)

# A bare int below this many EMU (0 excepted) is taken for a unit slip: ``8`` meant
# as 8 pt is 8 EMU, a corner radius of 0.0006 pt.
_MIN_BARE_EMU = 100

_UNIT_HINT = "use a float for points, or Pt(...)"


def _is_bare_int(value: Any) -> bool:
    """True for a plain ``int`` — neither a :class:`Length` nor a ``bool``."""
    return isinstance(value, int) and not isinstance(value, (Length, bool))


def _describe_length(length: Length) -> str:
    return f"{int(length)} EMU ({length.pt:.3g} pt)"


def _coerce_length_at(value: Any, path: str) -> Length:
    """:func:`_coerce_length`, with *path* prefixed to the :class:`TypeError` it raises."""
    try:
        return _coerce_length(value)
    except TypeError as exc:
        raise TypeError(f"{path}: {exc}") from None


def _coerce_font_size(value: Any, path: str) -> Length:
    """Coerce a typography size, requiring 1 pt <= size <= 4000 pt.

    The unit rule is :func:`_coerce_length`'s, so ``36`` is 36 EMU — which is
    why it is rejected here, naming *path*, instead of surfacing later as
    "value must be in range 100 to 400000" from deep inside a recipe.
    """
    size = _coerce_length_at(value, path)
    if not _MIN_FONT_SIZE <= size <= _MAX_FONT_SIZE:
        hint = f"a bare int is read as EMU, so {_UNIT_HINT}" if _is_bare_int(value) else _UNIT_HINT
        raise ValueError(
            f"{path}: font size {_describe_length(size)} is outside the 1-4000 pt range; {hint}"
        )
    return size


def _coerce_extent(value: Any, path: str) -> Length:
    """Coerce a radius, spacing or shadow extent, rejecting a bare int that is a unit slip.

    A bare ``int`` of 1-99 EMU (``{"radii": {"md": 8}}``) is stored as a
    sub-hundredth-of-a-point length that renders as nothing; it raises, naming
    *path*.  ``0`` has no unit to get wrong and is accepted, as is any
    :class:`Length` or ``float``.
    """
    length = _coerce_length_at(value, path)
    if _is_bare_int(value) and value != 0 and abs(value) < _MIN_BARE_EMU:
        raise ValueError(
            f"{path}: a bare int is read as EMU, and {_describe_length(length)} is almost "
            f"certainly not what you meant; {_UNIT_HINT}"
        )
    return length


def _coerce_alpha(value: Any, path: str) -> float:
    try:
        alpha: Optional[float] = float(value)
    except (TypeError, ValueError):
        alpha = None
    if alpha is None or not 0.0 <= alpha <= 1.0:
        raise ValueError(f"{path}: shadow alpha must be a number in [0.0, 1.0]; got {value!r}")
    return alpha


def _section(spec: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """Return the *name* category of a token spec: a mapping, empty when absent or ``None``."""
    value = spec.get(name)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(
            f"tokens.{name} must be a mapping of slot name -> value; "
            f"got {type(value).__name__!r}: {value!r}"
        )
    return value


def _typography_with_field(
    base: TypographyToken, field_name: str, value: Any, path: str = "typography"
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
        raise ValueError(f"unknown typography field {field_name!r}; choose from {sorted(fields)}")
    if field_name == "size" and value is not None:
        value = _coerce_font_size(value, f"{path}.size")
    elif field_name == "color" and value is not None:
        value = _coerce_color(value)
    fields[field_name] = value
    return TypographyToken(**fields)


def _shadow_with_field(
    base: ShadowToken, field_name: str, value: Any, path: str = "shadow"
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
        raise ValueError(f"unknown shadow field {field_name!r}; choose from {sorted(fields)}")
    if field_name in ("blur_radius", "distance") and value is not None:
        value = _coerce_extent(value, f"{path}.{field_name}")
    elif field_name == "color" and value is not None:
        value = _coerce_color(value)
    elif field_name == "alpha" and value is not None:
        value = _coerce_alpha(value, f"{path}.alpha")
    elif field_name == "direction" and value is not None:
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
            "primary": "#3B5BDB",
            "neutral": "#1F2933",
            "muted": "#7B8794",
            "surface": "#F5F7FA",
            "on_primary": "#FFFFFF",
            "lt1": "#FFFFFF",
            "lt2": "#E4E7EB",
            "positive": "#0CA678",
            "negative": "#E03131",
            "success": "#0CA678",
            "danger": "#E03131",
        },
        "typography": {
            "heading": {"family": "Inter", "size": Pt(32), "bold": True},
            "body": {"family": "Inter", "size": Pt(16)},
        },
        "radii": {"sm": Pt(4), "md": Pt(8), "lg": Pt(16)},
        "spacings": {"xs": Pt(4), "sm": Pt(8), "md": Pt(16), "lg": Pt(32)},
        "shadows": {
            "card": {
                "blur_radius": Pt(8),
                "distance": Pt(2),
                "direction": 90.0,
                "color": "#000000",
                "alpha": 0.18,
            },
        },
    },
    "modern_dark": {
        "palette": {
            "primary": "#7C5CFF",
            "neutral": "#E4E7EB",
            "muted": "#7B8794",
            "surface": "#1F2933",
            "on_primary": "#0B0F19",
            "lt1": "#323F4B",
            "lt2": "#3E4C59",
            "positive": "#3DD68C",
            "negative": "#FF6B6B",
            "success": "#3DD68C",
            "danger": "#FF6B6B",
        },
        "typography": {
            "heading": {"family": "Inter", "size": Pt(32), "bold": True},
            "body": {"family": "Inter", "size": Pt(16)},
        },
        "radii": {"sm": Pt(4), "md": Pt(8), "lg": Pt(16)},
        "spacings": {"xs": Pt(4), "sm": Pt(8), "md": Pt(16), "lg": Pt(32)},
        "shadows": {
            "card": {
                "blur_radius": Pt(12),
                "distance": Pt(3),
                "direction": 90.0,
                "color": "#000000",
                "alpha": 0.45,
            },
        },
    },
    "corporate_navy": {
        "palette": {
            "primary": "#0B2545",
            "neutral": "#13315C",
            "muted": "#8DA9C4",
            "surface": "#EEF4ED",
            "on_primary": "#FFFFFF",
            "lt1": "#FFFFFF",
            "lt2": "#D6DDE0",
            "positive": "#247B7B",
            "negative": "#A23B3B",
            "success": "#247B7B",
            "danger": "#A23B3B",
        },
        "typography": {
            "heading": {"family": "Source Serif Pro", "size": Pt(34), "bold": True},
            "body": {"family": "Source Sans Pro", "size": Pt(16)},
        },
        "radii": {"sm": Pt(2), "md": Pt(4), "lg": Pt(8)},
        "spacings": {"xs": Pt(4), "sm": Pt(8), "md": Pt(16), "lg": Pt(32)},
        "shadows": {
            "card": {
                "blur_radius": Pt(6),
                "distance": Pt(1),
                "direction": 90.0,
                "color": "#000000",
                "alpha": 0.12,
            },
        },
    },
    "vibrant": {
        "palette": {
            "primary": "#FF3366",
            "neutral": "#22223B",
            "muted": "#9A8C98",
            "surface": "#FFF8F0",
            "on_primary": "#FFFFFF",
            "lt1": "#FFFFFF",
            "lt2": "#FFE5D9",
            "positive": "#06D6A0",
            "negative": "#EF233C",
            "success": "#06D6A0",
            "danger": "#EF233C",
        },
        "typography": {
            "heading": {"family": "Poppins", "size": Pt(36), "bold": True},
            "body": {"family": "Poppins", "size": Pt(16)},
        },
        "radii": {"sm": Pt(6), "md": Pt(12), "lg": Pt(24)},
        "spacings": {"xs": Pt(4), "sm": Pt(8), "md": Pt(16), "lg": Pt(32)},
        "shadows": {
            "card": {
                "blur_radius": Pt(14),
                "distance": Pt(4),
                "direction": 90.0,
                "color": "#000000",
                "alpha": 0.20,
            },
        },
    },
}
