#!/bin/bash
# ローカルで PostgreSQL を使ったテストを実行するスクリプト
#
# 使い方:
#   ./scripts/test-with-db.sh          # 全テストを実行
#   ./scripts/test-with-db.sh -v       # verbose モードで実行
#   ./scripts/test-with-db.sh -k bump  # bump 関連のテストのみ実行

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# テスト用 PostgreSQL コンテナを起動
echo "Starting test PostgreSQL container..."
docker compose -f docker-compose.test.yml up -d

# PostgreSQL が準備完了するまで待機
echo "Waiting for PostgreSQL to be ready..."
until docker compose -f docker-compose.test.yml exec -T test-db pg_isready -U test_user -d discord_util_bot_test > /dev/null 2>&1; do
    sleep 1
done
echo "PostgreSQL is ready!"

# テスト実行
echo "Running tests..."
DISCORD_TOKEN=test-token \
TEST_DATABASE_URL=postgresql+asyncpg://test_user:test_pass@localhost:5432/discord_util_bot_test \
TEST_DATABASE_URL_SYNC=postgresql://test_user:test_pass@localhost:5432/discord_util_bot_test \
.venv/bin/python -m pytest "$@"

TEST_EXIT_CODE=$?

# コンテナを停止 (--keep オプションがない場合)
if [[ "$*" != *"--keep"* ]]; then
    echo "Stopping test PostgreSQL container..."
    docker compose -f docker-compose.test.yml down
fi

exit $TEST_EXIT_CODE
