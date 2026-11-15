"""API for reading/writing serialized Open Packaging Convention (OPC) package."""

from __future__ import annotations

import contextlib
import os
import posixpath
import secrets
import stat
import zipfile
import zlib
from typing import IO, TYPE_CHECKING, Any, Container, Sequence

from power_pptx._reproducible import zip_date_time
from power_pptx.exc import InvalidPackageError, PackageNotFoundError
from power_pptx.opc.constants import CONTENT_TYPE as CT
from power_pptx.opc.oxml import CT_Types, serialize_part_xml
from power_pptx.opc.packuri import CONTENT_TYPES_URI, PACKAGE_URI, PackURI
from power_pptx.opc.shared import CaseInsensitiveDict
from power_pptx.opc.spec import default_content_types
from power_pptx.util import lazyproperty

if TYPE_CHECKING:
    from power_pptx.opc.package import Part, _Relationships  # pyright: ignore[reportPrivateUsage]


class PackageReader(Container[bytes]):
    """Provides access to package-parts of an OPC package with dict semantics.

    The package may be in zip-format (a .pptx file) or expanded into a directory structure,
    perhaps by unzipping a .pptx file.
    """

    def __init__(self, pkg_file: str | os.PathLike[str] | IO[bytes]):
        self._pkg_file = pkg_file

    def __contains__(self, pack_uri: object) -> bool:
        """Return True when part identified by `pack_uri` is present in package."""
        return pack_uri in self._blob_reader

    def __getitem__(self, pack_uri: PackURI) -> bytes:
        """Return bytes for part corresponding to `pack_uri`."""
        return self._blob_reader[pack_uri]

    def close(self) -> None:
        """Release the package file, if this reader has opened it.

        Package items are read on demand, so the underlying file stays open between reads.
        Call this once everything needed has been read. A stream passed in by the caller is
        left open; it is theirs.
        """
        blob_reader = self.__dict__.get("_blob_reader")
        if blob_reader is not None:
            blob_reader.close()

    def rels_xml_for(self, partname: PackURI) -> bytes | None:
        """Return optional rels item XML for `partname`.

        Returns `None` if no rels item is present for `partname`. `partname` is a |PackURI|
        instance.
        """
        blob_reader, uri = self._blob_reader, partname.rels_uri
        return blob_reader[uri] if uri in blob_reader else None

    @lazyproperty
    def _blob_reader(self) -> _PhysPkgReader:
        """|_PhysPkgReader| subtype providing read access to the package file."""
        return _PhysPkgReader.factory(self._pkg_file)


class PackageWriter:
    """Writes a zip-format OPC package to `pkg_file`.

    `pkg_file` can be either a path to a zip file (a string or path object) or a file-like
    object. `pkg_rels` is the |_Relationships| object containing relationships for the package.
    `parts` is a sequence of |Part| subtype instance to be written to the package.

    Its single API classmethod is :meth:`write`. This class is not intended to be instantiated.
    """

    def __init__(
        self,
        pkg_file: str | os.PathLike[str] | IO[bytes],
        pkg_rels: _Relationships,
        parts: Sequence[Part],
    ):
        self._pkg_file = pkg_file
        self._pkg_rels = pkg_rels
        self._parts = parts

    @classmethod
    def write(
        cls,
        pkg_file: str | os.PathLike[str] | IO[bytes],
        pkg_rels: _Relationships,
        parts: Sequence[Part],
    ) -> None:
        """Write a physical package (.pptx file) to `pkg_file`.

        The serialized package contains `pkg_rels` and `parts`, a content-types stream based on
        the content type of each part, and a .rels file for each part that has relationships.

        Writing to a path is all-or-nothing: the package is written to a temporary file beside
        the destination and moved into place only once it is complete, so a failure part-way
        leaves whatever was at the path before exactly as it was.
        """
        cls(pkg_file, pkg_rels, parts)._write()

    def _write(self) -> None:
        """Write physical package (.pptx file)."""
        self._raise_on_shared_partname()
        with _PhysPkgWriter.factory(self._pkg_file) as phys_writer:
            self._write_content_types_stream(phys_writer)
            self._write_pkg_rels(phys_writer)
            self._write_parts(phys_writer)

    def _raise_on_shared_partname(self) -> None:
        """Raise |ValueError| if two of the parts to be written have the same partname.

        Each part becomes the zip member named by its partname, so two parts with one name would
        produce a zip with a duplicated member: PowerPoint rejects such a file and the second
        part silently replaces the first on the next load. `OpcPackage.save()` renames colliding
        parts before it gets here; this is the last line of defence for any other caller, and it
        runs before anything is written.
        """
        seen: set[str] = set()
        for part in self._parts:
            partname = part.partname
            if partname in seen:
                raise ValueError(
                    "cannot write package: more than one part is named '%s'" % partname
                )
            seen.add(partname)

    def _write_content_types_stream(self, phys_writer: _PhysPkgWriter) -> None:
        """Write `[Content_Types].xml` part to the physical package.

        This part must contain an appropriate content type lookup target for each part in the
        package.
        """
        phys_writer.write(
            CONTENT_TYPES_URI,
            serialize_part_xml(_ContentTypesItem.xml_for(self._parts)),
        )

    def _write_parts(self, phys_writer: _PhysPkgWriter) -> None:
        """Write blob of each part in `parts` to the package.

        A rels item for each part is also written when the part has relationships.
        """
        for part in self._parts:
            phys_writer.write(part.partname, part.blob)
            if part._rels:  # pyright: ignore[reportPrivateUsage]
                phys_writer.write(part.partname.rels_uri, part.rels.xml)

    def _write_pkg_rels(self, phys_writer: _PhysPkgWriter) -> None:
        """Write the XML rels item for `pkg_rels` ('/_rels/.rels') to the package."""
        phys_writer.write(PACKAGE_URI.rels_uri, self._pkg_rels.xml)


