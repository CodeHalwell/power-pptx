"""Fundamental Open Packaging Convention (OPC) objects.

The :mod:`power_pptx.packaging` module coheres around the concerns of reading and writing
presentations to and from a .pptx file.
"""

from __future__ import annotations

import collections
import os
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    DefaultDict,
    Iterator,
    Mapping,
    Sequence,
    Set,
    cast,
)

from power_pptx.exc import InvalidPackageError
from power_pptx.opc.constants import RELATIONSHIP_TARGET_MODE as RTM
from power_pptx.opc.constants import RELATIONSHIP_TYPE as RT
from power_pptx.opc.oxml import CT_Relationships, serialize_part_xml
from power_pptx.opc.packuri import (
    CONTENT_TYPES_URI,
    PACKAGE_URI,
    PackURI,
    numbered_partname_pieces,
)
from power_pptx.opc.serialized import PackageReader, PackageWriter
from power_pptx.opc.shared import CaseInsensitiveDict
from power_pptx.oxml import parse_xml
from power_pptx.util import lazyproperty

if TYPE_CHECKING:
    from typing_extensions import Self

    from power_pptx.opc.oxml import CT_Relationship, CT_Types
    from power_pptx.oxml.xmlchemy import BaseOxmlElement
    from power_pptx.package import Package
    from power_pptx.parts.presentation import PresentationPart


class _RelatableMixin:
    """Provide relationship methods required by both the package and each part."""

    def part_related_by(self, reltype: str) -> Part:
        """Return (single) part having relationship to this package of `reltype`.

        Raises |KeyError| if no such relationship is found and |ValueError| if more than one such
        relationship is found.
        """
        return self._rels.part_with_reltype(reltype)

    def relate_to(self, target: Part | str, reltype: str, is_external: bool = False) -> str:
        """Return rId key of relationship of `reltype` to `target`.

        If such a relationship already exists, its rId is returned. Otherwise the relationship is
        added and its new rId returned.
        """
        if isinstance(target, str):
            assert is_external
            return self._rels.get_or_add_ext_rel(reltype, target)

        return self._rels.get_or_add(reltype, target)

    def related_part(self, rId: str) -> Part:
        """Return related |Part| subtype identified by `rId`."""
        return self._rels[rId].target_part

    def target_ref(self, rId: str) -> str:
        """Return URL contained in target ref of relationship identified by `rId`."""
        return self._rels[rId].target_ref

    @lazyproperty
    def _rels(self) -> _Relationships:
        """|_Relationships| object containing relationships from this part to others."""
        raise NotImplementedError(  # pragma: no cover
            "`%s` must implement `.rels`" % type(self).__name__
        )


