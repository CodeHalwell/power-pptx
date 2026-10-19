"""Objects related to system font file lookup."""

from __future__ import annotations

import os
import sys
from struct import calcsize, error as struct_error, unpack_from

from power_pptx.util import lazyproperty


#: Environment variable holding extra font directories (``os.pathsep``
#: separated). They are searched with :func:`register_font_dir` folders and
#: take precedence over the operating-system font folders.
FONT_DIRS_ENV = "POWER_PPTX_FONT_DIRS"

#: CSS-style numeric weights and the face names conventionally used for them.
WEIGHT_NAMES = {
    100: "Thin",
    200: "ExtraLight",
    300: "Light",
    400: "Regular",
    500: "Medium",
    600: "SemiBold",
    700: "Bold",
    800: "ExtraBold",
    900: "Black",
}
_WEIGHT_ALIASES = {name.lower(): weight for weight, name in WEIGHT_NAMES.items()}
_WEIGHT_ALIASES.update({"normal": 400, "demibold": 600, "heavy": 900})

_registered_dirs: list[str] = []
# Explicit per-style files from register_font_family(), keyed like the
# installed-font index; they win over anything found by scanning folders.
_registered_files: dict[tuple[str, bool, bool], str] = {}
_registered_faces: dict[tuple[str, int, bool], str] = {}


