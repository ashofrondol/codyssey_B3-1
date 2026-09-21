"""Mini Redis — 해시맵 / 이중 연결 리스트 / 최소 힙을 직접 구현한 인메모리 저장소.

계층:
    linked_list  ←  hashmap  ←  mini_redis  ←  cli
    protocol                 ←  mini_redis, cli   (결과 튜플의 종류 태그)

의존은 단방향이다. 자료구조 모듈(linked_list / hashmap / heap)은 애플리케이션
모듈(mini_redis / cli)을 import 하지 않는다.

여기서 재노출하는 것은 코어 API 뿐이다. `cli` 를 함께 끌어올리면 자료구조
하나만 쓰려는 코드까지 CLI 계층을 로드하게 되므로, REPL 은 `minredis.cli` 에서
직접 가져간다. 실행 진입점은 저장소 루트의 main.py 다.
"""

from .mini_redis import ERR_NOT_INTEGER, ERR_OOM, MiniRedis
from .protocol import ResultKind

__all__ = [
    'ERR_NOT_INTEGER',
    'ERR_OOM',
    'MiniRedis',
    'ResultKind',
]
