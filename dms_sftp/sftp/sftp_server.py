import base64
import logging
import os
import stat as stat_module

from odoo import api

try:
    from paramiko import SFTPServerInterface, SFTPServer, SFTPAttributes
    from paramiko.common import o644
    from paramiko.sftp import SFTP_OK, SFTP_NO_SUCH_FILE, SFTP_PERMISSION_DENIED
except ImportError:
    pass

from .handle import DmsSftpHandle

_logger = logging.getLogger(__name__)


class DmsSftpSftpServerInterface(SFTPServerInterface):
    def __init__(self, server, env):
        self.env = api.Environment(env.cr, server.env.user.id, env.context)
        super().__init__(server, env)

    def _resolve(self, path):
        path = path.strip("/")
        if not path:
            return None, None

        parts = path.split("/")

        storage = self.env["dms.storage"].search([("name", "=", parts[0])], limit=1)
        if not storage:
            return None, None

        if len(parts) == 1:
            return storage, "storage"

        current_dir = False
        for i, part in enumerate(parts[1:], start=1):
            domain = [("name", "=", part), ("storage_id", "=", storage.id)]
            if current_dir:
                domain.append(("parent_id", "=", current_dir.id))
            else:
                domain.append(("parent_id", "=", False))

            directory = self.env["dms.directory"].search(domain, limit=1)
            if directory:
                current_dir = directory
                if i == len(parts) - 1:
                    return current_dir, "directory"
            else:
                if i == len(parts) - 1 and current_dir:
                    file_rec = self.env["dms.file"].search([
                        ("name", "=", part),
                        ("directory_id", "=", current_dir.id),
                    ], limit=1)
                    if file_rec:
                        return file_rec, "file"
                return None, None

        if current_dir:
            return current_dir, "directory"
        return None, None

    def _attr(self, record, record_type, name):
        attr = SFTPAttributes()
        attr.filename = name or record.name
        if record_type in ("storage", "directory"):
            attr.st_mode = stat_module.S_IFDIR | stat_module.S_IRUSR | stat_module.S_IXUSR | stat_module.S_IWUSR
            attr.st_size = 0
        else:
            attr.st_mode = stat_module.S_IFREG | stat_module.S_IRUSR | stat_module.S_IWUSR
            attr.st_size = int(record.size or 0)
        attr.st_uid = self.env.uid or 0
        attr.st_gid = 0
        if record.write_date:
            attr.st_mtime = record.write_date.timestamp()
        return attr

    def list_folder(self, path):
        path = path.strip("/")
        if not path:
            try:
                storages = self.env["dms.storage"].search([("is_hidden", "=", False)])
                return [self._attr(s, "storage", s.name) for s in storages]
            except Exception as e:
                _logger.error("list_folder root error: %s", e)
                return SFTP_NO_SUCH_FILE

        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE

        try:
            if record_type == "storage":
                record.check_access("read")
                dirs = record.root_directory_ids.filtered(lambda d: not d.is_hidden)
                return [self._attr(d, "directory", d.name) for d in dirs]
            elif record_type == "directory":
                record.check_access("read")
                result = []
                for child in record.child_directory_ids.filtered(lambda d: not d.is_hidden):
                    result.append(self._attr(child, "directory", child.name))
                for file_rec in record.file_ids:
                    result.append(self._attr(file_rec, "file", file_rec.name))
                return result
            return SFTP_NO_SUCH_FILE
        except Exception as e:
            _logger.error("list_folder error: %s", e)
            return SFTP_NO_SUCH_FILE

    def stat(self, path):
        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE
        try:
            record.check_access("read")
            return self._attr(record, record_type, record.name)
        except Exception:
            return SFTP_NO_SUCH_FILE

    def lstat(self, path):
        return self.stat(path)

    def open(self, path, flags, attr):
        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE
        if record_type != "file":
            return SFTP_PERMISSION_DENIED

        try:
            if flags & (os.O_WRONLY | os.O_RDWR):
                record.check_access("write")
            else:
                record.check_access("read")
            return DmsSftpHandle(record, flags)
        except Exception:
            return SFTP_PERMISSION_DENIED

    def remove(self, path):
        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE
        if record_type != "file":
            return SFTP_PERMISSION_DENIED
        try:
            record.check_access("unlink")
            record.unlink()
            return SFTP_OK
        except Exception:
            return SFTP_PERMISSION_DENIED

    def rename(self, oldpath, newpath):
        record, record_type = self._resolve(oldpath)
        if record is None:
            return SFTP_NO_SUCH_FILE
        try:
            record.check_access("write")
            new_path_clean = newpath.strip("/")
            *new_dir_parts, new_name = new_path_clean.split("/")
            new_dir_path = "/" + "/".join(new_dir_parts) if new_dir_parts else "/"
            parent_record, parent_type = self._resolve(new_dir_path)
            if parent_record is None or parent_type not in ("storage", "directory"):
                return SFTP_PERMISSION_DENIED

            record.write({"name": new_name})
            if record_type == "file" and parent_type == "directory":
                record.write({"directory_id": parent_record.id})
            return SFTP_OK
        except Exception:
            return SFTP_PERMISSION_DENIED

    def mkdir(self, path, attr):
        path_clean = path.strip("/")
        *dir_parts, dir_name = path_clean.split("/")
        dir_path = "/" + "/".join(dir_parts) if dir_parts else "/"
        parent_record, parent_type = self._resolve(dir_path)
        if parent_record is None:
            return SFTP_NO_SUCH_FILE
        if parent_type not in ("storage", "directory"):
            return SFTP_PERMISSION_DENIED
        try:
            parent_record.check_access("create")
            if parent_type == "storage":
                self.env["dms.directory"].create({
                    "name": dir_name,
                    "storage_id": parent_record.id,
                    "is_root_directory": True,
                })
            else:
                self.env["dms.directory"].create({
                    "name": dir_name,
                    "parent_id": parent_record.id,
                })
            return SFTP_OK
        except Exception:
            return SFTP_PERMISSION_DENIED

    def rmdir(self, path):
        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE
        if record_type != "directory":
            return SFTP_PERMISSION_DENIED
        if record.child_directory_ids or record.file_ids:
            return SFTP_PERMISSION_DENIED
        try:
            record.check_access("unlink")
            record.unlink()
            return SFTP_OK
        except Exception:
            return SFTP_PERMISSION_DENIED

    def chattr(self, path, attr):
        return SFTP_OK

    def session_ended(self):
        self.env.cr.close()
        super().session_ended()


class DmsSftpSftpServer(SFTPServer):
    def start_subsystem(self, name, transport, channel):
        with api.Environment.manage():
            return super().start_subsystem(name, transport, channel)
