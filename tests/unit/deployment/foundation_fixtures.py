"""Synthetic Terraform ZIPs for package and submission tests."""

import io
import stat
import warnings
import zipfile

from deployment.foundation_package import SOURCE_FILES


def archive_bytes(*, changed=None, extra=None, timestamp=(2020, 1, 1, 0, 0, 0),
                  member_data=None, member_modes=None, compression=zipfile.ZIP_STORED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name in SOURCE_FILES:
            info = zipfile.ZipInfo('foundation/' + name, timestamp)
            mode = (member_modes or {}).get(name, stat.S_IFREG)
            info.external_attr = (mode | 0o600) << 16
            data = (member_data or {}).get(name, b'changed' if name == changed else name.encode())
            archive.writestr(info, data, compress_type=compression)
        if extra is not None:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr(extra, 'unexpected')
    return stream.getvalue()
