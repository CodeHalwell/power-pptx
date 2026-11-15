"""Opening a malformed or hostile package fails clearly, or not at all where it need not.

A .pptx arrives from outside: an upload, a mail attachment, another tool's
export.  Whatever is wrong with it should produce one recognisable error
type rather than whichever exception the first failing line happened to
raise, and nothing in it should be able to exhaust the stack or memory.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys
import warnings
import zipfile
from typing import Callable

import pytest

from power_pptx import Presentation
from power_pptx.exc import InvalidPackageError, PackageNotFoundError

Edit = Callable[[str, bytes], "tuple[str, bytes] | None"]

_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _deck(n_slides: int = 1) -> bytes:
    prs = Presentation()
    for i in range(n_slides):
        prs.slides.add_slide(prs.slide_layouts[5]).shapes.title.text = "slide %d" % i
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _rewrite(
    deck: bytes,
    edit: Edit | None = None,
    drop: tuple[str, ...] = (),
    add: tuple[tuple[str, bytes], ...] = (),
) -> bytes:
    """Return `deck` with members edited, dropped and/or added."""
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(deck)) as zin,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for name in zin.namelist():
            if name in drop:
                continue
            data = zin.read(name)
            if edit is not None:
                edited = edit(name, data)
                if edited is None:
                    continue
                name, data = edited
            zout.writestr(name, data)
        for name, data in add:
            zout.writestr(name, data)
    return out.getvalue()


def _with_dtd(member: str) -> Edit:
    def edit(name: str, data: bytes):
        if name == member:
            head, rest = data.split(b"?>", 1)
            data = head + b'?><!DOCTYPE x [<!ENTITY e "boom">]>' + rest
        return name, data

    return edit


def _without_content_type_for_slide1(name: str, data: bytes):
    if name == "[Content_Types].xml":
        override = (
            b'<Override PartName="/ppt/slides/slide1.xml" ContentType="application/'
            b'vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )
        default = b'<Default Extension="xml" ContentType="application/xml"/>'
        assert override in data
        assert default in data
        data = data.replace(override, b"").replace(default, b"")
    return name, data


# -- each entry: (id, package bytes, text the error message must contain) --
def _faulty_packages() -> list[tuple[str, bytes, str]]:
    deck = _deck()
    return [
        ("not-a-zip", b"hello world, this is not a zip archive", "not a zip archive"),
        ("empty-file", b"", "not a zip archive"),
        ("empty-zip", _rewrite(deck, edit=lambda n, d: None), "no '[Content_Types].xml'"),
        (
            "no-content-types",
            _rewrite(deck, drop=("[Content_Types].xml",)),
            "no '[Content_Types].xml'",
        ),
        ("no-package-rels", _rewrite(deck, drop=("_rels/.rels",)), "no '_rels/.rels'"),
        (
            "no-main-part",
            _rewrite(deck, drop=("ppt/presentation.xml",)),
            "no main document part",
        ),
        (
            "part-without-content-type",
            _rewrite(deck, edit=_without_content_type_for_slide1),
            "'ppt/slides/slide1.xml' has no content type",
        ),
        (
            "dtd-in-a-slide",
            _rewrite(deck, edit=_with_dtd("ppt/slides/slide1.xml")),
            "'ppt/slides/slide1.xml' contains a DTD",
        ),
        (
            "dtd-in-a-rels-item",
            _rewrite(deck, edit=_with_dtd("ppt/_rels/presentation.xml.rels")),
            "'ppt/_rels/presentation.xml.rels' contains a DTD",
        ),
        (
            "dtd-in-content-types",
            _rewrite(deck, edit=_with_dtd("[Content_Types].xml")),
            "'[Content_Types].xml' contains a DTD",
        ),
    ]


_FAULTY = _faulty_packages()


def _as_str_path(data: bytes, tmp_path: pathlib.Path):
    path = tmp_path / "deck.pptx"
    path.write_bytes(data)
    return str(path)


def _as_path_object(data: bytes, tmp_path: pathlib.Path):
    path = tmp_path / "deck.pptx"
    path.write_bytes(data)
    return path


def _as_stream(data: bytes, tmp_path: pathlib.Path):
    return io.BytesIO(data)


_FORMS = [
    pytest.param(_as_str_path, id="str-path"),
    pytest.param(_as_path_object, id="path-object"),
    pytest.param(_as_stream, id="stream"),
]


class DescribeOpeningAMalformedPackage:
    @pytest.mark.parametrize("form", _FORMS)
    @pytest.mark.parametrize(
        ("package", "message"),
        [pytest.param(data, message, id=id_) for id_, data, message in _FAULTY],
    )
    def it_raises_InvalidPackageError_however_the_package_is_given(
        self, tmp_path, form, package, message
    ):
        with pytest.raises(InvalidPackageError) as e:
            Presentation(form(package, tmp_path))

        assert message in str(e.value)
        # -- the message reads as written, not as the repr() KeyError would show --
        assert not str(e.value).startswith(("'", '"'))

    @pytest.mark.parametrize(
        "caught_as", [PackageNotFoundError, zipfile.BadZipFile, KeyError, InvalidPackageError]
    )
    @pytest.mark.parametrize("form", _FORMS)
    def it_is_still_caught_by_the_handlers_these_faults_used_to_need(
        self, tmp_path, form, caught_as
    ):
        for _, package, _ in _FAULTY:
            with pytest.raises(caught_as):
                Presentation(form(package, tmp_path))

    def it_says_so_when_the_file_looks_like_a_legacy_or_encrypted_presentation(self, tmp_path):
        ole_compound_file = bytes.fromhex("d0cf11e0a1b11ae1") + b"\0" * 504

        for form in (_as_str_path, _as_path_object, _as_stream):
            with pytest.raises(InvalidPackageError) as e:
                Presentation(form(ole_compound_file, tmp_path))
            assert "legacy .ppt file or a password-protected presentation" in str(e.value)

    def it_reports_a_member_that_cannot_be_decompressed(self):
        deck = _deck()
        stored = io.BytesIO()
        with (
            zipfile.ZipFile(io.BytesIO(deck)) as zin,
            zipfile.ZipFile(stored, "w", zipfile.ZIP_STORED) as zout,
        ):
            for name in zin.namelist():
                zout.writestr(name, zin.read(name))
        damaged = stored.getvalue().replace(b"<p:presentation ", b"<p:presentatiom ", 1)
        assert damaged != stored.getvalue()

        with pytest.raises(InvalidPackageError) as e:
            Presentation(io.BytesIO(damaged))

        assert "cannot read 'ppt/presentation.xml' from package" in str(e.value)

    def but_a_missing_file_is_not_found_rather_than_invalid(self, tmp_path):
        missing = tmp_path / "nope.pptx"

        for path in (str(missing), missing):
            with pytest.raises(PackageNotFoundError) as e:
                Presentation(path)
            assert not isinstance(e.value, InvalidPackageError)
            assert str(e.value) == "Package not found at '%s'" % missing
            # -- a path object used to raise FileNotFoundError here; it still is one --
            assert isinstance(e.value, FileNotFoundError)

    def and_a_package_that_is_not_a_presentation_is_a_ValueError_as_before(self):
        content_types = "application/vnd.openxmlformats-officedocument.presentationml"

        def as_docx(name: str, data: bytes):
            if name == "[Content_Types].xml":
                data = data.replace(
                    (content_types + ".presentation.main+xml").encode(),
                    b"application/vnd.openxmlformats-officedocument.wordprocessingml"
                    b".document.main+xml",
                )
            return name, data

        with pytest.raises(ValueError, match="is not a PowerPoint file"):
            Presentation(io.BytesIO(_rewrite(_deck(), edit=as_docx)))


class DescribeOpeningAnOddButReadablePackage:
    def it_opens_a_valid_deck_given_as_a_path_object(self, tmp_path):
        path = tmp_path / "ok.pptx"
        path.write_bytes(_deck(2))

        assert len(Presentation(path).slides) == 2

    def it_follows_a_chain_of_parts_deeper_than_the_recursion_limit(self):
        depth = sys.getrecursionlimit() + 200
        extra = []
        for i in range(depth):
            link = (
                '<Relationship Id="rId1" Type="http://x/y" Target="c%d.xml"/>' % (i + 1)
                if i + 1 < depth
                else ""
            )
            extra.append(("ppt/chain/c%d.xml" % i, b"<a/>"))
            extra.append(
                (
                    "ppt/chain/_rels/c%d.xml.rels" % i,
                    ('<Relationships xmlns="%s">%s</Relationships>' % (_REL_NS, link)).encode(),
                )
            )

        def link_chain(name: str, data: bytes):
            if name == "ppt/_rels/presentation.xml.rels":
                data = data.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rId999" Type="http://x/y" Target="chain/c0.xml"/>'
                    b"</Relationships>",
                )
            return name, data

        prs = Presentation(io.BytesIO(_rewrite(_deck(), edit=link_chain, add=tuple(extra))))

        chain = [p for p in prs.part.package.iter_parts() if p.partname.startswith("/ppt/chain/")]
        assert len(chain) == depth
        assert len(prs.slides) == 1
        saved = io.BytesIO()
        prs.save(saved)
        with zipfile.ZipFile(saved) as z:
            assert "ppt/chain/c%d.xml" % (depth - 1) in z.namelist()
        reopened = Presentation(io.BytesIO(saved.getvalue()))
        assert (
            sum(p.partname.startswith("/ppt/chain/") for p in reopened.part.package.iter_parts())
            == depth
        )

    @pytest.mark.parametrize("target_mode", ["external", "EXTERNAL", "External"])
    def it_reads_TargetMode_without_regard_to_case(self, target_mode):
        def add_link(name: str, data: bytes):
            if name == "ppt/slides/_rels/slide1.xml.rels":
                data = data.replace(
                    b"</Relationships>",
                    (
                        '<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/'
                        'officeDocument/2006/relationships/hyperlink" '
                        'Target="https://example.com/a b" TargetMode="%s"/></Relationships>'
                        % target_mode
                    ).encode(),
                )
            return name, data

        prs = Presentation(io.BytesIO(_rewrite(_deck(), edit=add_link)))

        rel = prs.slides[0].part.rels["rId99"]
        assert rel.is_external
        assert rel.target_ref == "https://example.com/a b"
        saved = io.BytesIO()
        prs.save(saved)
        with zipfile.ZipFile(saved) as z:
            rels_xml = z.read("ppt/slides/_rels/slide1.xml.rels").decode()
        assert 'Target="https://example.com/a b" TargetMode="External"' in rels_xml
        assert Presentation(io.BytesIO(saved.getvalue())).slides[0].part.rels["rId99"].is_external

    def it_does_not_inflate_a_member_that_nothing_refers_to(self, monkeypatch):
        # A "zip bomb": megabytes of zeros that deflate to almost nothing,
        # under a name no relationship points at.
        junk = ("ppt/media/junk.bin", b"\0" * (4 * 1024 * 1024))
        bomb = _rewrite(_deck(), add=(junk,))
        assert len(bomb) < 200 * 1024
        read_names: list[str] = []
        real_read = zipfile.ZipFile.read

        def recording_read(self, name, pwd=None):
            read_names.append(name if isinstance(name, str) else name.filename)
            return real_read(self, name, pwd)

        monkeypatch.setattr(zipfile.ZipFile, "read", recording_read)

        prs = Presentation(io.BytesIO(bomb))

        assert "ppt/presentation.xml" in read_names
        assert "ppt/slides/slide1.xml" in read_names
        assert "ppt/media/junk.bin" not in read_names
        assert len(read_names) == len(set(read_names))
        # -- and, as before, a part nothing refers to is not carried into a save --
        saved = io.BytesIO()
        prs.save(saved)
        with zipfile.ZipFile(saved) as z:
            assert "ppt/media/junk.bin" not in z.namelist()

    def it_ignores_members_with_path_like_names_it_never_extracts(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            odd = _rewrite(_deck(), add=(("../evil.txt", b"x"), ("/abs.txt", b"y")))

        prs = Presentation(io.BytesIO(odd))
        saved = io.BytesIO()
        prs.save(saved)

        with zipfile.ZipFile(saved) as z:
            assert not [n for n in z.namelist() if "evil" in n or "abs" in n]

    @pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="needs /proc to list open files")
    def it_does_not_keep_the_package_file_open_after_loading(self, tmp_path):
        def open_paths() -> list[str]:
            paths = []
            for fd in os.listdir("/proc/self/fd"):
                # -- the descriptor used for the listing itself is gone by now --
                with contextlib.suppress(OSError):
                    paths.append(os.readlink("/proc/self/fd/%s" % fd))
            return paths

        path = tmp_path / "deck.pptx"
        path.write_bytes(_deck())
        broken = tmp_path / "broken.pptx"
        broken.write_bytes(_rewrite(_deck(), drop=("[Content_Types].xml",)))

        prs = Presentation(str(path))
        with pytest.raises(InvalidPackageError):
            Presentation(str(broken))

        assert len(prs.slides) == 1
        assert str(path) not in open_paths()
        assert str(broken) not in open_paths()

    def but_it_leaves_a_stream_the_caller_passed_open(self):
        stream = io.BytesIO(_deck())

        prs = Presentation(stream)

        assert len(prs.slides) == 1
        assert not stream.closed
