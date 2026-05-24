#!/bin/sh
set -e

COUNT="${1:-10}"
OUTPUT="${2:-game_client/load_test/accounts.json}"

python manage.py seed_load_test_users --count "$COUNT" --output "$OUTPUT" --force
echo "Accounts saved to $OUTPUT"
