"""Test only: makes this Python behave like a Windows account that may not make symbolic links.

Put this folder on PYTHONPATH and set KPI_CHECK_NO_LINKS=1. Python loads a module named sitecustomize at start, so
every Python that inherits the two variables refuses os.symlink, and with it pathlib's symlink_to, the way Windows
does without Developer Mode or administrator rights: an OSError that is not a PermissionError. Without the variable
this file changes nothing. scripts/DOC-SNIPPETS.md has no part in it; scripts/check.sh and the release never set it.
The Windows test job without links sets it, to prove that the check script passes on such an account."""
import errno
import os

if os.environ.get("KPI_CHECK_NO_LINKS") == "1":
    def _refused(src, dst, *args, **kwargs):
        raise OSError(errno.EINVAL, "a required privilege is not held by the client (KPI_CHECK_NO_LINKS is set)", str(dst))

    os.symlink = _refused
