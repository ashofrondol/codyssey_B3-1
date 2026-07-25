# Mini Redis

Redis의 핵심 동작을 직접 구현해 본 CLI 기반 인메모리 키-값 저장소.
해시맵 · 이중 연결 리스트 · 최소 힙을 **밑바닥부터** 작성해
LRU 자동 제거와 TTL 만료가 어떻게 동작하는지 손으로 확인할 수 있다.

## 개발 환경

- Python 3.8 이상 (3.9+ 전용 문법 미사용)
- 표준 라이브러리만 사용 (`time`, `re`, 테스트에 `unittest`)
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

### 테스트

```bash
python -m unittest discover -s tests -t . -v
```

시계를 주입(`MiniRedis(now_fn=...)`)하기 때문에 TTL 테스트도 `sleep` 없이
결정적으로 돌아간다. 전체 105개 테스트가 0.5초 안에 끝난다.
`tests/test_cli.py`의 `TestConstraints`가 AST로 전 파일을 훑어
`dict`/`set`/`collections` 사용과 3.9+ 문법을 스스로 검사하므로,
과제 제약 위반은 테스트 실패로 바로 드러난다.

## 파일 구조

| 파일                                 | 역할                                                          |
| ------------------------------------ | ------------------------------------------------------------- |
| [linked_list.py](linked_list.py)     | 이중 연결 리스트 (sentinel 기반, 모든 연산 O(1))              |
| [hashmap.py](hashmap.py)             | 해시맵 (FNV-1a 해시 + 체이닝, 로드 팩터에 따른 2배 확장/축소) |
| [heap.py](heap.py)                   | 최소 힙 (배열 기반, `_heapify_up` / `_heapify_down`)          |
| [mini_redis.py](mini_redis.py)       | 세 자료구조를 조합한 Mini Redis 코어 엔진                     |
| [main.py](main.py)                   | REPL 진입점, 토크나이저, 디스패처, 결과 포매터                |
| [tests/](tests/)                     | 단위·회귀 테스트 (자료구조 3종 + 코어 + CLI)                  |

의존 방향은 단방향이다: `main → mini_redis → {hashmap → linked_list, heap, linked_list}`.
자료구조 모듈은 애플리케이션 로직을 import 하지 않는다.

## 지원 명령어

### String 타입

| 명령                  | 설명                              | 출력 예시          |
| --------------------- | --------------------------------- | ------------------ |
| `SET key value`       | 키에 값 저장 (LRU 갱신, TTL 초기화) | `OK`             |
| `GET key`             | 키 조회 (성공 시에만 LRU 갱신)    | `"value"` / `(nil)`|
| `DEL key`             | 키 삭제                           | `(integer) 1/0`    |
| `EXISTS key`          | 키 존재 여부                      | `(integer) 1/0`    |
| `DBSIZE`              | 전체 키 개수 (인자 없음)          | `(integer) N`      |
| `KEYS`                | 전체 키 목록 (**인자 없음**)      | `1) "key1"` ...    |

### 메모리 관리

| 명령                          | 설명                                       |
| ----------------------------- | ------------------------------------------ |
| `CONFIG SET maxmemory <byte>` | 최대 메모리(바이트) 설정. 0은 무제한.      |
| `INFO memory`                 | `used_memory`, `maxmemory`, `evicted_keys` |

### TTL

| 명령                  | 설명                                                |
| --------------------- | --------------------------------------------------- |
| `EXPIRE key seconds`  | 만료 시간 설정 (0 이하면 즉시 삭제 후 `1`)          |
| `TTL key`             | 남은 초. 키 없음=`-2`, 만료 없음=`-1`               |

### 기타

| 명령            | 설명      |
| --------------- | --------- |
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

> **KEYS 출력 순서에 의존하지 말 것.** 해시 버킷 순회 순서라서 삽입 순서도
> 정렬 순서도 아니다. 위 예시의 `user:3` → `user:2` 순서는 우연이다.
>
> **`TTL user:2`의 값은 호출 간격에 따라 2 또는 3이다.** 남은 시간을 내림(floor)
> 하므로, 두 명령이 같은 타이머 틱 안에서 실행되면 3이 나온다(Windows의
> `time.time()`은 해상도가 낮아 실제로 자주 그렇다). 대화형으로 한 줄씩 치면
> 2가 나온다. 자세한 규칙은 아래 "명세 해석 규칙" 3번 참고.