class OpcPackage(_RelatableMixin):
    """Main API class for |python-opc|.

    A new instance is constructed by calling the :meth:`open` classmethod with a path to a package
    file or file-like object containing a package (.pptx file).
    """

    def __init__(self, pkg_file: str | os.PathLike[str] | IO[bytes]):
        self._pkg_file = pkg_file

    @classmethod
    def open(cls, pkg_file: str | os.PathLike[str] | IO[bytes]) -> Self:
        """Return an |OpcPackage| instance loaded with the contents of `pkg_file`.

        Raises |PackageNotFoundError| when there is no file at a path given, and its subclass
        |InvalidPackageError| when what is there is not a readable package.
        """
        return cls(pkg_file)._load()

    def drop_rel(self, rId: str) -> None:
        """Remove relationship identified by `rId`."""
        self._rels.pop(rId)

    def iter_parts(self) -> Iterator[Part]:
        """Generate exactly one reference to each part in the package."""
        visited: Set[Part] = set()
        for rel in self.iter_rels():
            if rel.is_external:
                continue
            part = rel.target_part
            if part in visited:
                continue
            yield part
            visited.add(part)

    def iter_rels(self) -> Iterator[_Relationship]:
        """Generate exactly one reference to each relationship in package.

        Performs a depth-first traversal of the rels graph.
        """
        visited: Set[Part] = set()

        # -- The walk keeps its own stack of partly-consumed relationship collections rather
        # -- than recursing: a package can chain parts far deeper than the interpreter's
        # -- recursion limit (each part related only to the next), and that must not raise
        # -- RecursionError. The order produced is exactly that of the recursive walk.
        pending: list[Iterator[_Relationship]] = [iter(self._rels.values())]
        while pending:
            for rel in pending[-1]:
                yield rel
                # --- external items can have no relationships ---
                if rel.is_external:
                    continue
                # -- all relationships other than those for the package belong to a part. Once
                # -- that part has been processed, processing it again would lead to the same
                # -- relationships appearing more than once.
                part = rel.target_part
                if part in visited:
                    continue
                visited.add(part)
                # --- descend into relationships of each unvisited target-part ---
                pending.append(iter(part.rels.values()))
                break
            else:
                pending.pop()

    @property
    def main_document_part(self) -> PresentationPart:
        """Return |Part| subtype serving as the main document part for this package.

        In this case it will be a |Presentation| part.
        """
        try:
            return cast("PresentationPart", self.part_related_by(RT.OFFICE_DOCUMENT))
        except KeyError:
            raise InvalidPackageError(
                "package has no main document part: '_rels/.rels' has no officeDocument"
                " relationship to a part that is present in the package"
            ) from None

    def next_partname(self, tmpl: str) -> PackURI:
        """Return |PackURI| next available partname matching `tmpl`.

        `tmpl` is a printf (%)-style template string containing a single replacement item, a '%d'
        to be used to insert the integer portion of the partname. Example:
        '/ppt/slides/slide%d.xml'
        """
        # --- expected next partname is tmpl % n where n is one greater than the number
        # --- of existing partnames that match tmpl. Speed up finding the next one
        # --- (maybe) by searching from the end downward rather than from 1 upward.
        prefix = tmpl[: (tmpl % 42).find("42")]
        partnames = {p.partname for p in self.iter_parts() if p.partname.startswith(prefix)}
        for n in range(len(partnames) + 1, 0, -1):
            candidate_partname = tmpl % n
            if candidate_partname not in partnames:
                return PackURI(candidate_partname)
        raise Exception("ProgrammingError: ran out of candidate_partnames")  # pragma: no cover

    def save(self, pkg_file: str | os.PathLike[str] | IO[bytes]) -> None:
        """Save this package to `pkg_file`.

        `file` can be either a path to a file (a string or path object) or a file-like object.
        """
        parts = tuple(self.iter_parts())
        _resolve_partname_collisions(parts)
        PackageWriter.write(pkg_file, self._rels, parts)

    def _load(self) -> Self:
        """Return the package after loading all parts and relationships."""
        pkg_xml_rels, parts = _PackageLoader.load(self._pkg_file, cast("Package", self))
        self._rels.load_from_xml(PACKAGE_URI, pkg_xml_rels, parts)
        return self

    @lazyproperty
    def _rels(self) -> _Relationships:
        """|Relationships| object containing relationships of this package."""
        return _Relationships(PACKAGE_URI.baseURI)


def _resolve_partname_collisions(parts: Sequence[Part]) -> None:
    """Give each part in `parts` a partname of its own.

    A partname is the part's file name inside the zip, so two parts sharing one would be written
    as two zip members of the same name: a package that PowerPoint rejects and that loses one of
    the parts on the next load. Nothing in the object model enforces uniqueness (a partname is
    just an attribute), so this is checked at the one place it matters, right before writing.

    The first part to claim a name keeps it. A later part with the same name is renamed to the
    first free numbered sibling (`/ppt/slides/slide2.xml` -> `/ppt/slides/slide7.xml`).
    Relationships refer to part objects, not names, so they follow the rename.

    Names are compared without regard to case, as OPC requires: `/ppt/media/Image1.png` and
    `/ppt/media/image1.png` are different zip members but the same part name to PowerPoint.
    """
    seen: Set[str] = set()
    colliding: list[Part] = []
    for part in parts:
        key = part.partname.lower()
        if key in seen:
            colliding.append(part)
        else:
            seen.add(key)

    for part in colliding:
        prefix, suffix = numbered_partname_pieces(part.partname)
        n = 1
        while ("%s%d%s" % (prefix, n, suffix)).lower() in seen:
            n += 1
        part.partname = PackURI("%s%d%s" % (prefix, n, suffix))
        seen.add(part.partname.lower())


