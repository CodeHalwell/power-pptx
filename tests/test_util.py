"""Unit-test suite for `power_pptx.util` module."""

from __future__ import annotations

import copy
import pickle
from decimal import Decimal

import pytest

from power_pptx.util import Centipoints, Cm, Emu, Inches, Length, Mm, Pt, _coerce_emu


class DescribeLength(object):
    def it_can_construct_from_convenient_units(self, construct_fixture):
        UnitCls, units_val, emu = construct_fixture
        length = UnitCls(units_val)
        assert isinstance(length, Length)
        assert length == emu

    def it_can_self_convert_to_convenient_units(self, units_fixture):
        emu, units_prop_name, expected_length_in_units = units_fixture
        length = Length(emu)
        length_in_units = getattr(length, units_prop_name)
        assert length_in_units == expected_length_in_units

    # fixtures -------------------------------------------------------

    @pytest.fixture(
        params=[
            (Length, 914400, 914400),
            (Inches, 1.1, 1005840),
            (Centipoints, 12.5, 1587),
            (Cm, 2.53, 910799),
            (Emu, 9144.9, 9144),
            (Mm, 13.8, 496800),
            (Pt, 24.5, 311150),
        ]
    )
    def construct_fixture(self, request):
        UnitCls, units_val, emu = request.param
        return UnitCls, units_val, emu

    @pytest.fixture(
        params=[
            (914400, "inches", 1.0),
            (914400, "centipoints", 7200.0),
            (914400, "cm", 2.54),
            (914400, "emu", 914400),
            (914400, "mm", 25.4),
            (914400, "pt", 72.0),
        ]
    )
    def units_fixture(self, request):
        emu, units_prop_name, expected_length_in_units = request.param
        return emu, units_prop_name, expected_length_in_units


class DescribeLengthCopying(object):
    """Copying or pickling a length keeps its value and its class.

    Each would rebuild the length by calling its class with the stored EMU,
    which a unit class converts again: ``deepcopy(Inches(1))`` came back as
    836127360000 EMU. That broke any deep copy of a component tree or token.
    """

    @pytest.mark.parametrize(
        "length", [Inches(1), Pt(4), Cm(2), Mm(3), Centipoints(250), Emu(5), Length(7)]
    )
    @pytest.mark.parametrize(
        "duplicate",
        [copy.copy, copy.deepcopy, lambda value: pickle.loads(pickle.dumps(value))],
        ids=["copy", "deepcopy", "pickle"],
    )
    def it_keeps_the_value_and_class(self, length: Length, duplicate):
        result = duplicate(length)

        assert result == length
        assert type(result) is type(length)

    def and_it_copies_lengths_held_in_a_container(self):
        sizes = {"title": Pt(36), "gap": Inches(0.25)}

        assert copy.deepcopy(sizes) == sizes


class DescribeCoerceEmu(object):
    """Coordinate values are coerced to integer EMU at constructor entry.

    Float-valued ``<a:off>`` / ``<a:ext>`` attributes violate the OOXML
    schema's ``xs:long`` / ``xs:nonNegativeInteger`` rules and trigger
    the PowerPoint "Repair?" dialog even though python-pptx, the XSDs,
    and LibreOffice accept them silently.
    """

    def it_passes_int_through_unchanged(self):
        assert _coerce_emu(914400) == 914400

    def it_passes_None_through_unchanged(self):
        assert _coerce_emu(None) is None

    def it_passes_Length_subclasses_through_unchanged(self):
        for length in (Inches(1), Emu(123), Pt(10), Cm(2), Mm(5)):
            assert _coerce_emu(length) == int(length)

    def it_rounds_floats_half_to_even(self):
        # Python's int() truncates toward zero; round() is half-to-even.
        # Truncation accumulates one-EMU drift over arithmetic chains.
        assert _coerce_emu(914400.5) == 914400  # banker's rounding
        assert _coerce_emu(914401.5) == 914402  # banker's rounding
        assert _coerce_emu(914400.4) == 914400
        assert _coerce_emu(914400.6) == 914401

    def it_handles_negative_floats(self):
        # <a:off> may legitimately have negative coords (off-slide).
        assert _coerce_emu(-0.5) == 0  # half-to-even
        assert _coerce_emu(-1.5) == -2  # half-to-even
        assert _coerce_emu(-100.4) == -100

    def it_rejects_bool_explicitly(self):
        # bool is a Python int subclass but is always a programming
        # error as a coordinate.
        with pytest.raises(TypeError):
            _coerce_emu(True)
        with pytest.raises(TypeError):
            _coerce_emu(False)

    def it_accepts_Decimal_via_float_fallback(self):
        assert _coerce_emu(Decimal("914400.5")) == 914400

    def it_rejects_non_numeric(self):
        with pytest.raises(TypeError):
            _coerce_emu("not-a-number")
        with pytest.raises(TypeError):
            _coerce_emu(object())

    def it_rejects_numeric_strings_and_bytes(self):
        # str/bytes are convertible via float() but passing a coordinate
        # as a string is always a programming error.
        with pytest.raises(TypeError):
            _coerce_emu("914400")
        with pytest.raises(TypeError):
            _coerce_emu(b"914400")
        with pytest.raises(TypeError):
            _coerce_emu(bytearray(b"914400"))

    def it_rejects_nan_and_inf_with_TypeError(self):
        # NaN raises ValueError from int(round(...)); ±inf raises
        # OverflowError. Both are normalised to TypeError so callers
        # see a single, informative exception type.
        with pytest.raises(TypeError):
            _coerce_emu(float("nan"))
        with pytest.raises(TypeError):
            _coerce_emu(float("inf"))
        with pytest.raises(TypeError):
            _coerce_emu(float("-inf"))

    def it_handles_the_field_repro_arithmetic(self):
        # The exact failure mode from the field bug report:
        # ``card_w = (Inches(N) - gutter) / 2`` produces a float.
        card_w = (Inches(12.33) - Inches(0.25)) / 2
        assert isinstance(card_w, float)
        assert isinstance(_coerce_emu(card_w), int)