## 자료구조 설명

### 1) 이중 연결 리스트 — LRU 추적용

- `prev` / `next` / `data` 세 필드를 가진 노드
- 앞/뒤 **sentinel 노드**를 두어 빈 리스트나 끝 노드 같은 경계 조건을 없앤다
- 외부에서 노드 참조를 들고 있으면 `remove_node` · `move_to_front` 모두 O(1)
- LRU 캐시에서 **앞쪽 = 가장 최근에 사용된 항목**(MRU), 뒤쪽 = LRU
- 각 노드는 자신이 속한 리스트를 `owner`로 들고 있다. 이미 제거된 노드나
  다른 리스트의 노드를 넘겨도 크래시나 `_size` 손상 없이 무시된다
  (독립 모듈로 재사용되는 자료구조이므로 호출 계약을 스스로 방어한다)

### 2) 해시맵 — 메인 저장소

- **해시 함수**: FNV-1a (64비트). 문자열을 UTF-8 바이트로 변환 후
  ```
  h = (h XOR byte) * FNV_PRIME mod 2^64
  ```
  이렇게 얻은 64비트 해시값을 `% capacity`로 접어 버킷 인덱스를 만든다
- **충돌 해결**: 체이닝. 각 버킷이 이중 연결 리스트를 가짐
- **확장**: 로드 팩터(저장 키 수 / 버킷 수)가 **0.75를 넘으면 버킷 2배**,
  모든 키를 다시 배치(rehash). capacity 8이면 6개까지는 그대로, 7번째 삽입에서 확장
- **축소**: 로드 팩터가 **0.1875 아래로 떨어지면 절반**으로 줄인다.
  축소 임계를 확장 임계의 1/4로 잡아서 "축소 → 즉시 재확장" 진동이 생기지 않는다
  (축소 직후 로드 팩터는 0.375 미만이라 확장 임계 0.75의 절반)
- 버킷 테이블은 파이썬 `list`를 **고정 길이 인덱스 접근 배열**로만 사용

### 3) 최소 힙 — TTL 만료 관리용

- 완전 이진 트리를 1차원 배열로 표현
  - 부모: `(i - 1) // 2`, 자식: `2*i + 1`, `2*i + 2`
- `push` / `pop`은 트리 높이만큼만 비교/교환 → **O(log n)**
- `(expire_at, key)` 튜플을 넣어두면 항상 가장 먼저 만료될 키를 O(1)로 확인
- 만료 시각이 같으면 튜플 비교가 두 번째 요소(키 문자열)로 넘어간다 —
  순서만 갈릴 뿐 정확성에는 영향이 없다

## LRU 동작 흐름

1. `SET`이 들어오면 새 엔트리 크기를 미리 계산한다
2. 단일 엔트리가 `maxmemory`보다 크면 **아무것도 바꾸지 않고 OOM 에러**
   (축출을 시도하지 않으므로 기존 키·값·TTL과 `evicted_keys`가 전부 보존된다)
3. 같은 키가 이미 있으면 먼저 제거 (덮어쓰기 시 TTL은 자연스럽게 초기화)
4. **만료된 키를 먼저 회수한다** (아래 참고)
5. `used_memory + new_size > maxmemory`인 동안 LRU 리스트의 **맨 뒤** 키를 제거
   - `evicted_keys`를 1 증가
6. 새 엔트리를 LRU 리스트 **맨 앞**에 삽입하고 해시맵에 등록
7. `GET`이 성공하면 해당 노드를 `move_to_front`로 끌어올림 (만료 삭제는 갱신 안 함)
8. `CONFIG SET maxmemory`로 한도를 낮춰 현재 사용량을 밑돌면, `OK`를 돌려주기
   전에 그 자리에서 4~5단계를 수행한다

해시맵 엔트리에 LRU 노드 참조를 함께 보관하기 때문에
"이 키가 LRU 리스트 어디 있지?" 를 탐색할 필요가 없어서 모든 단계가 O(1).

