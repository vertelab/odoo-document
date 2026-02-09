#!/bin/bash
DBS=$(su - postgres -c "psql -At -c \"select datname from pg_database where datistemplate = false and datname != 'postgres' and datname != '';\" | paste -sd , -")
/usr/local/bin/sync_directory -d $DBS