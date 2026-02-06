#!/usr/bin/env python3
import argparse
import base64
import logging
import multiprocessing
import pwd
import grp
import os
import time
import re
import signal
import hashlib
from datetime import datetime, timedelta
import stat
import traceback
import threading
import shutil
from configparser import ConfigParser
import inotify.adapters
import inotify.constants
from odoorpc import ODOO
from odoorpc.error import RPCError
import urllib.error


# Loggningskonfiguration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/odoo/sync_directory.log'),
        logging.StreamHandler()
    ]
)

def read_admin_password():
    config = ConfigParser()
    config.read('/etc/odoo/odoo.conf')
    return config.get('options', 'admin_passwd')

def get_all_databases():
    """TODO: to be used later"""
    try:
        odoo = ODOO('localhost', port=8069)
        databases = odoo.db.list()
        return databases
    except Exception as e:
        logging.error(f'Failed to get databases from Odoo: {e}')
        return []

def connect_to_odoo(database):
    admin_password = read_admin_password()

    for password in [admin_password, 'admin']:
        try:
            odoo = ODOO('localhost', port=8069)
            odoo.login(database, 'admin', password)
            return odoo
        except (RPCError, urllib.error.HTTPError) as e:
            logging.debug(f'Misslyckades ansluta till {database}: {e}')
            continue
            
    return None

_recently_synced = {}
_lock = threading.Lock()
SYNC_COOLDOWN = 15

def mark_as_synced(checksum, source):
    with _lock:
        _recently_synced[checksum] = {
            'source': source,
            'timestamp': time.time()
        }

def is_recently_synced(checksum):
    with _lock:
        if checksum not in _recently_synced:
            return False

        entry = _recently_synced[checksum]
        if time.time() - entry['timestamp'] > SYNC_COOLDOWN:
            del _recently_synced[checksum]
            return False
        
        return True

def calculate_file_checksum(filepath):
    sha1 = hashlib.sha1()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(65536):
                sha1.update(chunk)
        return sha1.hexdigest()
    except OSError:
        return None

def ensure_permissions(path):
    try:
        shutil.chown(path, user='odoo', group='odoo')
        mode = 0o2775 if os.path.isdir(path) else 0o664
        os.chmod(path, mode)

    except Exception as e:
        logging.warning(f"Tillståndssynkning misslyckades för {path}, kör du som sudo?: {e}")

def parse_datetime(odoo_datetime_str):
    return datetime.strptime(odoo_datetime_str, '%Y-%m-%d %H:%M:%S')

def poll_odoo_changes(odoo, directory_id, local_path):
    DmsFile = odoo.env['dms.file']

    odoo_files = DmsFile.search_read(
        [('directory_id', '=', directory_id)],
        ['id', 'name', 'checksum', 'write_date', 'storage_path']   
    )

    odoo_by_checksum = {f['checksum']: f for f in odoo_files}
    local_by_checksum = {}
    
    for filename in os.listdir(local_path):
        full_path = os.path.join(local_path, filename)
        if os.path.isfile(full_path):
            checksum = calculate_file_checksum(full_path)
            local_by_checksum[checksum] = {"filename": filename, "mtime": os.path.getmtime(full_path)}
    
    odoo_keys = set(odoo_by_checksum.keys())
    local_keys = set(local_by_checksum.keys())

    for checksum in odoo_keys & local_keys:
        odoo_info = odoo_by_checksum[checksum]
        local_info = local_by_checksum[checksum]
        if odoo_info['name'] != local_info['filename']:
            sync_rename(odoo, checksum, odoo_info, local_info, local_path)

    for checksum in odoo_keys - local_keys:
        handle_new_from_odoo(odoo, odoo_by_checksum[checksum], local_path)

    for checksum in local_keys - odoo_keys:
        local_info = local_by_checksum[checksum]
        filename = local_info['filename']
        full_path = os.path.join(local_path, filename)
        file_age = time.time() - local_info['mtime']
        if file_age < SYNC_COOLDOWN * 2:
            logging.debug(f"Fil '{filename}' är ny lokalt ({file_age:.0f}s), väntar.")
            continue
        logging.info(f"Fil '{filename}' finns lokalt men inte i Odoo-katalog {directory_id}, raderar lokalt.")
        os.remove(full_path)



