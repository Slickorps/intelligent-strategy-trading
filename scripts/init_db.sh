#!/usr/bin/env bash
#
# init_db.sh — IST 数据库初始化脚本
#
# 用法:
#   ./scripts/init_db.sh              # 创建数据库和表
#   ./scripts/init_db.sh --reset      # 删除并重建数据库
#   ./scripts/init_db.sh --seed       # 初始化数据库并填充种子数据
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ─────────────────────────────────────
# 环境变量 (可通过 .env 覆盖)
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-ist_user}"
DB_PASS="${POSTGRES_PASSWORD:-ist_pass}"
DB_NAME="${POSTGRES_DB:-ist_trading}"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# ─────────────────────────────────────
# 加载 .env 文件 (如果存在)
if [ -f "$PROJECT_DIR/.env" ]; then
    # shellcheck source=/dev/null
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

# ─────────────────────────────────────
# 执行 SQL
run_sql() {
    PGPASSWORD="$DB_PASS" psql \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d postgres \
        -c "$1" 2>/dev/null || true
}

run_sql_target() {
    PGPASSWORD="$DB_PASS" psql \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        -f "$1"
}

# ─────────────────────────────────────
# 创建数据库
create_db() {
    echo -e "${GREEN}[INFO]${NC} 创建数据库: $DB_NAME"
    run_sql "CREATE DATABASE $DB_NAME;"
    echo -e "${GREEN}[INFO]${NC} 数据库创建完成"
}

# ─────────────────────────────────────
# 初始化表结构
init_tables() {
    echo -e "${GREEN}[INFO]${NC} 初始化表结构 ..."
    if [ -f "$PROJECT_DIR/init.sql" ]; then
        run_sql_target "$PROJECT_DIR/init.sql"
        echo -e "${GREEN}[INFO]${NC} 表结构初始化完成"
    else
        echo -e "${RED}[ERROR]${NC} 未找到 init.sql 文件"
        exit 1
    fi
}

# ─────────────────────────────────────
# 重置数据库
reset_db() {
    echo -e "${RED}[WARN]${NC} 删除并重建数据库: $DB_NAME"
    run_sql "DROP DATABASE IF EXISTS $DB_NAME;"
    create_db
    init_tables
}

# ─────────────────────────────────────
# 主入口
main() {
    local mode="${1:-init}"

    case "$mode" in
        --reset)
            reset_db
            ;;
        --seed)
            create_db
            init_tables
            echo -e "${GREEN}[INFO]${NC} 种子数据初始化 (暂无种子数据)"
            ;;
        init|*)
            create_db
            init_tables
            ;;
    esac

    echo -e "${GREEN}[INFO]${NC} 数据库初始化完成 ✓"
}

main "$@"