def _is_external(rel: CT_Relationship) -> bool:
    """True when relationship element `rel` targets a resource outside the package.

    `TargetMode` is matched without regard to case. The schema spells it "External", but files
    written by other tools carry "external", and reading that as an internal relationship
    turns a URL into a (missing) partname.
    """
    return rel.targetMode.strip().lower() == RTM.EXTERNAL.lower()


def _raise_on_dtd(element: Any, item_name: str) -> None:
    """Raise |InvalidPackageError| if the XML `element` was parsed from declares a DTD.

    OPC forbids DTD declarations in package XML and PowerPoint refuses such a file. Entity
    references are deliberately not expanded on parsing, so an XML part that uses an entity
    declared in its DTD would be written back with the reference but without the declaration:
    a file that can no longer be opened at all. Better to say so on the way in.
    """
    docinfo = element.getroottree().docinfo
    if docinfo.doctype or docinfo.internalDTD is not None:
        raise InvalidPackageError(
            "package item '%s' contains a DTD (<!DOCTYPE ...>), which is not allowed in a"
            " PowerPoint package" % item_name
        )


class _PackageLoader:
    """Function-object that loads a package from disk (or other store)."""

    def __init__(self, pkg_file: str | os.PathLike[str] | IO[bytes], package: Package):
        self._pkg_file = pkg_file
        self._package = package

    @classmethod
    def load(
        cls, pkg_file: str | os.PathLike[str] | IO[bytes], package: Package
    ) -> tuple[CT_Relationships, dict[PackURI, Part]]:
        """Return (pkg_xml_rels, parts) pair resulting from loading `pkg_file`.

        The returned `parts` value is a {partname: part} mapping with each part in the package
        included and constructed complete with its relationships to other parts in the package.

        The returned `pkg_xml_rels` value is a `CT_Relationships` object containing the parsed
        package relationships. It is the caller's responsibility (the package object) to load
        those relationships into its |_Relationships| object.
        """
        return cls(pkg_file, package)._load()

    def _load(self) -> tuple[CT_Relationships, dict[PackURI, Part]]:
        """Return (pkg_xml_rels, parts) pair resulting from loading pkg_file."""
        try:
            parts, xml_rels = self._parts, self._xml_rels

            for partname, part in parts.items():
                part.load_rels_from_xml(xml_rels[partname], parts)

            return xml_rels[PACKAGE_URI], parts
        finally:
            # -- package items are read on demand, so the reader holds the file open until
            # -- everything has been read; that is now, whether or not it went well --
            package_reader = self.__dict__.get("_package_reader")
            if package_reader is not None:
                package_reader.close()

    @lazyproperty
    def _content_types(self) -> _ContentTypeMap:
        """|_ContentTypeMap| object providing content-types for items of this package.

        Provides a content-type (MIME-type) for any given partname.
        """
        if CONTENT_TYPES_URI not in self._package_reader:
            raise InvalidPackageError(
                "package has no '[Content_Types].xml'; it is not a PowerPoint package"
            )
        return _ContentTypeMap.from_xml(self._package_reader[CONTENT_TYPES_URI])

    @lazyproperty
    def _package_reader(self) -> PackageReader:
        """|PackageReader| object providing access to package-items in pkg_file."""
        return PackageReader(self._pkg_file)

    @lazyproperty
    def _parts(self) -> dict[PackURI, Part]:
        """dict {partname: Part} populated with parts loading from package.

        Among other duties, this collection is passed to each relationships collection so each
        relationship can resolve a reference to its target part when required. This reference can
        only be reliably carried out once the all parts have been loaded.
        """
        content_types = self._content_types
        package = self._package
        package_reader = self._package_reader

        parts: dict[PackURI, Part] = {}
        for partname in self._xml_rels:
            # -- "/" is the package itself. Invalid partnames can arise in some packages;
            # -- ignore those rather than raise an exception.
            if partname == "/" or partname not in package_reader:
                continue
            try:
                content_type = content_types[partname]
            except KeyError:
                raise InvalidPackageError(
                    "package part '%s' has no content type in '[Content_Types].xml'"
                    % partname.membername
                ) from None
            part = PartFactory(partname, content_type, package, blob=package_reader[partname])
            if isinstance(part, XmlPart):
                _raise_on_dtd(
                    part._element,  # pyright: ignore[reportPrivateUsage]
                    partname.membername,
                )
            parts[partname] = part
        return parts

    @lazyproperty
    def _xml_rels(self) -> dict[PackURI, CT_Relationships]:
        """dict {partname: xml_rels} for package and all package parts.

        This is used as the basis for other loading operations such as loading parts and
        populating their relationships.
        """
        xml_rels: dict[PackURI, CT_Relationships] = {}

        # -- Depth-first, in the order a recursive walk would visit, but with the walk's state
        # -- kept on an explicit stack: one entry per part being worked through, holding its
        # -- base URI and the relationships of it not yet looked at. A hostile (or merely
        # -- odd) package can chain parts thousands deep, each related only to the next, and
        # -- recursion would die with RecursionError on it.
        xml_rels[PACKAGE_URI] = pkg_rels = self._xml_rels_for(PACKAGE_URI)
        pending: list[tuple[str, Iterator[CT_Relationship]]] = [
            (PACKAGE_URI.baseURI, iter(pkg_rels.relationship_lst))
        ]
        while pending:
            base_uri, rels = pending[-1]
            for rel in rels:
                if _is_external(rel):
                    continue
                target_partname = PackURI.from_rel_ref(base_uri, rel.target_ref)
                if target_partname in xml_rels:
                    continue
                xml_rels[target_partname] = target_rels = self._xml_rels_for(target_partname)
                pending.append((target_partname.baseURI, iter(target_rels.relationship_lst)))
                break
            else:
                pending.pop()

        return xml_rels

    def _xml_rels_for(self, partname: PackURI) -> CT_Relationships:
        """Return CT_Relationships object formed by parsing rels XML for `partname`.

        A CT_Relationships object is returned in all cases. A part that has no relationships
        receives an "empty" CT_Relationships object, i.e. containing no `CT_Relationship` objects.
        """
        rels_xml = self._package_reader.rels_xml_for(partname)
        if rels_xml is None:
            # -- a part need not have relationships, but a package without any has no main
            # -- part and so nothing to open --
            if partname == PACKAGE_URI:
                raise InvalidPackageError(
                    "package has no '_rels/.rels'; it is not a PowerPoint package"
                )
            return CT_Relationships.new()
        rels = cast(CT_Relationships, parse_xml(rels_xml))
        _raise_on_dtd(rels, partname.rels_uri.membername)
        return rels