class _PhysPkgReader(Container[PackURI]):
    """Base class for physical package reader objects."""

    def __contains__(self, item: object) -> bool:
        """Must be implemented by each subclass."""
        raise NotImplementedError(  # pragma: no cover
            "`%s` must implement `.__contains__()`" % type(self).__name__
        )

    def __getitem__(self, pack_uri: PackURI) -> bytes:
        """Blob for part corresponding to `pack_uri`."""
        raise NotImplementedError(  # pragma: no cover
            f"`{type(self).__name__}` must implement `.__contains__()`"
        )

    def close(self) -> None:
        """Release any resource held open for reading. A no-op unless overridden."""

    @classmethod
    def factory(cls, pkg_file: str | os.PathLike[str] | IO[bytes]) -> _PhysPkgReader:
        """Return |_PhysPkgReader| subtype instance appropriage for `pkg_file`."""
        # --- a path object is a path, exactly like the str it stands for ---
        if isinstance(pkg_file, os.PathLike):
            pkg_file = os.fsdecode(pkg_file)

        # --- for pkg_file other than a path, assume it's a stream and pass it to Zip
        # --- reader to sort out
        if not isinstance(pkg_file, str):
            return _ZipPkgReader(pkg_file)

        # --- otherwise we treat `pkg_file` as a path ---
        if os.path.isdir(pkg_file):
            return _DirPkgReader(pkg_file)

        if zipfile.is_zipfile(pkg_file):
            return _ZipPkgReader(pkg_file)

        if not os.path.exists(pkg_file):
            raise _PackageFileNotFoundError("Package not found at '%s'" % pkg_file)

        raise InvalidPackageError(_not_a_package_message("file '%s'" % pkg_file, pkg_file))


class _DirPkgReader(_PhysPkgReader):
    """Implements |PhysPkgReader| interface for OPC package extracted into directory.

    `path` is the path to a directory containing an expanded package.
    """

    def __init__(self, path: str):
        self._path = os.path.abspath(path)

    def __contains__(self, pack_uri: object) -> bool:
        """Return True when part identified by `pack_uri` is present in zip archive."""
        if not isinstance(pack_uri, PackURI):
            return False
        return os.path.exists(posixpath.join(self._path, pack_uri.membername))

    def __getitem__(self, pack_uri: PackURI) -> bytes:
        """Return bytes of file corresponding to `pack_uri` in package directory."""
        path = os.path.join(self._path, pack_uri.membername)
        try:
            with open(path, "rb") as f:
                return f.read()
        except IOError:
            raise KeyError("no member '%s' in package" % pack_uri)


