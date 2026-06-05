from odoo import api, SUPERUSER_ID

try:
    from paramiko import Transport
    from paramiko.transport import DEFAULT_WINDOW_SIZE, DEFAULT_MAX_PACKET_SIZE
except ImportError:
    pass


class DmsSftpTransport(Transport):
    def __init__(
        self, cr, sock, default_window_size=DEFAULT_WINDOW_SIZE,
        default_max_packet_size=DEFAULT_MAX_PACKET_SIZE, gss_kex=False,
        gss_deleg_creds=True
    ):
        self.cr = cr
        super().__init__(
            sock, default_window_size=default_window_size,
            default_max_packet_size=default_max_packet_size,
            gss_kex=gss_kex, gss_deleg_creds=gss_deleg_creds,
        )

    def run(self):
        with api.Environment.manage():
            self.env = api.Environment(self.cr, SUPERUSER_ID, {})
            result = super().run()
        return result