> **4단계가 왜 필요한가.** 만료됐지만 아직 회수되지 않은 키는 `used_memory`를
> 점유한 채 LRU 리스트에도 남아 있다. 이 상태로 축출을 시작하면
> (1) 필요 없는 축출이 촉발되고 (2) **죽은 키 대신 살아있는 키가 희생되며**
> (3) 그 삭제가 `evicted_keys`에 잘못 집계된다. 그래서 `_evict_to_fit`은
> 희생자를 고르기 전에 항상 `_purge_expired_via_heap()`을 먼저 부른다.
>
> **단, `maxmemory <= 0` 가드보다 뒤에 둔다.** 무제한 모드에서는 축출 자체가
> 없어 만료 회수가 어차피 필요 없는데, 가드보다 앞에 두면 무제한 `SET` 한 번이
> "그동안 만료된 키 전부"를 떠안아 통째로 멈춘다(만료 키 5만 개 기준 약 1.5초
> 측정). 무제한 모드의 회수는 `DBSIZE`/`KEYS`/`INFO`가 맡고, 힙 상한은
> `EXPIRE`의 컴팩션이 지키므로 관측되는 동작은 달라지지 않는다.
> 제한 모드에서는 회수량이 "`maxmemory` 안에 들어갈 수 있는 키 수"로
> 자연히 상한이 잡힌다.
>
> 이 트레이드오프가 lazy deletion의 본질이다. 실제 Redis는 **회수 예산 상한을
> 둔 주기적 active expire cycle**을 백그라운드로 돌려, 접근이 없어도 만료 키를
> 조금씩 회수하면서 단일 명령 지연을 억제한다. (체크리스트 4절 문항)

## TTL 동작 흐름 (lazy deletion + 컴팩션)

- `EXPIRE key seconds`가 들어오면 엔트리의 `expire_at`을 갱신하고
  `(expire_at, key)`를 힙에 push
- 같은 키에 다시 `EXPIRE`를 걸면 힙에는 **옛 항목이 그대로 남는다**
  (찾아서 삭제하면 O(n)이 되므로)
- 힙 정리는 `SET` / `CONFIG SET` / `KEYS` / `DBSIZE` / `INFO memory`에서
  게으르게 수행:
  1. 힙 맨 앞을 `peek`
  2. `expire_at`이 미래이면 즉시 종료 (만료 항목이 없으면 비용은 사실상 0)
  3. 만료된 항목은 `pop` 후 **현재 엔트리의 `expire_at`과 일치하는지** 확인
  4. 일치하지 않으면 stale 항목으로 보고 버리고 다음으로
- 개별 `GET`/`DEL`/`EXISTS`/`TTL` 시점에도 그 키만큼은 즉시 만료 검사를 수행
- **컴팩션**: 힙 크기가 임계를 넘으면 살아있는 엔트리만으로 힙을 재구축한다.
  이게 없으면 같은 키에 `EXPIRE`를 반복하거나 TTL이 걸린 키를 `DEL`할 때
  아무도 회수하지 않는 항목이 무한정 쌓인다(만료 시각이 먼 미래면 3단계가
  손도 못 댄다). 재구축 사이에 힙이 최소 2배로 벌어져야 하므로 상각 비용은
  push당 O(log n)에 머문다
  - 임계는 `max(32, 2 × 직전 재구축에서 살아남은 TTL 항목 수)`다. **전체 키
    수가 아니라 TTL이 걸린 키 수**를 기준으로 잡아야, TTL 없는 키가 대다수인
    저장소에서 상한이 필요 이상으로 커지지 않는다
  - 컴팩션 검사는 **힙이 커지는 유일한 지점인 `EXPIRE`에서도** 수행한다.
    purge 계열 명령(`SET`/`DBSIZE`/`KEYS`/`INFO`)이 한 번도 섞이지 않는
    "`GET` 후 `EXPIRE`로 세션 연장" 워크로드에서는 그것 말고는 컴팩션을
    유발할 경로가 없다 (20만 회 반복 시 힙 200,100 → 186으로 확인)