class Part(_RelatableMixin):
    """Base class for package parts.

    Provides common properties and methods, but intended to be subclassed in client code to
    implement specific part behaviors. Also serves as the default class for parts that are not yet
    given specific behaviors.
    """

    def __init__(
        self, partname: PackURI, content_type: str, package: Package, blob: bytes | None = None
    ):
        # --- XmlPart subtypes, don't store a blob (the original XML) ---
        self._partname = partname
        self._content_type = content_type
        self._package = package
        self._blob = blob

    @classmethod
    def load(cls, partname: PackURI, content_type: str, package: Package, blob: bytes) -> Self:
        """Return `cls` instance loaded from arguments.

        This one is a straight pass-through, but subtypes may do some pre-processing, see XmlPart
        for an example.
        """
        return cls(partname, content_type, package, blob)

    @property
    def blob(self) -> bytes:
        """Contents of this package part as a sequence of bytes.

        Intended to be overridden by subclasses. Default behavior is to return the blob initial
        loaded during `Package.open()` operation.
        """
        return self._blob or b""

    @blob.setter
    def blob(self, blob: bytes):
        """Note that not all subclasses use the part blob as their blob source.

        In particular, the |XmlPart| subclass uses its `self._element` to serialize a blob on
        demand. This works fine for binary parts though.
        """
        self._blob = blob

    @property
    def content_type(self) -> str:
        """Content-type (MIME-type) of this part."""
        return self._content_type

    def load_rels_from_xml(self, xml_rels: CT_Relationships, parts: dict[PackURI, Part]) -> None:
        """load _Relationships for this part from `xml_rels`.

        Part references are resolved using the `parts` dict that maps each partname to the loaded
        part with that partname. These relationships are loaded from a serialized package and so
        already have assigned rIds. This method is only used during package loading.
        """
        self._rels.load_from_xml(self._partname.baseURI, xml_rels, parts)

    @lazyproperty
    def package(self) -> Package:
        """Package this part belongs to."""
        return self._package

    @property
    def partname(self) -> PackURI:
        """|PackURI| partname for this part, e.g. "/ppt/slides/slide1.xml"."""
        return self._partname

    @partname.setter
    def partname(self, partname: PackURI):
        if not isinstance(partname, PackURI):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(  # pragma: no cover
                "partname must be instance of PackURI, got '%s'" % type(partname).__name__
            )
        self._partname = partname

    @lazyproperty
    def rels(self) -> _Relationships:
        """Collection of relationships from this part to other parts."""
        # --- this must be public to allow the part graph to be traversed ---
        return self._rels

    def _blob_from_file(self, file: str | IO[bytes]) -> bytes:
        """Return bytes of `file`, which is either a str path or a file-like object."""
        # --- a str `file` is assumed to be a path ---
        if isinstance(file, str):
            with open(file, "rb") as f:
                return f.read()

        # --- otherwise, assume `file` is a file-like object
        # --- reposition file cursor if it has one
        if callable(getattr(file, "seek")):
            file.seek(0)
        return file.read()

    @lazyproperty
    def _rels(self) -> _Relationships:
        """Relationships from this part to others."""
        return _Relationships(self._partname.baseURI)


