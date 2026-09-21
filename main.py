"""Mini Redis 실행 진입점.

구현은 minredis 패키지에 있다. 이 파일은 `python main.py` 라는 실행 경로를
그대로 유지하기 위한 얇은 shim이며, 여기에 로직을 두지 않는다.

사용 예:
    python main.py
    mini-redis> SET user:1 "Alice"
    OK
    mini-redis> GET user:1
    "Alice"
    mini-redis> exit
"""

from minredis.cli import repl

if __name__ == '__main__':
    repl()