class _ZipPkgReader(_PhysPkgReader):
    """Implements |PhysPkgReader| interface for a zip-file OPC package.

    Members are decompressed one at a time, when asked for. The package loader only asks for
    the items the package's relationships actually lead to, so a member that nothing refers to
    is never inflated, however large it claims to be.
    """

    def __init__(self, pkg_file: str | IO[bytes]):
        self._pkg_file = pkg_file

    def __contains__(self, pack_uri: object) -> bool:
        """Return True when part identified by `pack_uri` is present in zip archive."""
        return pack_uri in self._members

    def __getitem__(self, pack_uri: PackURI) -> bytes:
        """Return bytes for part corresponding to `pack_uri`.

        Raises |KeyError| if no matching member is present in zip archive.
        """
        if pack_uri not in self._members:
            raise KeyError("no member '%s' in package" % pack_uri)
        try:
            return self._zipf.read(self._members[pack_uri])
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as e:
            # -- a bad CRC, a truncated or corrupt deflate stream, a compression method this
            # -- Python cannot read, or an encrypted member --
            raise InvalidPackageError(
                "cannot read '%s' from package: %s" % (pack_uri.membername, e)
            ) from e

    def close(self) -> None:
        """Close the zip archive, if it has been opened.

        A file this reader opened from a path is closed with it; a stream handed in by the
        caller is left open.
        """
        zipf = self.__dict__.pop("_zipf", None)
        if zipf is not None:
            zipf.close()

    @lazyproperty
    def _members(self) -> dict[PackURI, zipfile.ZipInfo]:
        """dict mapping the pack URI of each zip member to its directory entry.

        Reading the directory inflates nothing. When a name occurs more than once the last
        entry wins, which is also the one `ZipFile.read(name)` would return.
        """
        return {PackURI("/%s" % zinfo.filename): zinfo for zinfo in self._zipf.infolist()}

    @lazyproperty
    def _zipf(self) -> zipfile.ZipFile:
        """`ZipFile` instance open for reading."""
        try:
            return zipfile.ZipFile(self._pkg_file, "r")
        except zipfile.BadZipFile as e:
            source = (
                "file '%s'" % self._pkg_file
                if isinstance(self._pkg_file, str)
                else "the stream provided"
            )
            raise InvalidPackageError(_not_a_package_message(source, self._pkg_file)) from e


class _PackageFileNotFoundError(PackageNotFoundError, FileNotFoundError):
    """Raised when there is no file at the path a package was to be opened from.

    A path given as `str` has always raised |PackageNotFoundError| here, while a path object
    used to fall through to `zipfile` and raise `FileNotFoundError`. Both spellings now take the
    same route, and this is both of those errors so neither kind of caller has to change.
    """


# -- the first bytes of an OLE compound file, which is what both a PowerPoint 97-2003 .ppt
# -- and a password-protected (encrypted) .pptx are on disk --
_OLE_COMPOUND_FILE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


def _not_a_package_message(source: str, pkg_file: str | IO[bytes]) -> str:
    """Return the error message for `pkg_file` not being a zip archive at all."""
    message = "%s is not a PowerPoint package (not a zip archive)" % source
    if _leading_bytes(pkg_file, len(_OLE_COMPOUND_FILE_MAGIC)) == _OLE_COMPOUND_FILE_MAGIC:
        message += (
            "; it looks like a legacy .ppt file or a password-protected presentation,"
            " neither of which can be read"
        )
    return message


def _leading_bytes(pkg_file: str | IO[bytes], count: int) -> bytes:
    """Return the first `count` bytes of `pkg_file`, or b"" if they cannot be read."""
    try:
        if isinstance(pkg_file, str):
            with open(pkg_file, "rb") as f:
                return f.read(count)
        pkg_file.seek(0)
        head = pkg_file.read(count)
        return head if isinstance(head, bytes) else b""
    except Exception:
        return b""


class _PhysPkgWriter:
    """Base class for physical package writer objects."""

    @classmethod
    def factory(cls, pkg_file: str | os.PathLike[str] | IO[bytes]) -> _ZipPkgWriter:
        """Return |_PhysPkgWriter| subtype instance appropriage for `pkg_file`.

        Currently the only subtype is `_ZipPkgWriter`, but a `_DirPkgWriter` could be implemented
        or even a `_StreamPkgWriter`.
        """
        return _ZipPkgWriter(pkg_file)

    def write(self, pack_uri: PackURI, blob: bytes) -> None:
        """Write `blob` to package with membername corresponding to `pack_uri`."""
        raise NotImplementedError(  # pragma: no cover
            f"`{type(self).__name__}` must implement `.write()`"
        )


