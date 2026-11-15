"""`Presentation.save()` to a path is all-or-nothing.

The package used to be written straight onto the destination, so a failure
half-way through serialisation left a truncated zip where a good deck had
been.  It is now written beside the destination and moved into place only
when complete.
"""

from __future__ import annotations

import io
import os
import zipfile

import pytest

from power_pptx import Presentation
from power_pptx.parts.slide import SlidePart


class _SerialisationFailure(Exception):
    pass


def _deck(n_slides: int = 3) -> Presentation:
    prs = Presentation()
    for i in range(n_slides):
        prs.slides.add_slide(prs.slide_layouts[5]).shapes.title.text = "slide %d" % i
    return prs


def _fail_when_serialising(monkeypatch: pytest.MonkeyPatch, victim: SlidePart) -> None:
    """Make writing out `victim` raise, as a bug or an out-of-memory would mid-save."""
    real_blob = SlidePart.blob

    def blob(self):
        if self is victim:
            raise _SerialisationFailure("simulated failure while serialising a slide")
        return real_blob.fget(self)

    monkeypatch.setattr(SlidePart, "blob", property(blob))


class DescribeSavingToAPath:
    def it_leaves_the_previous_file_intact_when_a_save_fails_midway(self, tmp_path, monkeypatch):
        path = tmp_path / "deck.pptx"
        _deck().save(str(path))
        good = path.read_bytes()
        prs = Presentation(str(path))
        prs.slides[0].shapes.title.text = "edited"
        _fail_when_serialising(monkeypatch, prs.slides[2].part)

        with pytest.raises(_SerialisationFailure):
            prs.save(str(path))

        assert path.read_bytes() == good
        assert os.listdir(tmp_path) == ["deck.pptx"]
        reopened = Presentation(str(path))
        assert [s.shapes.title.text for s in reopened.slides] == ["slide 0", "slide 1", "slide 2"]

    def it_creates_no_file_when_a_first_save_fails(self, tmp_path, monkeypatch):
        path = tmp_path / "deck.pptx"
        prs = _deck()
        _fail_when_serialising(monkeypatch, prs.slides[1].part)

        with pytest.raises(_SerialisationFailure):
            prs.save(path)

        assert os.listdir(tmp_path) == []

    def it_can_be_retried_after_a_failed_save(self, tmp_path, monkeypatch):
        path = tmp_path / "deck.pptx"
        prs = _deck()
        with monkeypatch.context() as patch:
            _fail_when_serialising(patch, prs.slides[1].part)
            with pytest.raises(_SerialisationFailure):
                prs.save(str(path))

        prs.save(str(path))

        assert os.listdir(tmp_path) == ["deck.pptx"]
        assert len(Presentation(str(path)).slides) == 3

    def it_replaces_the_file_it_was_opened_from(self, tmp_path):
        path = tmp_path / "deck.pptx"
        _deck().save(str(path))
        prs = Presentation(str(path))
        prs.slides[0].shapes.title.text = "edited"

        prs.save(str(path))

        assert os.listdir(tmp_path) == ["deck.pptx"]
        assert Presentation(str(path)).slides[0].shapes.title.text == "edited"

    def it_writes_the_same_package_to_a_path_as_to_a_stream(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        prs = _deck()
        path = tmp_path / "deck.pptx"
        stream = io.BytesIO()

        prs.save(str(path))
        prs.save(stream)

        assert path.read_bytes() == stream.getvalue()

    def it_still_reports_a_destination_that_cannot_be_written(self, tmp_path):
        prs = _deck(1)

        with pytest.raises(FileNotFoundError):
            prs.save(str(tmp_path / "no-such-directory" / "deck.pptx"))
        with pytest.raises(OSError):
            prs.save(str(tmp_path))  # -- a directory --

        assert os.listdir(tmp_path) == []


class DescribeSavingToAStream:
    def it_writes_straight_to_the_stream(self):
        stream = io.BytesIO()

        _deck().save(stream)

        assert zipfile.is_zipfile(stream)
        assert not stream.closed
