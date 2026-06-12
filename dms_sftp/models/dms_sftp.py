import logging
import socket
import threading
from io import StringIO

from odoo import api, models
from odoo.modules.registry import Registry
from odoo.service.server import server

try:
    import paramiko
    from ..sftp.transport import DmsSftpTransport
    from ..sftp.server import DmsSftpServer
    from ..sftp.sftp_server import DmsSftpSftpServer, DmsSftpSftpServerInterface
except ImportError:
    pass

_logger = logging.getLogger(__name__)

_db2thread = {}
_channels = []


class DmsSftp(models.AbstractModel):
    _name = "dms.sftp"
    _description = "DMS SFTP Server"

    def _run_server(self, dbname, stop):
        db_registry = Registry.new(dbname)
        with db_registry.cursor() as cr:
            env = api.Environment(cr, 1, {})
            env[self._name].__run_server(stop)

    @api.model
    def __run_server(self, stop):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        host, port = self.env["ir.config_parameter"].get_param(
            "dms_sftp.bind", "localhost:2222"
        ).split(":")
        _logger.info("SFTP binding to %s:%s", host, port)
        server_socket.bind((host, int(port)))
        server_socket.listen(5)
        server_socket.settimeout(2)

        while not stop.is_set():
            try:
                conn, addr = server_socket.accept()
            except socket.timeout:
                while _channels and not _channels[0].get_transport().is_active():
                    _channels.pop(0)
                continue

            key = self.env["ir.config_parameter"].get_param("dms_sftp.hostkey")
            host_key = paramiko.ECDSAKey.from_private_key(StringIO(key))

            transport = DmsSftpTransport(self.env.cr.dbname, conn)
            transport.add_server_key(host_key)
            transport.set_subsystem_handler(
                "sftp", DmsSftpSftpServer, DmsSftpSftpServerInterface, self.env.cr.dbname
            )
            server = DmsSftpServer(self.env.cr.dbname)
            try:
                transport.start_server(server=server)
                channel = transport.accept()
                if channel:
                    _channels.append(channel)
            except (paramiko.SSHException, EOFError):
                continue

    def _register_hook(self):
        cr = self._cr
        if cr.dbname not in _db2thread:
            stop = threading.Event()
            _db2thread[cr.dbname] = (
                threading.Thread(target=self._run_server, args=(cr.dbname, stop)),
                stop,
            )
            _db2thread[cr.dbname][0].start()
            old_stop = server.stop

            def new_stop():
                stop.set()
                old_stop()

            server.stop = new_stop
        return super()._register_hook()