class FontFiles(object):
    """A class-based singleton serving as a lazy cache for system font details."""

    _font_files = None
    _font_faces = None

    @classmethod
    def find(cls, family_name: str, is_bold: bool, is_italic: bool) -> str:
        """Return the absolute path to an installed OpenType font.

        File is matched by `family_name` and the styles `is_bold` and `is_italic`.
        Files registered with :func:`register_font_family` win, then folders from
        :func:`register_font_dir` / ``POWER_PPTX_FONT_DIRS``, then system folders.
        """
        key = (family_name, is_bold, is_italic)
        if key in _registered_files:
            return _registered_files[key]
        if cls._font_files is None:
            cls._font_files = cls._installed_fonts()
        return cls._font_files[key]

    @classmethod
    def find_face(cls, family_name: str, weight: int, is_italic: bool) -> str:
        """Return the path to the face of `family_name` with numeric `weight`.

        Matches the typographic family (name ID 16, e.g. ``Inter``) or the legacy
        family (name ID 1, e.g. ``Inter Medium``) against the OS/2 weight class.
        Raises |KeyError| when no such face is available.
        """
        key = (family_name, weight, is_italic)
        if key in _registered_faces:
            return _registered_faces[key]
        if cls._font_faces is None:
            cls._font_faces = cls._installed_faces()
        return cls._font_faces[key]

    @classmethod
    def clear_cache(cls):
        """Forget scanned fonts so the next lookup rescans every font folder."""
        cls._font_files = None
        cls._font_faces = None

    @classmethod
    def _installed_fonts(cls):
        """
        Return a dict mapping a font descriptor to its font file path,
        containing all the font files resident on the current machine. The
        font descriptor is a (family_name, is_bold, is_italic) 3-tuple.
        Registered folders are scanned last so their files take precedence.
        """
        fonts = {}
        for d in [*cls._font_directories(), *registered_font_dirs()]:
            for key, path in cls._iter_font_files_in(d):
                fonts[key] = path
        return fonts

    @classmethod
    def _installed_faces(cls):
        """Return a ``(family, weight, is_italic) -> path`` index of every font file.

        Each file is indexed under both its typographic and legacy family names.
        """
        faces = {}
        for d in [*cls._font_directories(), *registered_font_dirs()]:
            for path in cls._iter_font_paths_in(d):
                try:
                    with _Font.open(path) as f:
                        families = {f.family_name, f.typographic_family_name}
                        weight, italic = f.weight, f.is_italic
                except (OSError, KeyError, ValueError, struct_error):
                    continue
                for family in families:
                    if isinstance(family, str):
                        faces[(family, weight, italic)] = path
        return faces

    @classmethod
    def _iter_font_paths_in(cls, directory):
        """Generate the absolute paths of the OpenType font files under *directory*."""
        if not os.path.isdir(directory):
            return
        for root, dirs, files in os.walk(directory):
            for filename in sorted(files):
                if os.path.splitext(filename)[1].lower() in (".otf", ".ttf"):
                    yield os.path.abspath(os.path.join(root, filename))

    @classmethod
    def _font_directories(cls):
        """
        Return a sequence of directory paths likely to contain fonts on the
        current platform. Returns an empty sequence on unrecognised platforms,
        in which case `find()` will not match any installed font and callers
        are expected to fall back to a default font.
        """
        if sys.platform.startswith("darwin"):
            return cls._os_x_font_directories()
        if sys.platform.startswith("win32"):
            return cls._windows_font_directories()
        if sys.platform.startswith("linux"):
            return cls._linux_font_directories()
        return []

    @classmethod
    def _iter_font_files_in(cls, directory):
        """
        Generate the OpenType font files found in and under *directory*. Each
        item is a key/value pair. The key is a (family_name, is_bold,
        is_italic) 3-tuple, like ('Arial', True, False), and the value is the
        absolute path to the font file. Directories that do not exist or are
        not readable are skipped silently so a probe list of conventional
        platform paths can be passed in without pre-filtering.
        """
        if not os.path.isdir(directory):
            return
        for root, dirs, files in os.walk(directory):
            for filename in files:
                file_ext = os.path.splitext(filename)[1]
                if file_ext.lower() not in (".otf", ".ttf"):
                    continue
                path = os.path.abspath(os.path.join(root, filename))
                try:
                    with _Font.open(path) as f:
                        yield ((f.family_name, f.is_bold, f.is_italic), path)
                except (OSError, KeyError, ValueError, struct_error):
                    # Skip malformed or unreadable font files rather than
                    # aborting the whole scan; one bad font on disk should
                    # not break `fit_text` for everyone else.
                    continue

    @classmethod
    def _os_x_font_directories(cls):
        """
        Return a sequence of directory paths on a Mac in which fonts are
        likely to be located.
        """
        os_x_font_dirs = [
            "/Library/Fonts",
            "/Network/Library/Fonts",
            "/System/Library/Fonts",
        ]
        home = os.environ.get("HOME")
        if home is not None:
            os_x_font_dirs.extend(
                [os.path.join(home, "Library", "Fonts"), os.path.join(home, ".fonts")]
            )
        return os_x_font_dirs

    @classmethod
    def _windows_font_directories(cls):
        """
        Return a sequence of directory paths on Windows in which fonts are
        likely to be located.
        """
        return [r"C:\Windows\Fonts"]

    @classmethod
    def _linux_font_directories(cls):
        """
        Return a sequence of directory paths on Linux in which fonts are
        likely to be located.
        """
        linux_font_dirs = [
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            "/usr/share/fonts/truetype",
        ]
        home = os.environ.get("HOME")
        if home is not None:
            linux_font_dirs.extend(
                [
                    os.path.join(home, ".fonts"),
                    os.path.join(home, ".local", "share", "fonts"),
                ]
            )
        return linux_font_dirs


