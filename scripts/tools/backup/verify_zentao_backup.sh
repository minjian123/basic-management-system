#!/usr/bin/env bash
# 验证禅道备份完整性（临时脚本）
set -uo pipefail
D=/mnt/data/backup/zentao
DBF=$(ls -t "$D"/zentao-db_*.sql.gz | head -1)
VOLF=$(ls -t "$D"/zentao-data_*.tar.gz | head -1)
echo "db file: $DBF"
echo "vol file: $VOLF"
echo "--- dump CREATE TABLE count:"
zcat "$DBF" | grep -c 'CREATE TABLE'
echo "--- actual table count (zentao schema):"
docker exec bms-mysql mysql -uzentao -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='zentao';" 2>/dev/null
echo "--- dump tail:"
zcat "$DBF" | tail -2
echo "--- vol entry count:"
tar -tzf "$VOLF" | wc -l
echo "--- vol key files (config/upload/extension/backup):"
tar -tzf "$VOLF" | grep -E 'zentao/config/my\.php|www/data/upload/$|extension/pkg/$|tmp/backup/' | head -8
echo "--- vol test (full read):"
tar -tzf "$VOLF" > /dev/null && echo TAR_OK
