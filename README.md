# Mini Redis

Redis의 핵심 동작을 직접 구현해 본 CLI 기반 인메모리 키-값 저장소.
해시맵 · 이중 연결 리스트 · 최소 힙을 **밑바닥부터** 작성해
LRU 자동 제거와 TTL 만료가 어떻게 동작하는지 손으로 확인할 수 있다.

## 개발 환경

- Python 3.8 이상
- 표준 라이브러리만 사용 (`time`만 사용)
- **`dict` / `set` / `collections` 사용 금지** — 학습 목적상 직접 구현

## 실행 방법

```bash
python main.py
```

```text
mini-redis> SET user:1 "Alice"
OK
mini-redis> GET user:1
"Alice"
mini-redis> exit
```

## 파일 구조

| 파일                                 | 역할                                                          |
| ------------------------------------ | ------------------------------------------------------------- |
| [linked_list.py](linked_list.py)     | 이중 연결 리스트 (sentinel 기반, 모든 연산 O(1))              |
| [hashmap.py](hashmap.py)             | 해시맵 (FNV-1a 해시 + 체이닝, 로드 팩터 0.75에서 2배 확장)    |
| [heap.py](heap.py)                   | 최소 힙 (배열 기반, `_heapify_up` / `_heapify_down`)          |
| [mini_redis.py](mini_redis.py)       | 세 자료구조를 조합한 Mini Redis 코어 엔진                     |
| [main.py](main.py)                   | REPL 진입점, 토크나이저, 결과 포매터                          |

## 지원 명령어

### String 타입

| 명령                  | 설명                              | 출력 예시          |
| --------------------- | --------------------------------- | ------------------ |
| `SET key value`       | 키에 값 저장 (LRU 갱신)           | `OK`               |
| `GET key`             | 키 조회 (LRU 갱신)                | `"value"` / `(nil)`|
| `DEL key`             | 키 삭제                           | `(integer) 1`      |
| `EXISTS key`          | 키 존재 여부                      | `(integer) 0/1`    |
| `DBSIZE`              | 전체 키 개수                      | `(integer) N`      |
| `KEYS`                | 전체 키 목록                      | `1) "key1"` ...    |

### 메모리 관리

| 명령                          | 설명                                       |
| ----------------------------- | ------------------------------------------ |
| `CONFIG SET maxmemory <byte>` | 최대 메모리(바이트) 설정. 0은 무제한.      |
| `INFO memory`                 | `used_memory`, `maxmemory`, `evicted_keys` |

### TTL

| 명령                  | 설명                                                |
| --------------------- | --------------------------------------------------- |
| `EXPIRE key seconds`  | 만료 시간 설정 (0 이하면 즉시 삭제)                 |
| `TTL key`             | 남은 초. 키 없음=`-2`, 만료 없음=`-1`               |

### 기타

| 명령        | 설명         |
| ----------- | ------------ |
| `exit` / `quit` | REPL 종료 |

## 사용 예시

```text
mini-redis> CONFIG SET maxmemory 30
OK
mini-redis> SET user:1 "Alice"
OK
mini-redis> SET user:2 "Bob"
OK
mini-redis> SET user:3 "Charlie"
OK
mini-redis> GET user:1
(nil)
mini-redis> INFO memory
used_memory:22
maxmemory:30
evicted_keys:1
mini-redis> KEYS
1) "user:3"
2) "user:2"
mini-redis> EXPIRE user:2 3
(integer) 1
mini-redis> TTL user:2
(integer) 2
```

`maxmemory=30` 환경에서 세 번째 `SET`을 처리하는 순간 총 메모리가 33 바이트가 되어
가장 오래된 `user:1`(11 바이트)이 자동으로 제거된다 (`evicted_keys:1`).

## 자료구조 설명

### 1) 이중 연결 리스트 — LRU 추적용

- `prev` / `next` / `data` 세 필드를 가진 노드
- 앞/뒤 **sentinel 노드**를 두어 빈 리스트나 끝 노드 같은 경계 조건을 없앤다
- 외부에서 노드 참조를 들고 있으면 `remove_node` · `move_to_front` 모두 O(1)
- LRU 캐시에서 **앞쪽 = 가장 최근에 사용된 항목**(MRU), 뒤쪽 = LRU

### 2) 해시맵 — 메인 저장소

