"""Small allowlisted Terraform archive and exact job-content attestation."""

import io
import os
import stat
import tempfile
import zipfile
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from .credential_errors import DeliveryError
from .submission_records import digest

SOURCE_FILES = ('.terraform.lock.hcl', 'identity.tf', 'locals.tf', 'outputs.tf',
                'providers.tf', 'secrets.tf', 'variables.tf', 'versions.tf')
MEMBERS = frozenset('foundation/' + name for name in SOURCE_FILES)
MAX_ARCHIVE_BYTES = 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024


def archive_digest(content):
    try:
        if not isinstance(content, bytes) or len(content) > MAX_ARCHIVE_BYTES:
            raise ValueError
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) != len(MEMBERS) or {e.filename for e in entries} != MEMBERS:
                raise ValueError
            if sum(e.file_size for e in entries) > MAX_ARCHIVE_BYTES:
                raise ValueError
            hashes = {}
            for entry in entries:
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if (entry.orig_filename != entry.filename or entry.flag_bits & 1
                        or mode not in (0, stat.S_IFREG)
                        or entry.file_size > MAX_MEMBER_BYTES
                        or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ValueError
                with archive.open(entry) as member:
                    data = member.read(MAX_MEMBER_BYTES + 1)
                if len(data) != entry.file_size or len(data) > MAX_MEMBER_BYTES:
                    raise ValueError
                hashes[entry.filename] = sha256(data).hexdigest()
            return digest(hashes)
    except (OSError, ValueError, RuntimeError, EOFError, zlib.error, zipfile.BadZipFile, NotImplementedError):
        raise DeliveryError('Terraform package contents could not be verified.') from None


@dataclass(frozen=True, repr=False)
class FoundationPackage:
    content: bytes
    digest: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'digest', archive_digest(self.content))

    @classmethod
    def build(cls, directory):
        directory = Path(directory)
        stream = io.BytesIO()
        try:
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError
            with zipfile.ZipFile(stream, 'w') as archive:
                for name in SOURCE_FILES:
                    # O_NOFOLLOW checks the opened file, rather than a prior path lookup.
                    fd = os.open(directory / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, 'rb') as source:
                        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                            raise ValueError
                        content = source.read(MAX_MEMBER_BYTES + 1)
                    if len(content) > MAX_MEMBER_BYTES:
                        raise ValueError
                    info = zipfile.ZipInfo('foundation/' + name, (2020, 1, 1, 0, 0, 0))
                    info.external_attr = (stat.S_IFREG | 0o600) << 16
                    archive.writestr(info, content)
            return cls(stream.getvalue())
        except (OSError, ValueError):
            raise DeliveryError('Required Terraform source files could not be packaged.') from None

    def verify(self, content):
        if archive_digest(content) != self.digest:
            raise DeliveryError('Job Terraform contents differ from the submitted package.')

    @contextmanager
    def path(self):
        with tempfile.TemporaryDirectory(prefix='gateway-foundation-') as directory:
            path = Path(directory) / 'foundation.zip'
            with path.open('xb') as output:
                os.chmod(path, 0o600)
                output.write(self.content)
            yield path
