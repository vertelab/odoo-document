from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry

try:
    from paramiko import Transport
    from paramiko.transport import DEFAULT_WINDOW_SIZE, DEFAULT_MAX_PACKET_SIZE
except ImportError:
    pass


class DmsSftpTransport(Transport):
    def __init__(
        self, dbname, sock, default_window_size=DEFAULT_WINDOW_SIZE,
        default_max_packet_size=DEFAULT_MAX_PACKET_SIZE,
    ):
        self.dbname = dbname
        super().__init__(
            sock, default_window_size=default_window_size,
            default_max_packet_size=default_max_packet_size,
        )

    def run(self):
        db_registry = Registry.new(self.dbname)
        with db_registry.cursor() as cr:
            self.env = api.Environment(cr, SUPERUSER_ID, {})
            result = super().run()
        return result