class _Font(object):
    """
    A wrapper around an OTF/TTF font file stream that knows how to parse it
    for its name and style characteristics, e.g. bold and italic.
    """

    def __init__(self, stream):
        self._stream = stream

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, exception_tb):
        self._stream.close()

    @property
    def is_bold(self):
        """
        |True| if this font is marked as a bold style of its font family.
        """
        try:
            return self._tables["head"].is_bold
        except KeyError:
            # some files don't have a head table
            return False

    @property
    def is_italic(self):
        """
        |True| if this font is marked as an italic style of its font family.
        """
        try:
            return self._tables["head"].is_italic
        except KeyError:
            # some files don't have a head table
            return False

    @property
    def weight(self):
        """The OS/2 ``usWeightClass`` (100–900), or 700/400 from the bold flag.

        Out-of-range legacy values are rounded to the nearest hundred.
        """
        try:
            value = self._tables["OS/2"].weight_class
        except (KeyError, struct_error):
            value = 0
        if not 1 <= value <= 1000:
            return 700 if self.is_bold else 400
        return min(900, max(100, int(round(value / 100.0)) * 100))

    @property
    def typographic_family_name(self):
        """The typographic family name (name ID 16), falling back to the family name."""
        return self._tables["name"].typographic_family_name or self.family_name

    @classmethod
    def open(cls, font_file_path):
        """
        Return a |_Font| instance loaded from *font_file_path*.
        """
        return cls(_Stream.open(font_file_path))

    @property
    def family_name(self):
        """
        The name of the typeface family for this font, e.g. 'Arial'. The full
        typeface name includes optional style names, such as 'Regular' or
        'Bold Italic'. This attribute is only the common base name shared by
        all fonts in the family.
        """
        return self._tables["name"].family_name

    @lazyproperty
    def _fields(self):
        """5-tuple containing the fields read from the font file header.

        Also known as the offset table.
        """
        # sfnt_version, tbl_count, search_range, entry_selector, range_shift
        return self._stream.read_fields(">4sHHHH", 0)

    def _iter_table_records(self):
        """
        Generate a (tag, offset, length) 3-tuple for each of the tables in
        this font file.
        """
        count = self._table_count
        bufr = self._stream.read(offset=12, length=count * 16)
        tmpl = ">4sLLL"
        for i in range(count):
            offset = i * 16
            tag, checksum, off, len_ = unpack_from(tmpl, bufr, offset)
            yield tag.decode("utf-8"), off, len_

    @lazyproperty
    def _tables(self):
        """
        A mapping of OpenType table tag, e.g. 'name', to a table object
        providing access to the contents of that table.
        """
        return dict(
            (tag, _TableFactory(tag, self._stream, off, len_))
            for tag, off, len_ in self._iter_table_records()
        )

    @property
    def _table_count(self):
        """
        The number of tables in this OpenType font file.
        """
        return self._fields[1]


class _Stream(object):
    """A thin wrapper around a binary file that facilitates reading C-struct values."""

    def __init__(self, file):
        self._file = file

    @classmethod
    def open(cls, path):
        """Return |_Stream| providing binary access to contents of file at `path`."""
        return cls(open(path, "rb"))

    def close(self):
        """
        Close the wrapped file. Using the stream after closing raises an
        exception.
        """
        self._file.close()

    def read(self, offset, length):
        """
        Return *length* bytes from this stream starting at *offset*.
        """
        self._file.seek(offset)
        return self._file.read(length)

    def read_fields(self, template, offset=0):
        """
        Return a tuple containing the C-struct fields in this stream
        specified by *template* and starting at *offset*.
        """
        self._file.seek(offset)
        bufr = self._file.read(calcsize(template))
        return unpack_from(template, bufr)


class _BaseTable(object):
    """
    Base class for OpenType font file table objects.
    """

    def __init__(self, tag, stream, offset, length):
        self._tag = tag
        self._stream = stream
        self._offset = offset
        self._length = length


class _HeadTable(_BaseTable):
    """
    OpenType font table having the tag 'head' and containing certain header
    information for the font, including its bold and/or italic style.
    """

    def __init__(self, tag, stream, offset, length):
        super(_HeadTable, self).__init__(tag, stream, offset, length)

    @property
    def is_bold(self):
        """
        |True| if this font is marked as having emboldened characters.
        """
        return bool(self._macStyle & 1)

    @property
    def is_italic(self):
        """
        |True| if this font is marked as having italicized characters.
        """
        return bool(self._macStyle & 2)

    @lazyproperty
    def _fields(self):
        """
        A 17-tuple containing the fields in this table.
        """
        return self._stream.read_fields(">4s4sLLHHqqhhhhHHHHH", self._offset)

    @property
    def _macStyle(self):
        """
        The unsigned short value of the 'macStyle' field in this head table.
        """
        return self._fields[12]


