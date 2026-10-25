#!/bin/sh
# Keycloak 元数据库角色与库（bms-postgres 首次初始化新卷时自动执行；存量实例按《Keycloak 部署使用说明》手动执行一次）。
# 凭据经环境变量注入（compose base.yml 已把 KEYCLOAK_DB_PASSWORD 传入 postgres 容器）。
set -e
: "${KEYCLOAK_DB_PASSWORD:?需设置 KEYCLOAK_DB_PASSWORD（见 deploy/.env）}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
SELECT 'CREATE ROLE keycloak LOGIN PASSWORD ' || quote_literal('${KEYCLOAK_DB_PASSWORD}')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'keycloak')\gexec
SELECT 'CREATE DATABASE keycloak OWNER keycloak'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\gexec
EOSQL
