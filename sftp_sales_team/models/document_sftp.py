import logging
import socket
import os
from io import StringIO, BytesIO
import threading
from odoo import SUPERUSER_ID, api, models
from odoo.modules.registry import Registry
from pathlib import Path
try:
    import paramiko
    from ..document_sftp_transport import DocumentSFTPTransport
    from ..document_sftp_server import DocumentSFTPServer
    from ..document_sftp_sftp_server import DocumentSFTPSftpServerInterface,\
        DocumentSFTPSftpServer
except ImportError:   # pragma: no cover
    pass
_db2thread = {}
_channels = []
_logger = logging.getLogger(__name__)


class DocumentSFTP(models.AbstractModel):
    _inherit = 'document.sftp'
    _description = 'SFTP server'

    def _get_sales_team(self):
        team_ids = self.env['crm.team'].search([])
        path = Path.home()
        SFTPClient = paramiko.sftp_client
        # print(Path.home())
        # paramiko.SFTP.mkdir()
        print(paramiko.SFTP.listdir_attr(paramiko.SFTPClient, path))

    def _mk_sale_team_dir(self, path):
        if path:
            try:
                sftp.chdir(remote_directory)  # sub-directory exists
            except IOError:
                dirname, basename = os.path.split(remote_directory.rstrip('/'))
                mkdir_p(sftp, dirname)  # make parent directories
                sftp.mkdir(basename)  # sub-directory missing, so created it
                sftp.chdir(basename)
                return True

    @api.model
    def __run_server(self, stop):
        # this is heavily inspired by
        # https://github.com/rspivak/sftpserver/blob/master/src/sftpserver
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        host, port = self.env['ir.config_parameter'].get_param(
            'document_sftp.bind', 'localhost:0'
        ).split(':')
        _logger.info('Binding to %s:%s', host, port)
        server_socket.bind((host, int(port)))
        host_real, port_real = server_socket.getsockname()
        _logger.info(
            'Listening to SFTP connections on %s:%s', host_real, port_real)
        if host_real != host or port_real != port:
            self.env['ir.config_parameter'].set_param(
                'document_sftp.bind', '%s:%s' % (host_real, port_real))
        server_socket.listen(5)
        server_socket.settimeout(2)

        print("====")
        self._get_sales_team()

        import pdb

        while not stop.is_set():
            try:
                conn, addr = server_socket.accept()
            except socket.timeout:
                while _channels and \
                        not _channels[0].get_transport().is_active():
                    _channels.pop(0)
                continue

            _logger.debug('Accepted connection from %s', addr)

            # ~ key = BytesIO(self.env['ir.config_parameter'].get_param('document_sftp.hostkey'))
            key = self.env['ir.config_parameter'].get_param('document_sftp.hostkey')
            host_key = paramiko.Ed25519Key.from_private_key(StringIO(key))

            transport = DocumentSFTPTransport(self.env.cr, conn)
            transport.add_server_key(host_key)
            transport.set_subsystem_handler(
                'sftp', DocumentSFTPSftpServer,
                DocumentSFTPSftpServerInterface, self.env)

            server = DocumentSFTPServer(self.env)
            try:
                transport.start_server(server=server)
                channel = transport.accept()
                if channel:
                    _channels.append(channel)
            except (paramiko.SSHException, EOFError):
                continue