class _OS2Table(_BaseTable):
    """The OpenType 'OS/2' table; only the weight class is read."""

    @property
    def weight_class(self):
        """The unsigned ``usWeightClass`` field, e.g. 500 for a Medium face."""
        return self._stream.read_fields(">HhH", self._offset)[2]


class _NameTable(_BaseTable):
    """
    An OpenType font table having the tag 'name' and containing the
    name-related strings for the font.
    """

    def __init__(self, tag, stream, offset, length):
        super(_NameTable, self).__init__(tag, stream, offset, length)

    @property
    def family_name(self):
        """
        The name of the typeface family for this font, e.g. 'Arial'.
        """

        def find_first(dict_, keys, default=None):
            for key in keys:
                value = dict_.get(key)
                if value is not None:
                    return value
            return default

        # keys for Unicode, Mac, and Windows family name, respectively
        return find_first(self._names, ((0, 1), (1, 1), (3, 1)))

    @property
    def typographic_family_name(self):
        """The typographic family name (name ID 16), e.g. 'Inter' for Inter Medium."""
        for key in ((3, 16), (0, 16), (1, 16)):
            value = self._names.get(key)
            if value is not None:
                return value
        return None

    @staticmethod
    def _decode_name(raw_name, platform_id, encoding_id):
        """
        Return the unicode name decoded from *raw_name* using the encoding
        implied by the combination of *platform_id* and *encoding_id*.
        """
        if platform_id == 1:
            # reject non-Roman Mac font names
            if encoding_id != 0:
                return None
            return raw_name.decode("mac-roman")
        elif platform_id in (0, 3):
            return raw_name.decode("utf-16-be")
        else:
            return None

    def _iter_names(self):
        """Generate a key/value pair for each name in this table.

        The key is a (platform_id, name_id) 2-tuple and the value is the unicode text
        corresponding to that key.
        """
        table_format, count, strings_offset = self._table_header
        table_bytes = self._table_bytes

        for idx in range(count):
            platform_id, name_id, name = self._read_name(table_bytes, idx, strings_offset)
            if name is None:
                continue
            yield ((platform_id, name_id), name)

    @staticmethod
    def _name_header(bufr, idx):
        """
        The (platform_id, encoding_id, language_id, name_id, length,
        name_str_offset) 6-tuple encoded in each name record C-struct.
        """
        name_hdr_offset = 6 + idx * 12
        return unpack_from(">HHHHHH", bufr, name_hdr_offset)

    @staticmethod
    def _raw_name_string(bufr, strings_offset, str_offset, length):
        """
        Return the *length* bytes comprising the encoded string in *bufr* at
        *str_offset* in the strings area beginning at *strings_offset*.
        """
        offset = strings_offset + str_offset
        tmpl = "%ds" % length
        return unpack_from(tmpl, bufr, offset)[0]

    def _read_name(self, bufr, idx, strings_offset):
        """Return a (platform_id, name_id, name) 3-tuple for name at `idx` in `bufr`.

        The triple looks like (0, 1, 'Arial'). `strings_offset` is the for the name at
        `idx` position in `bufr`. `strings_offset` is the index into `bufr` where actual
        name strings begin. The returned name is a unicode string.
        """
        platform_id, enc_id, lang_id, name_id, length, str_offset = self._name_header(bufr, idx)
        name = self._read_name_text(bufr, platform_id, enc_id, strings_offset, str_offset, length)
        return platform_id, name_id, name

    def _read_name_text(
        self, bufr, platform_id, encoding_id, strings_offset, name_str_offset, length
    ):
        """
        Return the unicode name string at *name_str_offset* or |None| if
        decoding its format is not supported.
        """
        raw_name = self._raw_name_string(bufr, strings_offset, name_str_offset, length)
        return self._decode_name(raw_name, platform_id, encoding_id)

    @lazyproperty
    def _table_bytes(self):
        """
        The binary contents of this name table.
        """
        return self._stream.read(self._offset, self._length)

    @property
    def _table_header(self):
        """
        The (table_format, name_count, strings_offset) 3-tuple contained
        in the header of this table.
        """
        return unpack_from(">HHH", self._table_bytes)

    @lazyproperty
    def _names(self):
        """A mapping of (platform_id, name_id) keys to string names for this font."""
        return dict(self._iter_names())