class XmlPart(Part):
    """Base class for package parts containing an XML payload, which is most of them.

    Provides additional methods to the |Part| base class that take care of parsing and
    reserializing the XML payload and managing relationships to other parts.
    """

    def __init__(
        self, partname: PackURI, content_type: str, package: Package, element: BaseOxmlElement
    ):
        super(XmlPart, self).__init__(partname, content_type, package)
        self._element = element

    @classmethod
    def load(cls, partname: PackURI, content_type: str, package: Package, blob: bytes):
        """Return instance of `cls` loaded with parsed XML from `blob`."""
        return cls(
            partname, content_type, package, element=cast("BaseOxmlElement", parse_xml(blob))
        )

    @property
    def blob(self) -> bytes:  # pyright: ignore[reportIncompatibleMethodOverride]
        """bytes XML serialization of this part."""
        return serialize_part_xml(self._element)

    # -- XmlPart cannot set its blob, which is why pyright complains --

    def drop_rel(self, rId: str) -> None:
        """Remove relationship identified by `rId` if its reference count is under 2.

        Relationships with a reference count of 0 are implicit relationships. Note that only XML
        parts can drop relationships.
        """
        if self._rel_ref_count(rId) < 2:
            self._rels.pop(rId)

    @property
    def part(self):
        """This part.

        This is part of the parent protocol, "children" of the document will not know the part
        that contains them so must ask their parent object. That chain of delegation ends here for
        child objects.
        """
        return self

    def _rel_ref_count(self, rId: str) -> int:
        """Return int count of references in this part's XML to `rId`."""
        return len([r for r in cast("list[str]", self._element.xpath("//@r:id")) if r == rId])


