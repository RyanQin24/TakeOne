import enum, datetime
if not hasattr(enum, "StrEnum"):
    class StrEnum(str, enum.Enum):
        def __new__(cls, *values):
            value = values[0]
            if not isinstance(value, str):
                raise TypeError(f"{value!r} is not a string")
            member = str.__new__(cls, value)
            member._value_ = value
            return member
        def __str__(self):
            return str(self.value)
        @staticmethod
        def _generate_next_value_(name, start, count, last_values):
            return name.lower()
    enum.StrEnum = StrEnum
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc
# Python 3.11 added the SQLITE_* result codes to the sqlite3 module. The product runs on
# 3.13; this audit host is 3.10. Supplying the constants makes the host MORE faithful to the
# product's runtime, not less -- without them `recording/repository.py:121` raises
# AttributeError on a code path that works correctly on the real target.
import sqlite3 as _sqlite3
for _name, _code in (("SQLITE_BUSY", 5), ("SQLITE_LOCKED", 6)):
    if not hasattr(_sqlite3, _name):
        setattr(_sqlite3, _name, _code)

# Python 3.11 also attaches `sqlite_errorcode` to sqlite3 exceptions. `repository.py:118`
# depends on it to tell "another process holds the finalization lease" (retry) from a real
# error (raise). On 3.10 the attribute is absent, getattr returns None, and the lease path
# raises instead of returning False -- a host artifact that looks exactly like a product bug.
# Derive the two codes this product tests for from the message, as 3.11+ would report them.
_BUSY_TEXT = ("database is locked", "database table is locked")
if not hasattr(_sqlite3.OperationalError, "sqlite_errorcode"):
    def _errorcode(self):
        text = str(self).lower()
        if any(fragment in text for fragment in _BUSY_TEXT):
            return _sqlite3.SQLITE_BUSY
        return None
    _sqlite3.OperationalError.sqlite_errorcode = property(_errorcode)