def _TableFactory(tag, stream, offset, length):
    """
    Return an instance of |Table| appropriate to *tag*, loaded from
    *font_file* with content of *length* starting at *offset*.
    """
    TableClass = {"head": _HeadTable, "name": _NameTable, "OS/2": _OS2Table}.get(tag, _BaseTable)
    return TableClass(tag, stream, offset, length)


def register_font_dir(path: str | os.PathLike[str]) -> None:
    """Search the fonts under `path` before the operating-system font folders.

    Lets a project measure with fonts it ships next to its code
    (``assets/fonts/inter/*.ttf``) without installing them system-wide, so
    ``strict_fonts=True`` works the same on a laptop, in Docker and in CI::

        register_font_dir(Path(__file__).parent / "assets" / "fonts")

    Registered folders are also handed to LibreOffice by
    :func:`~power_pptx.render.render_slides` and ``power-pptx review``.
    The ``POWER_PPTX_FONT_DIRS`` environment variable (``os.pathsep``
    separated) adds folders the same way. Registering a folder twice is a
    no-op; the font index is rebuilt on the next lookup.
    """
    directory = os.path.abspath(os.fspath(path))
    if not os.path.isdir(directory):
        raise ValueError(f"Font directory {directory!r} does not exist")
    if directory not in _registered_dirs:
        _registered_dirs.append(directory)
    FontFiles.clear_cache()


def register_font_family(
    family_name: str,
    *,
    regular: str | os.PathLike[str] | None = None,
    bold: str | os.PathLike[str] | None = None,
    italic: str | os.PathLike[str] | None = None,
    bold_italic: str | os.PathLike[str] | None = None,
    weights: dict[int | str, str | os.PathLike[str]] | None = None,
) -> None:
    """Map `family_name` styles to explicit font files.

    Use this when file names or name tables don't match the family you
    write in the deck, or to pin exactly which file measures each style::

        register_font_family(
            "Inter",
            regular="fonts/Inter-Regular.ttf",
            bold="fonts/Inter-Bold.ttf",
            weights={"medium": "fonts/Inter-Medium.ttf", 600: "fonts/Inter-SemiBold.ttf"},
        )

    ``weights`` maps upright weights (``100``–``900`` or names such as
    ``"medium"``) to files. Explicit files take precedence over scanned folders.
    """
    if not family_name:
        raise ValueError("family_name is required")
    styles = {
        (False, False): regular,
        (True, False): bold,
        (False, True): italic,
        (True, True): bold_italic,
    }
    faces = {resolve_weight(w): f for w, f in (weights or {}).items()}
    for value in (*styles.values(), *faces.values()):
        if value is not None and not os.path.isfile(os.fspath(value)):
            raise ValueError(f"Font file {os.fspath(value)!r} does not exist")
    for (is_bold, is_italic), value in styles.items():
        if value is not None:
            path = os.path.abspath(os.fspath(value))
            _registered_files[(family_name, is_bold, is_italic)] = path
            _registered_faces[(family_name, 700 if is_bold else 400, is_italic)] = path
    for weight, value in faces.items():
        path = os.path.abspath(os.fspath(value))
        _registered_faces[(family_name, weight, False)] = path
        if weight in (400, 700):
            _registered_files[(family_name, weight == 700, False)] = path


def registered_font_dirs() -> tuple[str, ...]:
    """Return the extra font folders, ``POWER_PPTX_FONT_DIRS`` first.

    Folders named in the environment variable that don't exist are skipped.
    """
    env = [
        os.path.abspath(d)
        for d in os.environ.get(FONT_DIRS_ENV, "").split(os.pathsep)
        if d and os.path.isdir(d)
    ]
    dirs = list(dict.fromkeys([*env, *_registered_dirs]))
    for path in [*_registered_files.values(), *_registered_faces.values()]:
        parent = os.path.dirname(path)
        if parent not in dirs:
            dirs.append(parent)
    return tuple(dirs)