class PartFactory:
    """Constructs a registered subtype of |Part|.

    Client code can register a subclass of |Part| to be used for a package blob based on its
    content type.
    """

    part_type_for: dict[str, type[Part]] = {}

    def __new__(cls, partname: PackURI, content_type: str, package: Package, blob: bytes) -> Part:
        PartClass = cls._part_cls_for(content_type)
        return PartClass.load(partname, content_type, package, blob)

    @classmethod
    def _part_cls_for(cls, content_type: str) -> type[Part]:
        """Return the custom part class registered for `content_type`.

        Returns |Part| if no custom class is registered for `content_type`.
        """
        if content_type in cls.part_type_for:
            return cls.part_type_for[content_type]
        return Part


class _ContentTypeMap:
    """Value type providing dict semantics for looking up content type by partname."""

    def __init__(self, overrides: dict[str, str], defaults: dict[str, str]):
        self._overrides = overrides
        self._defaults = defaults

    def __getitem__(self, partname: PackURI) -> str:
        """Return content-type (MIME-type) for part identified by *partname*."""
        if not isinstance(partname, PackURI):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(
                "_ContentTypeMap key must be <type 'PackURI'>, got %s" % type(partname).__name__
            )

        if partname in self._overrides:
            return self._overrides[partname]

        if partname.ext in self._defaults:
            return self._defaults[partname.ext]

        raise KeyError("no content-type for partname '%s' in [Content_Types].xml" % partname)

    @classmethod
    def from_xml(cls, content_types_xml: bytes) -> _ContentTypeMap:
        """Return |_ContentTypeMap| instance populated from `content_types_xml`."""
        types_elm = cast("CT_Types", parse_xml(content_types_xml))
        _raise_on_dtd(types_elm, CONTENT_TYPES_URI.membername)
        # -- note all partnames in [Content_Types].xml are absolute --
        overrides = CaseInsensitiveDict(
            (o.partName.lower(), o.contentType) for o in types_elm.override_lst
        )
        defaults = CaseInsensitiveDict(
            (d.extension.lower(), d.contentType) for d in types_elm.default_lst
        )
        return cls(overrides, defaults)