- **해시 함수**: FNV-1a (64비트). 문자열을 UTF-8 바이트로 변환 후
  ```
  h = (h XOR byte) * FNV_PRIME mod 2^64
  ```
- **충돌 해결**: 체이닝. 각 버킷이 이중 연결 리스트를 가짐
- **확장**: 로드 팩터(저장 키 수 / 버킷 수)가 **0.75를 넘으면 버킷 2배**,
  모든 키를 다시 배치(rehash)
- 버킷 테이블은 파이썬 `list`를 **고정 길이 인덱스 접근 배열**로만 사용

### 3) 최소 힙 — TTL 만료 관리용

- 완전 이진 트리를 1차원 배열로 표현
  - 부모: `(i - 1) // 2`, 자식: `2*i + 1`, `2*i + 2`
- `push` / `pop`은 트리 높이만큼만 비교/교환 → **O(log n)**
- `(expire_at, key)` 튜플을 넣어두면 항상 가장 먼저 만료될 키를 O(1)로 확인

## LRU 동작 흐름

1. `SET`이 들어오면 새 엔트리 크기를 미리 계산한다
2. 단일 엔트리가 `maxmemory`보다 크면 **저장하지 않고 OOM 에러**
3. 같은 키가 이미 있으면 먼저 제거 (덮어쓰기 시 TTL은 자연스럽게 초기화)
4. `used_memory + new_size > maxmemory`인 동안 LRU 리스트의 **맨 뒤** 키를 제거
   - `evicted_keys`를 1 증가
5. 새 엔트리를 LRU 리스트 **맨 앞**에 삽입하고 해시맵에 등록
6. `GET`이 성공하면 해당 노드를 `move_to_front`로 끌어올림 (만료 삭제는 갱신 안 함)

해시맵 엔트리에 LRU 노드 참조를 함께 보관하기 때문에
"이 키가 LRU 리스트 어디 있지?" 를 탐색할 필요가 없어서 모든 단계가 O(1).

## TTL 동작 흐름 (lazy deletion)

- `EXPIRE key seconds`가 들어오면 엔트리의 `expire_at`을 갱신하고
  `(expire_at, key)`를 힙에 push
- 같은 키에 다시 `EXPIRE`를 걸면 힙에는 **옛 항목이 그대로 남는다**
  (찾아서 삭제하면 O(n)이 되므로)
- 힙 정리는 `KEYS`/`DBSIZE`/`INFO memory` 호출 등에서 게으르게 수행:
  1. 힙 맨 앞을 `peek`
  2. `expire_at`이 미래이면 즉시 종료
  3. 만료된 항목은 `pop` 후 **현재 엔트리의 `expire_at`과 일치하는지** 확인
  4. 일치하지 않으면 stale 항목으로 보고 버리고 다음으로
- 개별 `GET`/`DEL`/`EXISTS`/`TTL` 시점에도 그 키만큼은 즉시 만료 검사를 수행

## 에러 표준

| 상황                | 출력                                                                |
| ------------------- | ------------------------------------------------------------------- |
| 모르는 명령         | `(error) ERR unknown command '<cmd>'`                               |
| 인자 개수 오류      | `(error) ERR wrong number of arguments for '<cmd>' command`         |
| 정수 파싱 실패      | `(error) ERR value is not an integer or out of range`               |
| 메모리 초과         | `(error) OOM command not allowed when used_memory > 'maxmemory'`    |

## 학습 체크포인트

이 과제를 마친 뒤 아래 질문에 스스로 답할 수 있어야 한다.

1. FNV-1a 해시는 충돌을 어떻게 줄이는가? 충돌이 났을 때 체이닝은 어떤 비용을 가지는가?
2. 해시맵 + 이중 연결 리스트 조합이 **왜 O(1) LRU**를 가능하게 하는가?
   (힌트: 해시맵으로 노드 참조를 곧장 찾으므로 리스트를 탐색할 필요가 없다)
3. 힙이 TTL 만료 관리에 적합한 이유는? 정렬된 리스트나 일반 큐로 했다면 무엇이 달라지나?
4. `maxmemory`를 초과한 순간부터 가장 오래된 키가 제거되는 전체 흐름을 설명할 수 있는가?
5. lazy deletion 전략의 장단점은? 어떤 상황에서 stale 힙 항목이 누적될 수 있는가?