def clear_registered_fonts() -> None:
    """Forget every :func:`register_font_dir` folder and registered family."""
    _registered_dirs.clear()
    _registered_files.clear()
    _registered_faces.clear()
    FontFiles.clear_cache()


def resolve_weight(weight: int | str | None, bold: bool = False) -> int:
    """Return the numeric weight for `weight`, e.g. ``"semibold"`` → ``600``.

    ``None`` means 700 when `bold` is set and 400 otherwise. Numeric weights
    must be multiples of 100 between 100 and 900.
    """
    if weight is None:
        return 700 if bold else 400
    if isinstance(weight, str):
        key = weight.lower().replace("-", "").replace("_", "").replace(" ", "")
        if key not in _WEIGHT_ALIASES:
            raise ValueError(
                f"Unknown font weight {weight!r}; use one of {sorted(_WEIGHT_ALIASES)}"
            )
        value = _WEIGHT_ALIASES[key]
    elif isinstance(weight, bool) or not isinstance(weight, int) or weight not in WEIGHT_NAMES:
        raise ValueError("weight must be a multiple of 100 between 100 and 900, or a name")
    else:
        value = weight
    if bold and value != 700:
        raise ValueError("bold=True conflicts with a non-bold weight; pass only weight")
    return value


def find_font_file(
    family_name: str,
    bold: bool = False,
    italic: bool = False,
    *,
    weight: int | str | None = None,
) -> str | None:
    """Return the path to the installed font file for `family_name`, or None.

    The non-raising form of :meth:`FontFiles.find` — useful for deciding, up
    front, whether font-metric measurement (`TextFrame.fit_text`, and any
    layout maths derived from it) will be exact or a fallback estimate::

        path = find_font_file("Inter", bold=True)
        if path is None:
            ...  # brand font missing in this environment

    `weight` (``"medium"``, ``600``, …) selects a face beyond regular and
    bold, matched on the font's OS/2 weight class. No nearer weight is
    substituted; ``None`` means that exact face isn't available.
    """
    value = resolve_weight(weight, bold)
    try:
        if value in (400, 700):
            return FontFiles.find(family_name, value == 700, italic)
        return FontFiles.find_face(family_name, value, italic)
    except (KeyError, OSError):
        return None


def font_face_family(font_file: str) -> str | None:
    """Return the legacy family name a deck must name to select `font_file`.

    PowerPoint selects Medium or SemiBold faces by their legacy family name
    (name ID 1), e.g. ``"Inter Medium"``, rather than by a weight attribute.
    """
    try:
        with _Font.open(font_file) as f:
            return f.family_name
    except (OSError, KeyError, ValueError, struct_error):
        return None


def font_is_installed(family_name: str, bold: bool = False, italic: bool = False) -> bool:
    """True when `family_name` (in the given style) is installed on this machine.

    The space-aware guarantee degrades to a best guess for fonts that aren't
    installed, so a build that must be exact can check first and either bundle
    the font file (``fit_text(font_file=...)``) or fall back to a family it
    knows is present::

        family = "Inter" if font_is_installed("Inter") else "Arial"
    """
    return find_font_file(family_name, bold, italic) is not None


def installed_font_families() -> tuple[str, ...]:
    """Return the sorted family names of every font installed on this machine.

    Handy when a deck renders with the wrong metrics in CI and you need to see
    what the build box actually has.  Font files that report no family name are
    skipped rather than breaking the listing.
    """
    if FontFiles._font_files is None:  # pyright: ignore[reportPrivateUsage]
        FontFiles._font_files = FontFiles._installed_fonts()  # pyright: ignore[reportPrivateUsage]
    # A font file whose `name` table carries no family record for platform 0, 1
    # or 3 is keyed under `None`.  One such file on the machine would otherwise
    # make this diagnostic helper raise `TypeError` from `sorted()` — the least
    # helpful moment for a diagnostic to fail.
    return tuple(
        sorted({family for family, _, _ in FontFiles._font_files if isinstance(family, str)})
    )