class _ZipPkgWriter(_PhysPkgWriter):
    """Implements |PhysPkgWriter| interface for a zip-file (.pptx file) OPC package.

    When `pkg_file` is a path, the archive is written to a temporary file in the same directory
    and takes the destination's place only on a clean exit from the context (`os.replace()`,
    which is atomic). Should anything fail while the package is being written, the temporary
    file is removed and the destination is left exactly as it was: either the previous good
    file or no file, never a truncated one.

    A file-like `pkg_file` is written to directly; what a caller's stream holds after a failure
    is the caller's to deal with.
    """

    def __init__(self, pkg_file: str | os.PathLike[str] | IO[bytes]):
        self._pkg_file = pkg_file
        # -- both set by `_zipf` when the archive is being written to a temporary file --
        self._temp_path: str | None = None
        self._final_path: str | None = None

    def __enter__(self) -> _ZipPkgWriter:
        """Enable use as a context-manager. Opening zip for writing happens here."""
        return self

    def __exit__(self, *exc: Any) -> None:
        """Close the zip archive on exit from context.

        Closing flushes any pending physical writes and releasing any resources it's using.
        On a clean exit the finished archive is then moved to its destination; on an exception
        (including one raised by the close itself) it is discarded instead.
        """
        failed = bool(exc) and exc[0] is not None
        try:
            self._zipf.close()
            if not failed and self._temp_path is not None and self._final_path is not None:
                os.replace(self._temp_path, self._final_path)
                self._temp_path = None
        finally:
            # -- still set means the archive did not make it to its destination --
            if self._temp_path is not None:
                with contextlib.suppress(OSError):
                    os.remove(self._temp_path)
                self._temp_path = None

    def write(self, pack_uri: PackURI, blob: bytes) -> None:
        """Write `blob` to zip package with membername corresponding to `pack_uri`."""
        date_time = zip_date_time()
        if date_time is None:
            self._zipf.writestr(pack_uri.membername, blob)
            return
        # SOURCE_DATE_EPOCH pins member times so repeated builds are byte-identical.
        info = zipfile.ZipInfo(pack_uri.membername, date_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o600 << 16
        self._zipf.writestr(info, blob)

    @lazyproperty
    def _zipf(self) -> zipfile.ZipFile:
        """`ZipFile` instance open for writing."""
        return zipfile.ZipFile(
            self._write_target(), "w", compression=zipfile.ZIP_DEFLATED, strict_timestamps=False
        )

    def _write_target(self) -> str | IO[bytes]:
        """Return what the archive is to be written to: a temporary sibling file where possible.

        A stream is returned as it is. So is a path that cannot or must not be replaced: one
        that names something other than a regular file (a device such as `/dev/null`, a named
        pipe, a directory), or one in a directory where no sibling file can be created. Those
        are written to in place, as they always were.
        """
        pkg_file = self._pkg_file
        if isinstance(pkg_file, os.PathLike):
            pkg_file = os.fsdecode(pkg_file)
        if not isinstance(pkg_file, str):
            return pkg_file

        # -- follow symlinks, so it is the file linked to that gets replaced, not the link --
        final_path = os.path.realpath(pkg_file)
        if os.path.lexists(final_path) and not os.path.isfile(final_path):
            return pkg_file

        directory, filename = os.path.split(final_path)
        temp_path = None
        for _ in range(100):
            candidate = os.path.join(directory, ".%s.%s.tmp" % (filename, secrets.token_hex(4)))
            try:
                # -- created like any new file would be, so the usual permissions (umask) apply
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            except FileExistsError:
                continue
            except OSError:
                # -- e.g. a read-only or missing directory: writing in place either works
                # -- (the file itself is writable) or raises the error the caller expects
                return pkg_file
            os.close(fd)
            temp_path = candidate
            break
        if temp_path is None:  # pragma: no cover - 100 random names all taken
            return pkg_file

        # -- a file that is being replaced keeps its permissions (and owner, where allowed) --
        with contextlib.suppress(OSError):
            existing = os.stat(final_path)
            os.chmod(temp_path, stat.S_IMODE(existing.st_mode))
            chown = getattr(os, "chown", None)
            if chown is not None:
                chown(temp_path, existing.st_uid, existing.st_gid)

        self._temp_path, self._final_path = temp_path, final_path
        return temp_path


class _ContentTypesItem:
    """Composes content-types "part" ([Content_Types].xml) for a collection of parts."""

    def __init__(self, parts: Sequence[Part]):
        self._parts = parts

    @classmethod
    def xml_for(cls, parts: Sequence[Part]) -> CT_Types:
        """Return content-types XML mapping each part in `parts` to a content-type.

        The resulting XML is suitable for storage as `[Content_Types].xml` in an OPC package.
        """
        return cls(parts)._xml

    @lazyproperty
    def _xml(self) -> CT_Types:
        """lxml.etree._Element containing the content-types item.

        This XML object is suitable for serialization to the `[Content_Types].xml` item for an OPC
        package. Although the sequence of elements is not strictly significant, as an aid to
        testing and readability Default elements are sorted by extension and Override elements are
        sorted by partname.
        """
        defaults, overrides = self._defaults_and_overrides
        _types_elm = CT_Types.new()

        for ext, content_type in sorted(defaults.items()):
            _types_elm.add_default(ext, content_type)
        for partname, content_type in sorted(overrides.items()):
            _types_elm.add_override(partname, content_type)

        return _types_elm

    @lazyproperty
    def _defaults_and_overrides(self) -> tuple[dict[str, str], dict[PackURI, str]]:
        """pair of dict (defaults, overrides) accounting for all parts.

        `defaults` is {ext: content_type} and overrides is {partname: content_type}.
        """
        defaults = CaseInsensitiveDict(rels=CT.OPC_RELATIONSHIPS, xml=CT.XML)
        overrides: dict[PackURI, str] = {}

        for part in self._parts:
            partname, content_type = part.partname, part.content_type
            ext = partname.ext
            if (ext.lower(), content_type) in default_content_types:
                defaults[ext] = content_type
            else:
                overrides[partname] = content_type

        return defaults, overrides
