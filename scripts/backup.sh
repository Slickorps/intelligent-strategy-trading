#!/usr/bin/env bash
#
# backup.sh — IST 数据备份脚本
#
# 用法:
#   ./scripts/backup.sh              # 备份 data/ 和 config/ 目录
#   ./scripts/backup.sh --db-only    # 仅备份数据库
#   ./scripts/backup.sh --remote     # 备份并上传到远程存储
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE_NAME="ist_backup_${TIMESTAMP}.tar.gz"

# ─────────────────────────────────────
# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ─────────────────────────────────────
# 确保备份目录存在
ensure_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        log_info "创建备份目录: $BACKUP_DIR"
    fi
}

# ─────────────────────────────────────
# 备份数据文件和配置
backup_files() {
    log_info "开始备份数据文件和配置 ..."

    local tmpdir
    tmpdir=$(mktemp -d)
    trap 'rm -rf $tmpdir' EXIT

    # 复制需要备份的目录
    if [ -d "$PROJECT_DIR/data" ]; then
        cp -r "$PROJECT_DIR/data" "$tmpdir/data"
    fi

    if [ -d "$PROJECT_DIR/config" ]; then
        cp -r "$PROJECT_DIR/config" "$tmpdir/config"
    fi

    if [ -d "$PROJECT_DIR/logs" ]; then
        cp -r "$PROJECT_DIR/logs" "$tmpdir/logs"
    fi

    # 打包
    cd "$tmpdir" && tar -czf "$BACKUP_DIR/$ARCHIVE_NAME" .
    log_info "备份完成: $BACKUP_DIR/$ARCHIVE_NAME"
    log_info "备份大小: $(du -h "$BACKUP_DIR/$ARCHIVE_NAME" | cut -f1)"
}

# ─────────────────────────────────────
# 备份数据库 (PostgreSQL)
backup_db() {
    log_info "开始备份数据库 ..."

    local DB_NAME="${POSTGRES_DB:-ist_trading}"
    local DB_USER="${POSTGRES_USER:-ist_user}"
    local DB_HOST="${POSTGRES_HOST:-localhost}"
    local DB_PORT="${POSTGRES_PORT:-5432}"

    local DB_BACKUP="ist_db_${TIMESTAMP}.sql.gz"

    if command -v pg_dump &> /dev/null; then
        PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump \
            -h "$DB_HOST" \
            -p "$DB_PORT" \
            -U "$DB_USER" \
            -d "$DB_NAME" \
            | gzip > "$BACKUP_DIR/$DB_BACKUP"
        log_info "数据库备份完成: $BACKUP_DIR/$DB_BACKUP"
    else
        log_warn "pg_dump 未安装，跳过数据库备份"
    fi
}

# ─────────────────────────────────────
# 清理旧备份 (保留最近 7 天)
cleanup_old() {
    log_info "清理 7 天前的旧备份 ..."
    find "$BACKUP_DIR" -name "ist_backup_*.tar.gz" -mtime +7 -delete 2>/dev/null || true
    find "$BACKUP_DIR" -name "ist_db_*.sql.gz"    -mtime +7 -delete 2>/dev/null || true
    log_info "旧备份清理完成"
}

# ─────────────────────────────────────
# 主入口
main() {
    local mode="${1:-full}"

    ensure_dir

    case "$mode" in
        --db-only)
            backup_db
            ;;
        --remote)
            backup_files
            backup_db
            log_info "上传到远程存储 (未实现 — 请配置 S3/rsync 目标)"
            ;;
        full|*)
            backup_files
            backup_db
            cleanup_old
            ;;
    esac

    log_info "全部备份操作完成 ✓"
}

main "$@"