class _Relationships(Mapping[str, "_Relationship"]):
    """Collection of |_Relationship| instances having `dict` semantics.

    Relationships are keyed by their rId, but may also be found in other ways, such as by their
    relationship type. |Relationship| objects are keyed by their rId.

    Iterating this collection has normal mapping semantics, generating the keys (rIds) of the
    mapping. `rels.keys()`, `rels.values()`, and `rels.items() can be used as they would be for a
    `dict`.
    """

    def __init__(self, base_uri: str):
        self._base_uri = base_uri

    def __contains__(self, rId: object) -> bool:
        """Implement 'in' operation, like `"rId7" in relationships`."""
        return rId in self._rels

    def __getitem__(self, rId: str) -> _Relationship:
        """Implement relationship lookup by rId using indexed access, like rels[rId]."""
        try:
            return self._rels[rId]
        except KeyError:
            raise KeyError("no relationship with key '%s'" % rId)

    def __iter__(self) -> Iterator[str]:
        """Implement iteration of rIds (iterating a mapping produces its keys)."""
        return iter(self._rels)

    def __len__(self) -> int:
        """Return count of relationships in collection."""
        return len(self._rels)

    def get_or_add(self, reltype: str, target_part: Part) -> str:
        """Return str rId of `reltype` to `target_part`.

        The rId of an existing matching relationship is used if present. Otherwise, a new
        relationship is added and that rId is returned.
        """
        existing_rId = self._get_matching(reltype, target_part)
        return (
            self._add_relationship(reltype, target_part) if existing_rId is None else existing_rId
        )

    def get_or_add_ext_rel(self, reltype: str, target_ref: str) -> str:
        """Return str rId of external relationship of `reltype` to `target_ref`.

        The rId of an existing matching relationship is used if present. Otherwise, a new
        relationship is added and that rId is returned.
        """
        existing_rId = self._get_matching(reltype, target_ref, is_external=True)
        return (
            self._add_relationship(reltype, target_ref, is_external=True)
            if existing_rId is None
            else existing_rId
        )

    def load_from_xml(
        self, base_uri: str, xml_rels: CT_Relationships, parts: dict[PackURI, Part]
    ) -> None:
        """Replace any relationships in this collection with those from `xml_rels`."""

        def iter_valid_rels():
            """Filter out broken relationships such as those pointing to NULL."""
            for rel_elm in xml_rels.relationship_lst:
                # --- Occasionally a PowerPoint plugin or other client will "remove"
                # --- a relationship simply by "voiding" its Target value, like making
                # --- it "/ppt/slides/NULL". Skip any relationships linking to a
                # --- partname that is not present in the package.
                if not _is_external(rel_elm):
                    partname = PackURI.from_rel_ref(base_uri, rel_elm.target_ref)
                    if partname not in parts:
                        continue
                yield _Relationship.from_xml(base_uri, rel_elm, parts)

        self._rels.clear()
        self._rels.update((rel.rId, rel) for rel in iter_valid_rels())

    def part_with_reltype(self, reltype: str) -> Part:
        """Return target part of relationship with matching `reltype`.

        Raises |KeyError| if not found and |ValueError| if more than one matching relationship is
        found.
        """
        rels_of_reltype = self._rels_by_reltype[reltype]

        if len(rels_of_reltype) == 0:
            raise KeyError("no relationship of type '%s' in collection" % reltype)

        if len(rels_of_reltype) > 1:
            raise ValueError("multiple relationships of type '%s' in collection" % reltype)

        return rels_of_reltype[0].target_part

    def pop(self, rId: str) -> _Relationship:
        """Return |_Relationship| identified by `rId` after removing it from collection.

        The caller is responsible for ensuring it is no longer required.
        """
        return self._rels.pop(rId)

    @property
    def xml(self):
        """bytes XML serialization of this relationship collection.

        This value is suitable for storage as a .rels file in an OPC package. Includes a `<?xml..`
        declaration header with encoding as UTF-8.
        """
        rels_elm = CT_Relationships.new()

        # -- Sequence <Relationship> elements deterministically (in numerical order) to
        # -- simplify testing and manual inspection.
        def iter_rels_in_numerical_order():
            sorted_num_rId_pairs = sorted(
                (
                    int(rId[3:]) if rId.startswith("rId") and rId[3:].isdigit() else 0,
                    rId,
                )
                for rId in self.keys()
            )
            return (self[rId] for _, rId in sorted_num_rId_pairs)

        for rel in iter_rels_in_numerical_order():
            rels_elm.add_rel(rel.rId, rel.reltype, rel.target_ref, rel.is_external)

        return rels_elm.xml_file_bytes

    def _add_relationship(self, reltype: str, target: Part | str, is_external: bool = False) -> str:
        """Return str rId of |_Relationship| newly added to spec."""
        rId = self._next_rId
        self._rels[rId] = _Relationship(
            self._base_uri,
            rId,
            reltype,
            target_mode=RTM.EXTERNAL if is_external else RTM.INTERNAL,
            target=target,
        )
        return rId

    def _get_matching(
        self, reltype: str, target: Part | str, is_external: bool = False
    ) -> str | None:
        """Return optional str rId of rel of `reltype`, `target`, and `is_external`.

        Returns `None` on no matching relationship
        """
        for rel in self._rels_by_reltype[reltype]:
            if rel.is_external != is_external:
                continue
            rel_target = rel.target_ref if rel.is_external else rel.target_part
            if rel_target == target:
                return rel.rId

        return None

    @property
    def _next_rId(self) -> str:
        """Next str rId available in collection.

        The next rId is the first unused key starting from "rId1" and making use of any gaps in
        numbering, e.g. 'rId2' for rIds ['rId1', 'rId3'].
        """
        # --- The common case is where all sequential numbers starting at "rId1" are
        # --- used and the next available rId is "rId%d" % (len(rels)+1). So we start
        # --- there and count down to produce the best performance.
        for n in range(len(self) + 1, 0, -1):
            rId_candidate = "rId%d" % n  # like 'rId19'
            if rId_candidate not in self._rels:
                return rId_candidate
        raise Exception(
            "ProgrammingError: Impossible to have more distinct rIds than relationships"
        )

    @lazyproperty
    def _rels(self) -> dict[str, _Relationship]:
        """dict {rId: _Relationship} containing relationships of this collection."""
        return {}

    @property
    def _rels_by_reltype(self) -> dict[str, list[_Relationship]]:
        """defaultdict {reltype: [rels]} for all relationships in collection."""
        D: DefaultDict[str, list[_Relationship]] = collections.defaultdict(list)
        for rel in self.values():
            D[rel.reltype].append(rel)
        return D


