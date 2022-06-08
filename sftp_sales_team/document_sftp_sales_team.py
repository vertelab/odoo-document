from odoo.addons.document_sftp.document_sftp_sftp_server import DocumentSFTPSftpServerInterface

_super_is_initial_balance_enabled = DocumentSFTPSftpServerInterface.session_started


def session_started(self):
    print("working")
    self.env = self.env(cr=self.env.registry.cursor())

    return _super_is_initial_balance_enabled


DocumentSFTPSftpServerInterface.session_started = session_started