> **"새 만료 시각이 더 이를 때만 push"하는 최적화는 쓰지 말 것.** TTL을
> 짧게 갱신했을 때 만료 키가 조회에 계속 노출되는 정확성 회귀가 생긴다.
> 무조건 push + `expire_at` 일치 검사가 옳다. (회귀 테스트로 고정해 두었다)

## 명세 해석 규칙

과제 명세가 규정하지 않아 구현마다 갈릴 수 있는 지점들이다.
이 구현은 아래처럼 확정했고, 전부 테스트로 고정해 두었다.

**1. 만료 키의 지위 (가장 중요)**

만료 시각이 지난 키는 **접근 여부와 무관하게 논리적으로 존재하지 않는 것으로
간주한다.** 따라서 `DBSIZE` 카운트, `KEYS` 목록, `used_memory` 어디에도
포함되지 않으며, `EXISTS`는 0, `DEL`은 0, `TTL`은 -2, `GET`은 `(nil)`이다.
**축출 판정에도 같은 원칙이 적용된다** — `used_memory`와 `maxmemory`를
비교하기 전에 만료 키를 먼저 회수하고, 만료로 사라진 키는 `evicted_keys`에
계상하지 않는다. `evicted_keys`는 오직 `maxmemory` 초과로 LRU 정책이 제거한
키만 센다.

내부 기법(lazy deletion 등)은 자유롭게 고르되, **외부에서 관측되는 출력은
항상 이 규칙과 같아야 한다.** 바꿔 말하면 조회 전용 명령(`DBSIZE` 등)을
중간에 끼워 넣든 말든 최종 상태가 동일해야 한다.

**2. 정수 인자의 범위**

정수를 받는 모든 명령(`CONFIG SET maxmemory`, `EXPIRE`)은 ASCII 부호와 ASCII
숫자만 허용하고, 64비트 signed 범위를 벗어나면
`(error) ERR value is not an integer or out of range`를 반환한다.
`1_000`, `" 12 "`, `0x10`, `3.0`, 유니코드 숫자(`١٢`)는 전부 거부한다.
인자 개수 검사가 정수 파싱보다 우선한다.

**3. TTL 반올림**

남은 시간을 **내림(floor)** 한다. 실제 Redis는 `(ttl_ms + 500) / 1000`
반올림이라 `EXPIRE k 3` 직후 3을 반환하지만, 이 구현은 명세 실행 예시의
`(integer) 2`를 재현하기 위해 내림을 택했다. 대신 경계에서 값이 시계
해상도에 따라 흔들린다는 점을 유의할 것 — 두 명령이 같은 타이머 틱 안에서
실행되면 남은 시간이 정확히 `3.0`이라 3이 나온다. 살아 있는 키가 `0`을
반환할 수 있으며, `0`은 만료를 뜻하지 않는다(만료/부재는 `-2`).

**4. `list` 사용 경계**

- **금지**: `dict`/`set`/`frozenset`/`collections`의 모든 사용, 그리고 파이썬
  `list`를 키-값 매핑 저장소로 쓰거나 선형 탐색으로 해시맵·연결 리스트의
  역할을 대체하는 것
- **허용**: ① 고정 길이 인덱스 배열(`[None] * n` 버킷 테이블)
  ② 힙의 백업 배열(완전 이진 트리를 인덱스 산술로 표현하는 용도이므로
  끝에서의 `append`/`pop` 포함) ③ 저장소가 아닌 임시 컬렉션
  (`HashMap.keys()`의 스냅샷, 파싱 토큰/문자 버퍼, 출력 조립용 버퍼)
- **판정 기준**: "자료구조의 핵심 기능 — 해싱, 체이닝, 노드 간 `prev`/`next`
  연결, 힙 순서 유지 — 을 파이썬 내장 자료구조가 대신 수행하는가?"
  아니라면 위반이 아니다

**5. 그 외**