def sync_rename(odoo, checksum, odoo_info, local_info, local_path):
    DmsFile = odoo.env['dms.file']
    odoo_name = odoo_info['name']
    local_name = local_info['filename']
    odoo_time = parse_datetime(odoo_info['write_date'])
    local_time = datetime.fromtimestamp(local_info['mtime'])

    if is_recently_synced(checksum):
        return
    
    if odoo_time > local_time:
        old_path = os.path.join(local_path, local_name)
        new_path = os.path.join(local_path, odoo_name)
        
        mark_as_synced(checksum, "odoo")
        os.rename(old_path, new_path)
        ensure_permissions(new_path)

        new_storage_path = odoo_info.get('storage_path', '').rsplit('/', 1)[0]
        if new_storage_path:
            new_storage_path = f"{new_storage_path}/{odoo_name}"
        else:
            new_storage_path = odoo_name
        DmsFile.write([odoo_info['id']], {'storage_path': new_storage_path})
    
    else:
        mark_as_synced(checksum, "local")

        new_storage_path = odoo_info.get('storage_path', '').rsplit('/', 1)[0]
        if new_storage_path:
            new_storage_path = f"{new_storage_path}/{local_name}"
        else:
            new_storage_path = local_name
        DmsFile.write([odoo_info['id']], {'name': local_name, 'storage_path': new_storage_path})

def delete_file_in_odoo(dms_model, file_id, filename):
    try:
        dms_model.unlink([file_id])

    except Exception as e:
        logging.error(f"Kunde inte radera '{filename}': {e}")

def upload_file_to_odoo(dms_model, directory_id, filename, full_path, existing_record=None):
    local_checksum = calculate_file_checksum(full_path)
    if not local_checksum:
        return

    if existing_record and existing_record.get('checksum') == local_checksum:
        return

    mark_as_synced(local_checksum, "local_upload")

    try:
        with open(full_path, "rb") as f:
            b64_content = base64.b64encode(f.read()).decode('utf-8')
            vals = {'content': b64_content}

            if existing_record:
                dms_model.write([existing_record['id']], vals)
            else:
                vals.update({
                'name': filename,
                'directory_id': directory_id
            })
            dms_model.create(vals)
    
    except Exception as e:
        logging.info(f"Misslyckades med uppladdning för '{filename}': {e}")

def handle_local_delete(dms_model, directory_id, existing_record, filename, dir_path, full_path):
    if not existing_record:
        return

    odoo_checksum = existing_record.get('checksum')
    if odoo_checksum:
        for local_file in os.listdir(dir_path):
            local_path = os.path.join(dir_path, local_file)
            if os.path.isfile(local_path):
                local_checksum = calculate_file_checksum(local_path)
                
                if local_checksum == odoo_checksum:
                    new_name_files = dms_model.search_read(
                        [('directory_id', '=', directory_id), ('name', '=', local_file)],
                        ['id', 'checksum']
                    )
                    
                    if new_name_files and new_name_files[0].get('checksum') == local_checksum:
                        dms_model.unlink([existing_record['id']])
                    else:
                        old_storage_path = existing_record.get('storage_path', '') or ''
                        base = old_storage_path.rsplit('/', 1)[0]
                        new_storage_path = f"{base}/{local_file}" if base and '/' in old_storage_path else local_file
                        
                        dms_model.write([existing_record['id']], {
                            'name': local_file,
                            'storage_path': new_storage_path
                        })
                    
                    mark_as_synced(local_checksum, "local")
                    return
        mark_as_synced(odoo_checksum, "local_delete")
    delete_file_in_odoo(dms_model, existing_record['id'], filename)

def handle_sync_event(odoo, mapped_directories, dir_path, filename, operation):
    if filename.startswith('.') or filename.endswith(('~', '.tmp')):
        return

    full_path = os.path.join(dir_path, filename)

    if os.path.exists(full_path):
        checksum = calculate_file_checksum(full_path)
        if is_recently_synced(checksum):
            return

    directory_id = next(
        (item['directory_id'] for item in mapped_directories if item['full_path'] == dir_path),
        None
    )

    if not directory_id:
        return
    
    try:
        DmsFile = odoo.env['dms.file']
        existing_files = DmsFile.search_read(
            [('directory_id', '=', directory_id), ('name', '=', filename)],
            ['id', 'checksum', 'storage_path']
        )

        existing_record = existing_files[0] if existing_files else None

        if operation == 'delete':
            handle_local_delete(DmsFile, directory_id, existing_record, filename, dir_path, full_path)
            return


        upload_file_to_odoo(DmsFile, directory_id, filename, full_path, existing_record)

    except Exception as e:
        logging.error(f"Oväntat fel i handle_sync_event för '{filename}': {e}")
        logging.error(traceback.format_exc())


def handle_new_from_odoo(odoo, odoo_file, local_path):
    DmsFile = odoo.env['dms.file']

    checksum = odoo_file['checksum']

    if is_recently_synced(checksum):
        return

    filename = odoo_file['name']
    file_id = odoo_file['id']

    content_b64 = DmsFile.read([file_id], ['content'])[0]['content']
    content = base64.b64decode(content_b64)

    full_path = os.path.join(local_path, filename)

    mark_as_synced(checksum, "odoo")
    with open(full_path, 'wb') as f:
        f.write(content)

    ensure_permissions(full_path)

