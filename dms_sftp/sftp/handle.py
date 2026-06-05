import base64
import logging
import os
import stat as stat_module

try:
    from paramiko import SFTP_EOF, SFTPHandle, SFTPAttributes
    from paramiko.sftp import SFTP_OK
except ImportError:
    pass

_logger = logging.getLogger(__name__)


class DmsSftpHandle(SFTPHandle):
    def __init__(self, dms_file, flags=0):
        self.dms_file = dms_file
        super().__init__(flags)

    def stat(self):
        return SFTPAttributes.from_stat(os.stat_result(
            (
                0o100644,
                0,
                0,
                1,
                self.dms_file.env.uid or 0,
                0,
                int(self.dms_file.size or 0),
                0,
                0,
                0,
            )
        ))

    def read(self, offset, length):
        data = base64.b64decode(self.dms_file.content or b"")
        if offset > len(data):
            return SFTP_EOF
        return data[offset:offset + length]

    def write(self, offset, data):
        existing = base64.b64decode(self.dms_file.content or b"")
        if offset > len(existing):
            existing = existing.ljust(offset, b"\x00")
        new_data = existing[:offset] + data + existing[offset + len(data):]
        self.dms_file.write({"content": base64.b64encode(new_data)})
        return len(data)

    def chattr(self, attr):
        return SFTP_OK

    def close(self):
        pass