| 상황 | 이 구현의 동작 |
| --- | --- |
| `CONFIG SET maxmemory`로 한도를 낮춤 | `OK` 전에 즉시 LRU 축출, `evicted_keys` 누적 |
| `CONFIG SET maxmemory` 음수 | 범위 에러. 기존 설정과 데이터 불변 |
| 단일 엔트리 > maxmemory | OOM. 축출 시도 없음 → 기존 키·값·TTL·`evicted_keys` 전부 보존 |
| 덮어쓰기 `SET` | 신규와 동일하게 LRU 최근성 갱신. 판정 기준값은 (기존 총합 − 기존 크기 + 새 크기) |
| `KEYS` 결과가 비었을 때 | 정확히 `(empty array)` 한 줄 |
| `KEYS` 출력 형식 | `N) "key"` (N은 1부터). 순서는 규정하지 않음 |
| 명령/서브커맨드/섹션명 대소문자 | 구분하지 않음. 키와 값은 구분함 |
| `unknown command '<cmd>'`의 `<cmd>` | 사용자가 입력한 첫 토큰을 대소문자 변형 없이 그대로 |
| `KEYS`에 인자 | 인자를 받지 않는 명령 → `wrong number of arguments` |
| `INFO`에 `memory` 외 섹션 | `Unsupported INFO section` |
| 따옴표 불균형 | 닫히지 않았거나, 토큰 중간에 나타나거나, 닫는 따옴표 뒤에 공백 없이 문자가 오면 `Protocol error: unbalanced quotes in request` |
| 내부 예외 | REPL 최상위 가드가 잡아 `(error) ERR internal error: ...` 출력 후 계속 |
| 입력 스트림 디코딩 실패 | `Protocol error: invalid input encoding` 출력 후 종료 (디코더가 같은 바이트에 계속 걸려 무한 루프가 되므로 한 줄 무시가 아니라 세션 종료) |

## 에러 표준

| 상황                | 출력                                                                |
| ------------------- | ------------------------------------------------------------------- |
| 모르는 명령         | `(error) ERR unknown command '<cmd>'`                               |
| 인자 개수 오류      | `(error) ERR wrong number of arguments for '<cmd>' command`         |
| 정수 파싱/범위 실패 | `(error) ERR value is not an integer or out of range`               |
| 메모리 초과         | `(error) OOM command not allowed when used_memory > 'maxmemory'`    |
| 따옴표 불균형       | `(error) ERR Protocol error: unbalanced quotes in request`          |
| 입력 디코딩 실패    | `(error) ERR Protocol error: invalid input encoding`                |
| 미지원 CONFIG/INFO  | `(error) ERR Unsupported CONFIG parameter: ...` 등                  |
| 내부 예외 (방어선)  | `(error) ERR internal error: ...`                                   |

## 테스트 구성

| 파일 | 내용 |
| --- | --- |
| [tests/test_linked_list.py](tests/test_linked_list.py) | 필수 메서드 6종, 경계(빈 리스트/단일 노드), 중복 제거·타 리스트 노드 방어, `move_to_front` 멱등성, 순회 중 삭제 |
| [tests/test_hashmap.py](tests/test_hashmap.py) | 필수 메서드 6종, 확장 시점 고정(7/13/25/49), 축소 목표 용량 고정과 진동 방지, 강제 충돌 체이닝, 해시 분포, 유니코드 키 |
| [tests/test_heap.py](tests/test_heap.py) | 필수 메서드 + `_heapify_up`/`_heapify_down`, 빈 힙, 500개 pop 순서 == `sorted()`, 혼합 연산 중 힙 불변식, `(expire_at, key)` 튜플 |
| [tests/test_mini_redis.py](tests/test_mini_redis.py) | 명령 규약 전수, 명세 실행 예시 고정, `used_memory` 불변식 퍼징(3000스텝), TTL 반환 코드·만료 경계·내림 규칙, 힙 컴팩션 상한 3종, **만료/축출 회귀 6종** |
| [tests/test_cli.py](tests/test_cli.py) | 토크나이저·이스케이프·따옴표 불균형, `_parse_int` 엄격성과 int64 경계, `format_result` 7종, 인자 개수 오류 전수, 프롬프트 문자열, REPL 최상위 가드, **AST 제약 검사** |

### 회귀로 고정한 핵심 시나리오

- `test_readonly_commands_do_not_change_outcome` — **조회 명령의 유무가 어떤
  키가 살아남는지를 바꾸면 안 된다.** 만료 키가 축출 판정을 오염시키던 버그의
  본질을 그대로 표현한 테스트다