class _Relationship:
    """Value object describing link from a part or package to another part."""

    def __init__(self, base_uri: str, rId: str, reltype: str, target_mode: str, target: Part | str):
        self._base_uri = base_uri
        self._rId = rId
        self._reltype = reltype
        self._target_mode = target_mode
        self._target = target

    @classmethod
    def from_xml(
        cls, base_uri: str, rel: CT_Relationship, parts: dict[PackURI, Part]
    ) -> _Relationship:
        """Return |_Relationship| object based on CT_Relationship element `rel`."""
        # -- the mode is normalized to its schema spelling here, so `.is_external` holds for
        # -- a file that wrote "external" and the relationship is saved as "External" --
        if _is_external(rel):
            return cls(base_uri, rel.rId, rel.reltype, RTM.EXTERNAL, rel.target_ref)
        target_part = parts[PackURI.from_rel_ref(base_uri, rel.target_ref)]
        return cls(base_uri, rel.rId, rel.reltype, RTM.INTERNAL, target_part)

    @lazyproperty
    def is_external(self) -> bool:
        """True if target_mode is `RTM.EXTERNAL`.

        An external relationship is a link to a resource outside the package, such as a
        web-resource (URL).
        """
        return self._target_mode == RTM.EXTERNAL

    @lazyproperty
    def reltype(self) -> str:
        """Member of RELATIONSHIP_TYPE describing relationship of target to source."""
        return self._reltype

    @lazyproperty
    def rId(self) -> str:
        """str relationship-id, like 'rId9'.

        Corresponds to the `Id` attribute on the `CT_Relationship` element and uniquely identifies
        this relationship within its peers for the source-part or package.
        """
        return self._rId

    @lazyproperty
    def target_part(self) -> Part:
        """|Part| or subtype referred to by this relationship."""
        if self.is_external:
            raise ValueError(
                "`.target_part` property on _Relationship is undefined when "
                "target-mode is external"
            )
        assert isinstance(self._target, Part)
        return self._target

    @property
    def target_partname(self) -> PackURI:
        """|PackURI| instance containing partname targeted by this relationship.

        Raises `ValueError` on reference if target_mode is external. Use :attr:`target_mode` to
        check before referencing.

        Read from the target part on each access, never cached: a part can be renamed after this
        relationship is first serialized (slide parts are renumbered when `prs.slides` is first
        used), and a remembered name would then be written to the .rels file for a part that is
        saved under a different one.
        """
        if self.is_external:
            raise ValueError(
                "`.target_partname` property on _Relationship is undefined when "
                "target-mode is external"
            )
        assert isinstance(self._target, Part)
        return self._target.partname

    @property
    def target_ref(self) -> str:
        """str reference to relationship target.

        For internal relationships this is the relative partname, suitable for serialization
        purposes. For an external relationship it is typically a URL.

        Like `.target_partname`, this is computed on each access so it always names the target
        part as it is called now.
        """
        if self.is_external:
            assert isinstance(self._target, str)
            return self._target

        return self.target_partname.relative_ref(self._base_uri)