def get_directories_for_storage(odoo, fs_storage_id):
    fs_storage_record = odoo.env['fs.storage'].browse(fs_storage_id)
    storage_ids = odoo.env['dms.storage'].search([('storage_backend_id', '=', fs_storage_id)])

    if not storage_ids:
        return []

    directory_ids = odoo.env['dms.directory'].search([('storage_id', 'in', storage_ids)])
    dms_directories = odoo.env['dms.directory'].browse(directory_ids)

    mapped_directories = []
    fs_root = fs_storage_record.directory_path or ""

    if fs_root and not fs_root.startswith('/'):
        fs_root = '/' + fs_root

    for directory in dms_directories:
        relative_path = directory.complete_name.lstrip('/')
        full_path = os.path.join(fs_root, relative_path)
        
        if not os.path.exists(full_path):
            logging.warning(f"DEBUG: Hittar ej sökväg: '{full_path}'")
        
        if os.path.exists(full_path):
            ensure_permissions(full_path)
            mapped_directories.append({
                'directory_id': directory.id,
                'full_path': full_path
            })
            
    return mapped_directories

def polling_loop(odoo, mapped_directories):
    while True:
        try:
            for item in mapped_directories:
                poll_odoo_changes(odoo, item['directory_id'], item['full_path'])

        except Exception as e:
            logging.error(f"Polling error: {e}")
        
        time.sleep(15)

def setup_inotify_watches(mapped_directories):
    i = inotify.adapters.Inotify()
    mask = (inotify.constants.IN_CLOSE_WRITE | 
            inotify.constants.IN_ISDIR | 
            inotify.constants.IN_MOVED_TO | 
            inotify.constants.IN_CREATE | 
            inotify.constants.IN_MOVED_FROM | 
            inotify.constants.IN_DELETE)

    for item in mapped_directories:
        path = item['full_path']
        try:
            i.add_watch(path, mask=mask)
        except Exception as e:
            logging.error(f"Kunde inte bevaka {path}: {e}")

    return i

def process_inotify_event(odoo, mapped_directories, event):
    header, type_names, watch_path, filename = event

    dir_path = watch_path.decode('utf-8') if isinstance(watch_path, bytes) else watch_path
    filename_str = filename.decode('utf-8') if isinstance(filename, bytes) else filename
    full_path = os.path.join(dir_path, filename_str)
    operation = ""

    if 'IN_ISDIR' in type_names:
        return

    if 'IN_DELETE' in type_names or 'IN_MOVED_FROM' in type_names:
        operation = 'delete'

    else:
        ensure_permissions(full_path)

    handle_sync_event(odoo, mapped_directories, dir_path, filename_str, operation=operation)

def watch_directory(database, fs_storage_id, mapped_directories):
    odoo = connect_to_odoo(database)

    if not odoo:
        return

    poll_thread = threading.Thread(
        target=polling_loop,
        args=(odoo, mapped_directories),
        daemon=True
    )
    poll_thread.start()

    inotify_adapter = setup_inotify_watches(mapped_directories)

    try:
        for event in inotify_adapter.event_gen(yield_nones=False):
            process_inotify_event(odoo, mapped_directories, event)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"Krasch i loopen för storage {fs_storage_id}: {e}")
        logging.error(traceback.format_exc())   


def main():
    os.umask(0o002)
    parser = argparse.ArgumentParser(description='Odoo Database Watcher')
    parser.add_argument('-d', '--db', required=True, help='Comma separated list od Odoo Databases')
    args = parser.parse_args()

    processes = []
    databases = [name.strip() for name in args.db.split(',')]

    for database in databases:
        odoo = connect_to_odoo(database)

        if not odoo:
            continue

        installed = odoo.env['ir.module.module'].search([
            ('name', 'in', ['fs_storage', 'storage_backend']), 
            ('state', '=', 'installed')
        ])
        if len(installed) < 2:
            continue

        try:
            fs_storages = odoo.env['fs.storage'].search([('protocol', 'in', ('dir', 'file'))])

            for fs_id in fs_storages:
                mapped_directories = get_directories_for_storage(odoo, fs_id)
                if mapped_directories:
                    p = multiprocessing.Process(
                        target=watch_directory,
                        args=(database, fs_id, mapped_directories)
                    )
                    p.start()
                    processes.append(p)
                else:
                    logging.warning(f"FS Storage ID {fs_id} p {database} saknar kopplade kataloger eller path. Ingen bevakning startad.")
        except Exception as e:
            logging.error(f"Fel vid uppstart av {database}: {e}")
            logging.error(traceback.format_exc())

    logging.info(f"Alla processer startade.")

    try:
        while True:
            pass
    except KeyboardInterrupt:
        logging.info("Avslutar scriptet...")
        # Avsluta alla processer
        for p in processes:
            os.kill(p.pid, signal.SIGTERM)
        # Vänta på att alla processer ska avslutas
        for p in processes:
            p.join()
        logging.info("Klar.")
 
if __name__ == '__main__':
    main()