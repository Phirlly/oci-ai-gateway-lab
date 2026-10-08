"""Bounded raw job ZIP download through the protected OCI CLI connection."""

import json
import os
import selectors
import signal
import subprocess
import time

from .credential_errors import CloudReadError
from .credential_identity import valid_ocid
from .foundation_package import MAX_ARCHIVE_BYTES


def download_job_package(client, job_id):
    # Keep the sole stdin frame below POSIX PIPE_BUF so an empty pipe cannot
    # block before the timed read loop, even if the child never consumes input.
    if not isinstance(job_id, str) or len(job_id) > 256 or not valid_ocid(job_id, 'ormjob'):
        raise CloudReadError('A bounded Resource Manager job identifier is required.')
    command = client.command + ['resource-manager', 'job', 'get-job-tf-config',
                                '--file', '-', '--from-json', 'file:///dev/stdin']
    process = None
    try:
        deadline = time.monotonic() + client.timeout
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, shell=False,
                                   start_new_session=True, env=client.environment)
        process.stdin.write(json.dumps({'jobId': job_id}).encode())
        process.stdin.close()
        content = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError
                chunk = os.read(process.stdout.fileno(), min(65536, MAX_ARCHIVE_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > MAX_ARCHIVE_BYTES:
                    raise ValueError
        if process.wait(timeout=max(0, deadline - time.monotonic())) or not content:
            raise ValueError
        return bytes(content)
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        raise CloudReadError('Job configuration is unavailable or unverified; retry the read later.') from None
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            process.stdout.close()
            try:
                process.stdin.close()
            except OSError:
                pass
