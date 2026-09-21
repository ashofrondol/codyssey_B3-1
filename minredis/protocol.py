"""코어(MiniRedis)와 CLI 사이를 건너는 결과 튜플의 '종류' 태그.

모든 명령은 `(kind, ...)` 형태의 튜플을 돌려주고, CLI는 그 kind를 보고 출력
형식을 고른다. 이 kind를 양쪽이 각자 문자열 리터럴로 들고 있으면 약속을
지켜 주는 것이 아무것도 없다 — 코어가 `('interger', 3)`을 돌려줘도 파이썬은
아무 말이 없고, CLI는 그냥 '모르는 종류'로 흘려보낸다.

한 곳에 모아 두면 두 가지가 생긴다.
    (1) 양쪽이 같은 이름을 참조하므로 오타가 AttributeError로 즉시 드러난다.
    (2) 프로토콜의 전체 목록을 한 화면에서 읽을 수 있다 — 이전에는 이 목록의
        유일한 정의가 모듈 docstring이었고, 코드에는 리터럴만 흩어져 있었다.

`str`을 섞은 Enum이므로 값은 그대로 문자열이다. `ResultKind.OK == 'ok'`가
참이라 코어를 쓰는 쪽이 문자열을 기대해도 깨지지 않는다. `enum`은 표준
라이브러리이고 Python 3.8에서 동작하므로 과제 제약과 무관하다.
"""

from enum import Enum


class ResultKind(str, Enum):
    """결과 튜플의 첫 번째 원소. 주석은 튜플의 모양이다."""

    OK = 'ok'          # (OK,)                            -> "OK"
    NIL = 'nil'        # (NIL,)                           -> "(nil)"
    INT = 'int'        # (INT, n)                         -> "(integer) n"
    BULK = 'bulk'      # (BULK, s)                        -> "\"s\""
    ARRAY = 'array'    # (ARRAY, [key, ...])              -> 줄바꿈 구분 목록
    INFO = 'info'      # (INFO, used, maxmemory, evicted) -> INFO memory 3줄
    ERROR = 'error'    # (ERROR, message)                 -> "(error) message"
    EXIT = 'exit'      # (EXIT,)  — CLI 전용: REPL 종료 신호 (코어는 만들지 않는다)