- `test_eviction_purges_expired_before_evicting_live_keys` — 만료 키 대신
  살아있는 키가 희생되지 않는지
- `test_config_set_purges_expired_before_evicting` — 같은 문제의 `CONFIG SET` 경로
- `test_huge_integer_is_error_not_crash` — `EXPIRE k 10^400`이 `OverflowError`로
  프로세스를 죽이지 않는지
- `test_stale_heap_entry_does_not_kill_new_value` — 덮어쓰기 후 힙에 남은
  옛 항목이 새 값을 지우지 않는지
- `test_ttl_shortening_takes_effect` — TTL을 짧게 갱신하면 짧아진 시각에 만료되는지
- `test_unlimited_mode_set_does_not_stall_on_mass_expiry` — 무제한 모드 `SET`이
  "그동안 만료된 키 전부 회수"를 떠안지 않는지
- `test_ttl_heap_bounded_without_any_purge_command` — purge 계열 명령을 한 번도
  섞지 않는 `GET`+`EXPIRE` 워크로드에서도 힙이 상한 안에 머무는지

### 뮤테이션 테스트 결과

핵심 라인을 하나씩 망가뜨린 사본으로 테스트가 실제로 잡아내는지 확인했다.
**19종 뮤턴트 전부 killed, 생존 0.** 검사한 것: 축출 전 만료 회수 삭제 /
`EXPIRE` 컴팩션 삭제 / purge를 가드 앞으로 되돌림 / `_parse_int`의 범위·정규식
검사 삭제 / 닫는 따옴표 뒤 검사 삭제 / `_is_expired` 경계 `<=`→`<` / 프롬프트
문자열 변경 / 에러 문구 변경 / REPL `continue`→`break` / `_SHRINK_FACTOR` 변경 /
컴팩션 임계 기준 변경 / `_maybe_shrink` 호출 삭제 / `move_to_front` 삭제 /
`owner` 검사 무력화 / `MinHeap.push` no-op / `KEYS` arity 삭제 / 로드팩터 임계 변경.

특히 `MinHeap.push`를 no-op으로 바꾸면 9개 테스트가 실패한다 — 힙이 장식이
아니라 실제 동작 경로에 있음을 저장소가 스스로 증명한다(체크리스트 1-E절 요구).

## 학습 체크포인트

이 과제를 마친 뒤 아래 질문에 **코드의 파일:라인을 지목하며** 답할 수 있어야 한다.

1. FNV-1a 해시는 충돌을 어떻게 줄이는가? 해시값 생성과 인덱스 산출은 어떻게 나뉘는가?
   충돌이 났을 때 체이닝은 어떤 비용을 가지는가?
2. 해시맵 + 이중 연결 리스트 조합이 **왜 O(1) LRU**를 가능하게 하는가?
   (힌트: 해시맵으로 노드 참조를 곧장 찾으므로 리스트를 탐색할 필요가 없다)
3. 힙이 TTL 만료 관리에 적합한 이유는? 정렬된 리스트나 일반 큐로 했다면 무엇이 달라지나?
   `(expire_at, key)` 튜플에서 만료 시각이 같으면 무슨 일이 일어나는가?
4. `maxmemory`를 초과한 순간부터 가장 오래된 키가 제거되는 전체 흐름을 설명할 수 있는가?
   `used_memory`는 언제 갱신되는가?
5. lazy deletion 전략의 장단점은? stale 힙 항목이 **언제 정리되고 언제 정리되지
   않는가?** 컴팩션은 왜 필요한가?
6. 축출 직전에 만료 키를 회수하지 않으면 정확히 무엇이 잘못되는가?
   (세 가지: 불필요한 축출 / 살아있는 키 희생 / `evicted_keys` 오염)
7. LRU 대신 LFU를 구현한다면 자료구조를 어떻게 바꿔야 하는가?
8. 데이터가 10만 건으로 늘어나면 현재 구조에서 병목은 어디인가?
   (힌트: 일괄 rehash로 특정 `SET` 하나만 O(n)으로 튄다 / 빈 버킷마다
   연결 리스트 + sentinel 2개를 선할당한다 / 접근 없는 만료 키는 회수가 늦다)
