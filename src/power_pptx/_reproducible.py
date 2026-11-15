"""Build-time pinning for reproducible output (``SOURCE_DATE_EPOCH``).

When the reproducible-builds ``SOURCE_DATE_EPOCH`` environment variable is
set, every timestamp the library would otherwise take from the clock uses it
instead: zip member times in the saved package, the default package core
properties, and the core properties of embedded chart workbooks. Identifiers
that are otherwise random (section ids) are derived from what they identify.
Two builds of the same input then produce byte-identical files.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

SOURCE_DATE_EPOCH = "SOURCE_DATE_EPOCH"

#: Zip archives cannot store times before 1980-01-01.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

#: Namespace of the UUIDs derived in a pinned build. Any fixed value would do.
_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "reproducible.power-pptx")


def source_date_epoch() -> dt.datetime | None:
    """Return ``SOURCE_DATE_EPOCH`` as a naive UTC datetime, or ``None`` when unset."""
    value = os.environ.get(SOURCE_DATE_EPOCH, "").strip()
    if not value:
        return None
    try:
        seconds = int(value)
    except ValueError:
        raise ValueError(
            f"{SOURCE_DATE_EPOCH} must be an integer number of seconds; got {value!r}"
        ) from None
    if seconds < 0:
        raise ValueError(f"{SOURCE_DATE_EPOCH} must not be negative; got {value!r}")
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).replace(tzinfo=None)


def build_time() -> dt.datetime:
    """Return the pinned build time, or the current UTC time when unpinned."""
    pinned = source_date_epoch()
    if pinned is not None:
        return pinned
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def new_uuid(*identity: object) -> uuid.UUID:
    """Return a UUID for a new object: random, or derived from *identity* when pinned.

    A pinned build must not draw on randomness, so under ``SOURCE_DATE_EPOCH``
    the result is the version-5 UUID of *identity*. The caller picks values
    that are the same in every build of the same input and tell the object
    apart from its siblings: its kind, its name, its position.
    """
    if source_date_epoch() is None:
        return uuid.uuid4()
    return uuid.uuid5(_UUID_NAMESPACE, "\x1f".join(str(part) for part in identity))


def zip_date_time() -> tuple[int, int, int, int, int, int] | None:
    """Return the pinned zip member time, clamped to 1980, or ``None`` when unpinned."""
    pinned = source_date_epoch()
    if pinned is None:
        return None
    stamp = pinned.timetuple()[:6]
    return max(stamp, _ZIP_EPOCH)  # type: ignore[return-value]
