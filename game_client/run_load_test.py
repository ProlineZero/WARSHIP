"""
Точка входа нагрузочного теста.
Запуск из game_client:
  python run_load_test.py --players 10 --accounts load_test/accounts.json
"""
import sys

from load_test.runner import main

if __name__ == '__main__':
    sys.exit(main())
