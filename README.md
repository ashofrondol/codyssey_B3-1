# Mini Redis

Redis의 핵심 동작을 직접 구현해 본 CLI 기반 인메모리 키-값 저장소.
해시맵 · 이중 연결 리스트 · 최소 힙을 **밑바닥부터** 작성해
LRU 자동 제거와 TTL 만료가 어떻게 동작하는지 손으로 확인할 수 있다.

## 0. 과제 명세 (원본 미션 요구사항)

> 출처: `codyssey_assignments/B3-1.pdf` — 원문 요구사항을 그대로 옮기고, 해설은 💡 로 구분했다.

---

### 0.1 미션 한눈에 보기

| 항목 | 내용 |
|------|------|
| 분야 | AI/SW 기초 |
| 구분 | 자료구조와 알고리즘 |
| 학습시간 | 80시간 |
| 미션 제목 | **정보를 엄청 빠르게 찾아주는 작은 저장소 만들기** |
| 산출물 | CLI 기반 Mini Redis 프로그램 1개 |
| 개발 환경 | Python 3.8 이상 |

**원문 — 1. 미션 소개**

> Redis를 써봤는데 왜 이렇게 빠른지 설명해보라고 하면 막히는 분들이 많습니다. 이유가 있습니다. 내부의 자료구조를 직접 구현해본 사람이 드물기 때문입니다. 해시맵, 이중 연결 리스트, 힙을 밑바닥부터 짜면서 LRU와 TTL이 어떻게 동작하는지 손으로 확인합니다.
>
> Redis는 전 세계에서 가장 널리 사용되는 In-Memory Key-Value 데이터 저장소입니다. 캐시, 메시지 브로커, 세션 저장소 등 다양한 용도로 활용되며, 그 핵심에는 효율적인 자료구조가 있습니다.
>
> 이번 미션에서는 Redis의 핵심 기능을 직접 구현하며 CLI 기반 Mini Redis를 완성합니다. 해시맵, 이중 연결 리스트, 힙 같은 자료구조를 밑바닥부터 구현하면서 평소 당연하게 사용하던 내장 자료형의 내부 동작 원리를 깊이 이해하게 됩니다.
>
> 또한, 실제 Redis가 메모리 제한 환경에서 어떻게 LRU 방식으로 오래된 데이터를 자동 제거하고, TTL을 통해 만료 시간을 관리하는지 직접 구현하며 체득합니다. 이 경험은 이후 알고리즘 학습, 코딩 테스트, 실제 서비스 성능 최적화로 확장될 수 있습니다.

#### 💡 (해설) 이 과제가 진짜로 묻는 것

> 💡 **1) "Redis 흉내내기"가 아니라 "자료구조 3종을 손으로 짜기"가 본체다.** `dict` 한 줄이면 SET/GET/DEL/EXISTS/DBSIZE/KEYS가 전부 동작한다. 그런데도 명세는 `dict`·`set`·`collections` 사용을 **금지**한다. 즉 채점의 무게중심은 "명령어가 동작하는가"가 아니라 "해시맵·이중 연결 리스트·최소 힙을 직접 만들었는가, 그리고 그것들이 실제 동작 경로에 놓여 있는가"다.
>
> 💡 **2) 세 자료구조가 각각 "왜 그것이어야 하는가"를 설명하게 만든다.** 해시맵 = O(1) 조회, 이중 연결 리스트 = O(1) 순서 갱신, 힙 = 최소 만료시각 O(1) 조회. 이 셋을 조합해야만 LRU + TTL이 상수/로그 시간에 돌아간다는 사실을 몸으로 겪게 하는 설계다.
>
> 💡 **3) "세 개의 구조가 한 키를 공유한다"는 일관성 문제가 숨은 난이도다.** DEL 한 번에 데이터 저장소·TTL 힙·LRU 리스트 세 곳에서 동시에 엔트리를 지워야 한다. 하나라도 빠뜨리면 유령 키·메모리 누수·stale 힙 항목이 생긴다. 명세가 `DEL은 데이터/TTL/LRU 모든 구조에서 엔트리를 함께 제거한다`를 따로 못 박아 둔 이유다.
>
> 💡 **4) used_memory 공식을 "정확히" 지키는지 본다.** `Σ(len(utf8(key)) + len(utf8(value)))` 이며 **노드/포인터/버킷 오버헤드는 제외**다. 한글·이모지 같은 멀티바이트 문자를 넣었을 때 `len(문자열)`이 아니라 `len(문자열.encode('utf-8'))`을 써야 값이 맞는다.
>
> 💡 **5) 출력 문자열이 곧 프로토콜이다.** `OK`, `(nil)`, `(integer) N`, `(error) ERR ...` 형식은 자유 서술이 아니라 "정확히 이 문자열"이어야 채점에서 인정된다.

---

### 0.2 최종 산출물 (제출물)

**원문 — 2. 최종 결과물**

> 다음 기능이 정상 동작하는 CLI 기반 Mini Redis 프로그램 1개를 완성한다.

**1. String 타입 기본 명령어 (6개)**

| 명령어 | 원문 설명 |
|--------|-----------|
| `SET` | 키에 값 저장 (성공 시 내부적으로 LRU 추적 업데이트) |
| `GET` | 키의 값 조회 (성공 시 내부적으로 LRU 추적 업데이트) |
| `DEL` | 키 삭제 |
| `EXISTS` | 키 존재 여부 확인 |
| `DBSIZE` | 전체 키 개수 반환 |
| `KEYS` | 전체 키 목록 출력 (패턴 매칭은 구현하지 않음) |

**2. 메모리 관리 명령어 (2개)**

| 명령어 | 원문 설명 |
|--------|-----------|
| `CONFIG SET maxmemory` | 최대 메모리 제한 설정 (바이트 단위) |
| `INFO memory` | 현재 메모리 사용량, 제한, 제거된 키 개수 확인 |

**3. TTL 관리 명령어 (2개)**

| 명령어 | 원문 설명 |
|--------|-----------|
| `EXPIRE` | 키의 만료 시간 설정 (초 단위) |
| `TTL` | 키의 남은 만료 시간 조회 |

**4. CLI 인터페이스**

- 사용자가 명령어를 입력하면 즉시 실행 결과를 확인할 수 있는 REPL 환경
- 명령어 파싱, 실행, 결과 출력이 반복적으로 동작

> 💡 (해설) PDF에는 "제출 증거 체크리스트" 절이 따로 없다. 다만 제약 사항(0.6)에서 **각 자료구조를 독립된 모듈/파일로 분리**하라고 요구하므로, 실질적인 제출 산출물은 아래 형태가 된다.
>
> - 실행 진입점 1개 (예: `main.py`) — `python main.py` 로 REPL이 떠야 한다
> - 이중 연결 리스트 모듈 1개
> - 해시맵 모듈 1개
> - 최소 힙 모듈 1개
> - Mini Redis 애플리케이션 로직 모듈
> - (보너스 2 선택 시) `STACK_QUEUE_DEQUE.md`
>
> 💡 파일명은 PDF가 지정하지 않는다. 단, 보너스 2의 문서명 `STACK_QUEUE_DEQUE.md` 만은 **원문이 명시한 고정 이름**이므로 그대로 써야 한다.

---

### 0.3 과제 목표 — 수료 후 스스로 설명할 수 있어야 하는 것

**원문 — 3. 과제 목표**

> 이 과제를 마친 후, 학습자는 아래를 스스로 설명할 수 있어야 한다.

- [ ] **G1.** 해시맵의 해시 함수와 충돌 해결 방식(체이닝)을 **구현 코드를 기반으로** 설명할 수 있다.
- [ ] **G2.** 이중 연결 리스트와 해시맵을 조합하여 **O(1) LRU 추적이 가능한 이유**를 설명할 수 있다.
- [ ] **G3.** 힙이 **TTL 만료 시간 관리에 적합한 이유**를 설명할 수 있다.
- [ ] **G4.** 메모리 제한 환경에서 LRU 정책으로 데이터를 제거하는 **전체 흐름(used_memory 갱신 포함)** 을 설명할 수 있다.

> 💡 (해설) 네 항목 모두 동사가 "구현한다"가 아니라 **"설명할 수 있다"** 이다. 즉 코드가 돌아가는 것만으로는 목표 달성이 아니며, 구두 평가에서 **파일:라인을 지목하며** 말할 수 있어야 한다. G1의 "구현 코드를 기반으로"라는 단서가 이를 못 박는다.

---

### 0.4 기능 요구 사항 (필수)

**원문 — 4. 기능 요구 사항**

> 다음 요구사항을 모두 만족해야 한다.

#### R1. 기본 자료구조 직접 구현 (내장 Key-Value 컬렉션으로 대체 금지)

**이중 연결 리스트**

- [ ] **R1-1** 노드 구조: `prev` , `next` , `data` 필드
- [ ] **R1-2** 주요 메서드: `insert_front` , `insert_back` , `remove_front` , `remove_back` , `remove_node` , `move_to_front`
- [ ] **R1-3** 모든 삽입/삭제/이동 연산은 **O(1)** 이어야 한다

**해시맵 (체이닝 방식)**

- [ ] **R1-4** 주요 메서드: `put` , `get` , `remove` , `contains` , `keys` , `size`
- [ ] **R1-5** 해시 함수는 **직접 설계**해야 한다
- [ ] **R1-6** 충돌 해결은 **체이닝 방식**으로 구현해야 한다 (권장: 이중 연결 리스트 재사용)
- [ ] **R1-7** **로드 팩터 0.75 초과** 시 버킷을 **2배 확장**해야 한다

**힙 (최소 힙)**

- [ ] **R1-8** 주요 메서드: `push` , `pop` , `peek` , `size`
- [ ] **R1-9** `_heapify_up` , `_heapify_down` 구현 필요
- [ ] **R1-10** TTL 만료 관리를 위해 **`(expire_at, key)`** 형태의 요소를 다룰 수 있어야 한다

#### R2. String 타입 명령어 (Redis 스타일 출력)

**공통 규칙**

- [ ] **R2-1** 키 기반 명령어는 실행 전 **"만료 여부"를 먼저 확인**할 수 있어야 한다 (만료된 키는 삭제 후 '없는 키'처럼 처리).
- [ ] **R2-2** 출력은 Redis 스타일을 따른다: `OK` , `(nil)` , `(integer) N` , `(error) ...`

**`SET key value`**

- [ ] **R2-3** 성공 시 `OK`
- [ ] **R2-4** 메모리 초과 시 LRU 제거를 수행한다 (세부 규칙은 R3 참조)
- [ ] **R2-5** 기존 키를 덮어쓰는 경우: 기존 TTL은 **"초기화(삭제)"** 한다

**`GET key`**

- [ ] **R2-6** 키가 없거나 만료된 경우 `(nil)`
- [ ] **R2-7** 존재하는 경우 `"value"` 형태로 반환
- [ ] **R2-8** **반환이 성공한 경우에만** LRU를 갱신한다 (만료로 삭제된 경우는 갱신하지 않음)

**`DEL key`**

- [ ] **R2-9** 삭제 성공 시 `(integer) 1` , 없으면 `(integer) 0`
- [ ] **R2-10** 삭제 시 **LRU/TTL 관련 구조에서도 해당 엔트리를 함께 제거**해야 한다

**`EXISTS key`**

- [ ] **R2-11** 존재하면 `(integer) 1` , 없으면 `(integer) 0`

**`DBSIZE`**

- [ ] **R2-12** 현재 저장된 키 개수를 `(integer) N` 으로 반환

**`KEYS`**

- [ ] **R2-13** 전체 키 목록을 **배열 형태**로 출력 (정렬/순서는 요구하지 않음)

  원문 예시:

  ```
  1. "user:2"
  2. "user:3"
  ```

- [ ] **R2-14** 키가 없으면 `(empty array)` 같은 형태로 비어 있음을 표현해도 된다

> 💡 (해설) 실제 Redis CLI의 배열 출력은 `1) "user:2"` 형태(숫자 + 닫는 괄호)다. PDF 텍스트에는 `1.` 로 보이지만 이는 문서 서식(번호 매기기 목록)일 가능성이 높다. 평가 체크리스트는 `N) "key"` 형식을 기대하므로, **`1) "user:2"` 형식으로 구현하는 것이 안전**하다. 순서는 요구되지 않으므로 채점은 집합 비교로 이뤄진다.

#### R3. 메모리 관리 + LRU 자동 제거

**`CONFIG SET maxmemory bytes`**

- [ ] **R3-1** `bytes` 는 **0 이상의 정수**
- [ ] **R3-2** **0은 "무제한"** 으로 간주한다
- [ ] **R3-3** 성공 시 `OK` , 정수 파싱 실패 시 에러 표준을 따른다

**`INFO memory`**

- [ ] **R3-4** 아래 **3개 항목을 최소 포함**해 출력한다 (표현 형태는 동일하면 됨):

  ```
  used_memory:<number>
  maxmemory:<number>
  evicted_keys:<number>
  ```

**used_memory 산정 기준(공식)**

- [ ] **R3-5** `used_memory = Σ( len(utf8(key)) + len(utf8(value)) )`
- [ ] **R3-6** 자료구조(노드/포인터/버킷 등) **오버헤드는 계산에서 제외**한다

**LRU 제거 규칙**

- [ ] **R3-7** `maxmemory > 0` 이고, **SET 이후** used_memory가 maxmemory를 **초과**하면 used_memory가 **maxmemory 이하가 될 때까지** "가장 오래 사용되지 않은 키(LRU)"부터 제거한다
- [ ] **R3-8** 제거된 키는 `evicted_keys` 에 **누적 카운트**한다
- [ ] **R3-9** 만약 **"단일 엔트리(키+값)" 자체가 maxmemory를 초과**한다면: **저장하지 않고 에러(OOM)를 출력**한다

#### R4. TTL 관리 (힙 기반)

**`EXPIRE key seconds`**

- [ ] **R4-1** key가 없으면 `(integer) 0`
- [ ] **R4-2** seconds가 **0 이하**라면 **"즉시 만료"로 처리해도 된다** (존재하면 삭제 후 `(integer) 1`)
- [ ] **R4-3** 정상 설정 시 `(integer) 1`

**`TTL key`**

- [ ] **R4-4** key가 없으면 `(integer) -2`
- [ ] **R4-5** key는 존재하지만 만료 시간이 없으면 `(integer) -1`
- [ ] **R4-6** 만료 시간이 있으면 **남은 초**를 `(integer) N` 으로 반환

**TTL/LRU 엣지 케이스 최소 규칙(명시)**

- [ ] **R4-7** 만료된 키는 GET 시 **먼저 삭제 후** `(nil)` 을 반환하며, **LRU 갱신은 하지 않는다**
- [ ] **R4-8** SET이 기존 키를 덮어쓸 때 TTL은 **초기화(삭제)** 한다
- [ ] **R4-9** EXPIRE를 **없는 키**에 호출하면 `(integer) 0` 이다
- [ ] **R4-10** DEL은 **데이터/TTL/LRU 모든 구조**에서 엔트리를 함께 제거한다
- [ ] **R4-11** 구현 방식은 **"힙을 통해 가장 빠른 만료를 빠르게 찾을 수 있어야 한다"** 는 목표를 만족하면 된다 (예: lazy deletion 전략 등은 구현 선택)

#### R5. 에러 처리 표준 + CLI 인터페이스

**CLI**

- [ ] **R5-1** `mini-redis> ` 프롬프트 출력
- [ ] **R5-2** 사용자 입력을 읽고 명령어 파싱 및 실행
- [ ] **R5-3** `exit` 또는 `quit` 으로 종료 가능

**에러 출력(표준 형식 예시)**

- [ ] **R5-4** 잘못된 명령: `(error) ERR unknown command '<cmd>'`
- [ ] **R5-5** 인자 개수 오류: `(error) ERR wrong number of arguments for '<cmd>' command`
- [ ] **R5-6** 정수 파싱 실패: `(error) ERR value is not an integer or out of range`
- [ ] **R5-7** 메모리 초과(OOM): `(error) OOM command not allowed when used_memory > 'maxmemory'`

**값 파싱**

- [ ] **R5-8** 예시처럼 `"Alice"` 같은 **따옴표 입력을 허용**한다 (구현 난이도에 따라 단순 규칙으로 처리 가능)
- [ ] **R5-9** **최소 요구**: 공백이 없는 값 / 큰따옴표로 감싼 값 **둘 중 하나 방식은 지원**

> 💡 (해설) 에러 문자열은 대소문자·따옴표·공백까지 그대로 맞춰야 한다. 특히 R5-5는 `for '<cmd>' command` 로 **끝에 ` command` 가 붙는다**는 점, R5-7은 `ERR` 가 아니라 **`OOM` 으로 시작**하고 `'maxmemory'` 가 작은따옴표로 감싸진다는 점이 자주 틀리는 지점이다.

---

### 0.5 보너스 과제 (선택)

**원문 — 5. 보너스 과제 (선택)**

- [ ] **B1. 동적 배열 직접 구현**
  - 동적 배열을 직접 구현하고 `append`/`get`/`set`/`remove` 및 **capacity 2배 확장 로직**을 포함한다
  - 해시맵 버킷 테이블 확장 / 힙 내부 저장소에 "배열 확장" 개념을 적용할 수 있다

- [ ] **B2. 스택/큐/덱 이해와 활용**
  - 스택/큐/덱의 개념을 조사하고 **`STACK_QUEUE_DEQUE.md`** 로 문서화한다
  - Pub/Sub(보너스 5)나 커맨드 히스토리 같은 큐 기반 기능의 기반이 된다

- [ ] **B3. 이진 트리와 순회 알고리즘**
  - 이진 트리 구현 및 **전위/중위/후위/레벨 순회**를 구현한다
  - "힙이 완전 이진 트리를 배열로 표현한다"는 관점을 더 단단히 만든다

- [ ] **B4. 이진 탐색 트리(BST)**
  - BST **삽입/탐색/삭제 및 중위 순회 정렬 결과**를 구현한다
  - 추후 "키 정렬/범위 조회" 같은 확장 기능의 기반이 된다

- [ ] **B5. Pub/Sub 기능 구현**
  - `PUBLISH` , `SUBSCRIBE` 명령어를 추가하고 **채널 기반 메시징**을 구현한다
  - 구현한 연결 리스트를 메시지 큐(구독자별 버퍼 등)로 재활용할 수 있다

> 💡 (해설) 보너스는 5개 모두 "필수 3종 자료구조의 연장선"으로 설계되어 있다. B1은 해시맵 버킷 배열과 힙 내부 배열의 **기반**, B3는 힙의 **이론적 배경**, B2/B5는 연결 리스트의 **재활용처**다. 즉 보너스를 하면 필수 구현의 이해가 되돌아와 깊어지는 구조다.

---

### 0.6 개발 환경 · 제약 사항

**원문 — 6. 개발 환경**

- **Python 3.8 이상**

**원문 — 7. 제약 사항**

#### ⛔ 라이브러리/내장 자료형 제한 (학습 목적)

- **C1. `dict` , `set` , `collections` 사용 금지**
- **C2.** 단, "고정 길이 배열/인덱스 접근" 수준의 저장소가 필요하다면 **제한적으로 사용할 수 있는 구현 방식을 선택**하되, **내장 컬렉션으로 해시맵/캐시를 대체하는 방식은 금지**한다 (예: **dict로 put/get 구현 금지**).

> 💡 (해설) C2가 허용하는 것은 `[None] * capacity` 처럼 **길이가 고정된 인덱스 접근 배열**(파이썬 `list`)까지다. 해시맵의 버킷 테이블과 힙의 내부 저장소를 만들려면 어차피 인덱스 배열이 필요하기 때문이다. 금지되는 것은 **키→값 매핑 자체를 내장 자료형에 위임**하는 것이다. 채점자는 AST 검사로 `dict`/`set`/`frozenset`/`collections`/`defaultdict`/`OrderedDict`/`Counter`/`deque` 의 **이름·리터럴(`{}`, `{...}`)·컴프리헨션·import 가 0건**인지 본다. **빈 dict 리터럴 `{}` 하나만 있어도 위반**이다.

#### 📁 구조

- **C3.** 각 자료구조(해시맵/이중 연결 리스트/힙)는 **독립된 모듈/파일로 분리**한다
- **C4.** 핵심 클래스/함수에는 **주석 또는 docstring**을 작성한다

#### 🚫 기능 범위 (구현하지 않는 것)

- **C5.** **네트워크 통신은 구현하지 않는다** (오직 CLI)
- **C6.** **데이터 영속성(파일 저장)은 구현하지 않는다**
- **C7.** Redis의 **복잡 자료형(List/Set/Sorted Set)은 구현하지 않는다**
- **C8.** **멀티스레딩/락 같은 동시성 처리는 요구하지 않는다**

> 💡 (해설) C1·C3은 **즉시 불합격(Fail-fast) 사유**와 직결된다. 평가 체크리스트 기준으로 (1) `dict`/`set`/`collections` 사용, (2) 해시맵·이중 연결 리스트·최소 힙 중 하나라도 직접 구현 부재, (3) `python main.py` 실행 불가 — 셋 중 하나라도 걸리면 나머지는 채점하지 않는다.
>
> 💡 Python **3.8** 기준이므로 3.9+ 문법을 쓰면 안 된다. 사용 금지 목록 — walrus `:=`(3.8에서는 동작하지만 채점 스크립트가 위반으로 잡는다), `match` 문(3.10+), `X | Y` 타입 표기(3.10+), `list[str]`/`dict[str, int]` 내장 제네릭(3.9+), `str.removeprefix`/`removesuffix`(3.9+).
>
> 💡 C3의 "독립 모듈"은 **단방향 의존**까지 의미한다. 자료구조 모듈이 `mini_redis`/`main` 같은 애플리케이션 로직을 import 하면 독립이 아니다.

---

### 0.7 결과/출력 예시

**원문 — 8. 결과 예시**

> 아래는 정답이 아니라 참고 예시다. 실제 실행 예시는 달라도 되지만, 평가를 위해 최대한 이해하기 쉬운 형태로 개발한다.

**실행 예시**

```
mini-redis> CONFIG SET maxmemory 30
OK
mini-redis> SET user:1 "Alice"
OK
mini-redis> SET user:2 "Bob"
OK
mini-redis> SET user:3 "Charlie"
OK
# maxmemory(30) 초과로 LRU(user:1) 제거
mini-redis> GET user:1
(nil)
mini-redis> INFO memory
used_memory:22
maxmemory:30
evicted_keys:1
mini-redis> KEYS
1. "user:2"
2. "user:3"
mini-redis> EXPIRE user:2 3
(integer) 1
mini-redis> TTL user:2
(integer) 2
# (3초 경과 후)
mini-redis> GET user:2
(nil)
mini-redis> TTL user:2
(integer) -2
```

**에러 출력 예시(예)**

```
mini-redis> CONFIG SET maxmemory abc
(error) ERR value is not an integer or out of range
mini-redis> GET
(error) ERR wrong number of arguments for 'GET' command
```

```
mini-redis> HELLO
(error) ERR unknown command 'HELLO'
```

#### 💡 (해설) 예시 숫자를 손으로 검산해 보기

> 💡 **`used_memory:22` 은 어떻게 나오나?**
> 남아 있는 키는 `user:2`(6바이트) + `Bob`(3바이트) = 9, `user:3`(6바이트) + `Charlie`(7바이트) = 13. 합계 **22**. 공식 `Σ(len(utf8(key)) + len(utf8(value)))` 와 정확히 일치한다. 값의 큰따옴표는 **파싱 단계에서 벗겨지므로 계산에 포함되지 않는다**(`"Bob"` 은 5바이트가 아니라 3바이트).
>
> 💡 **왜 `user:1` 이 제거됐나?**
> 세 키를 모두 넣으면 `user:1`(6)+`Alice`(5)=11, +9, +13 = 33 > 30. 초과분을 해소할 때까지 가장 오래 안 쓴 키인 `user:1` 이 제거되어 22 ≤ 30 이 된다. `evicted_keys:1`.
>
> 💡 **`EXPIRE user:2 3` 직후 `TTL user:2` 가 왜 `2` 인가?**
> 남은 시간을 **내림(floor)** 으로 계산하면 2.9997초 → `2` 가 나온다. 실제 Redis는 반올림해서 `3` 을 반환한다. 체크리스트는 **2와 3을 모두 인정**하므로 이 값을 리터럴로 맞추려 애쓸 필요는 없다.
>
> 💡 **`INFO memory` 는 실제로 3줄 출력이다.** PDF 본문의 `used_memory:<number> maxmemory:<number> evicted_keys:<number>` 는 한 줄처럼 보이지만 이는 텍스트 추출 결과이고, 실행 예시 블록이 3줄 출력을 보여준다.
>
> 💡 `#` 로 시작하는 줄(`# maxmemory(30) 초과로 LRU(user:1) 제거`)은 **프로그램 출력이 아니라 예시 문서의 주석**이다. 구현이 이런 줄을 출력할 필요는 없다.

---

### 0.8 📚 이 과제가 공부하길 원하는 것 (학습 지도)

> 이 표가 이 문서에서 가장 중요한 부분이다. 왼쪽은 명세가 시키는 일, 오른쪽은 그 요구가 실제로 겨냥한 CS 개념이다.

| 요구사항 | 표면적으로 시키는 일 | 실제로 학습시키려는 개념 | 스스로 답해볼 질문 |
|---|---|---|---|
| **R1-1 ~ R1-3** | 이중 연결 리스트의 `prev/next/data` 노드와 6개 메서드를 O(1)로 | **포인터 조작과 시간복잡도의 관계.** 단일 연결 리스트로는 `remove_node` 가 O(n)인 이유(앞 노드를 찾아야 함), 센티널(dummy head/tail) 노드를 두면 경계 조건 분기가 사라지는 이유 | `remove_node(node)` 가 왜 O(1)인가? 센티널 노드를 쓰지 않으면 어떤 `if` 들이 추가로 필요한가? 리스트가 비었을 때 `remove_front` 는 어떻게 동작하는가? |
| **R1-4, R1-5** | 해시맵 6개 메서드 + 해시 함수 직접 설계 | **해시 함수의 요건 — 결정성·균등 분포·저비용.** 문자열을 정수로 접는 방식(다항식 롤링 해시, FNV, djb2)과 그 안의 곱수·모듈러의 의미. `hash()` 를 그대로 쓰지 않고 직접 짜게 하는 이유 | 내 해시 함수는 입력 문자열을 어떤 과정으로 정수로 만들고, 그 정수를 어떻게 버킷 인덱스로 바꾸는가? (해시값 생성과 인덱스 산출을 **나눠서** 답해 보라) 왜 `sum(ord(c))` 는 나쁜 해시인가? |
| **R1-6** | 충돌 해결은 체이닝 (권장: 이중 연결 리스트 재사용) | **충돌 해결 전략의 트레이드오프.** 체이닝 vs 개방 주소법(선형 탐사·이중 해싱), 체인이 길어질 때의 최악 O(n), 자료구조 재사용(리스트를 버킷 체인으로)이 주는 코드 절약 | 모든 키가 같은 버킷에 몰리면 `get` 은 몇 번의 비교를 하는가? 개방 주소법을 썼다면 `remove` 에서 어떤 문제(tombstone)가 생기는가? |
| **R1-7** | 로드 팩터 0.75 초과 시 버킷 2배 확장 | **암오티즈드(분할 상환) 시간복잡도.** 왜 하필 0.75인가(공간 낭비 vs 충돌 확률), 왜 +1이 아니라 ×2인가(리사이즈 횟수를 로그로 줄여 삽입 평균 O(1) 유지), 리사이즈 시 **전 항목 재해싱이 필요한 이유**(인덱스가 capacity에 의존하므로) | 확장 시 기존 엔트리를 그냥 옮기면 왜 안 되고 다시 해싱해야 하는가? 확장 직후 그 한 번의 SET 은 O(n)인데, 그런데도 평균이 O(1)이라고 말할 수 있는 근거는? |
| **R1-8 ~ R1-10** | 최소 힙 `push/pop/peek/size` + `_heapify_up/_heapify_down` | **완전 이진 트리의 배열 표현.** 부모 `(i-1)//2`, 자식 `2i+1 / 2i+2` 라는 인덱스 산술로 포인터 없이 트리를 표현하는 아이디어. 힙 속성은 "부모 ≤ 자식"이지 전체 정렬이 아니다 | 힙은 정렬된 배열인가? `peek` 은 O(1)인데 `pop` 은 왜 O(log n)인가? `(expire_at, key)` 튜플에서 `expire_at` 이 같으면 무엇이 비교되는가? (튜플 비교의 2차 키) |
| **R2-1, R2-8, R4-7** | 만료 여부 선확인 / 만료 경로에서는 LRU 갱신 금지 | **Lazy expiration(지연 만료)과 "읽기가 쓰기가 되는" 부작용.** 조회 명령이 삭제라는 상태 변경을 일으키는 설계, 그리고 만료 삭제를 "사용"으로 오인해 LRU 순서를 오염시키면 안 되는 이유 | `GET` 하나의 전체 흐름을 순서대로 말해 보라(TTL 확인 → 삭제 여부 → 값 반환 → LRU 갱신 조건). 만료 키를 GET 했을 때 LRU를 갱신하면 구체적으로 무엇이 잘못되는가? |
| **R2-10, R4-10** | DEL은 데이터/TTL/LRU 세 구조에서 함께 제거 | **다중 인덱스 간 일관성(referential integrity).** 같은 논리적 엔티티가 3개 물리 구조에 동시에 존재할 때 생기는 유령 참조·메모리 누수·stale 엔트리 문제. 힙에서는 임의 원소 삭제가 O(n)이라 보통 **lazy deletion(꺼낼 때 유효성 검증)** 으로 우회한다 | 힙에서 특정 키의 항목만 골라 지우려면 몇 번의 탐색이 필요한가? lazy deletion을 쓴다면 pop 할 때 "이 항목은 이미 무효"임을 어떻게 판정하는가? |
| **R3-5, R3-6** | `used_memory = Σ(len(utf8(k)) + len(utf8(v)))`, 오버헤드 제외 | **문자 ≠ 바이트.** 유니코드 코드포인트와 UTF-8 인코딩 길이의 차이(ASCII 1, 한글 3, 이모지 4바이트). 그리고 "회계 모델을 단순화하면 무엇을 잃는가" — 실제 메모리와 장부상 메모리의 괴리 | `SET 안녕 하이` 이후 used_memory는 얼마인가? `len()` 과 `len(s.encode('utf-8'))` 의 차이를 설명해 보라. 오버헤드까지 포함하는 모델로 바꾸면 **버킷 2배 확장 순간** 무슨 일이 벌어지는가? |
| **R3-7, R3-8** | 초과 시 maxmemory 이하가 될 때까지 LRU부터 제거, evicted_keys 누적 | **캐시 교체 정책과 그 구현 비용.** LRU가 "해시맵 + 이중 연결 리스트"로 O(1)이 되는 원리(조회는 해시, 갱신은 리스트 이동), 그리고 **while 루프로 여러 개가 연쇄 축출될 수 있다**는 점 | 왜 둘 다 필요한가 — 해시맵만으로는? 리스트만으로는? LFU로 바꾸면 자료구조를 어떻게 바꿔야 하는가? 한 번의 SET이 여러 키를 축출할 수 있는가? |
| **R3-7 + R4 조합** | 축출 직전에 무엇을 먼저 해야 하는가 (명세가 직접 말하지 않는 부분) | **만료 키 회수와 축출의 순서 의존성.** 만료됐지만 아직 회수되지 않은 키가 used_memory 예산을 점유하면, 살아 있는 키가 대신 축출되고 evicted_keys 가 부풀려진다 | 축출 직전에 만료 키를 회수하지 않으면 정확히 무엇이 잘못되는지 **세 가지**로 말해 보라(불필요한 축출 / 살아있는 키 희생 / evicted_keys 오염). 만료로 사라진 키는 evicted_keys 에 포함되어야 하는가? |
| **R3-9** | 단일 엔트리가 maxmemory 초과면 저장하지 않고 OOM | **"실패해도 기존 상태를 망가뜨리지 않는다"는 원자성 감각.** 덮어쓰기 대상 키가 있었다면 그 값과 TTL은 그대로 보존되어야 하고, evicted_keys 도 증가하면 안 된다 | OOM으로 거절할 때 이미 지운 키가 있다면 어떻게 되는가? 검사를 "저장 후 되돌리기"가 아니라 "저장 전 사전 검사"로 해야 하는 이유는? |
| **R4-1 ~ R4-6, R4-11** | EXPIRE/TTL 반환값 규약 + 힙 기반 TTL | **우선순위 큐가 "가장 이른 마감"을 O(1)에 보여준다는 성질.** 정렬 리스트(삽입 O(n))·선형 스캔(조회 O(n)) 대비 힙(삽입 O(log n), 최소 조회 O(1))의 우위. `-2`/`-1`/`N` 세 가지 반환값은 **"없음"과 "무기한"을 구분**하는 API 설계 | 왜 정렬된 배열 대신 힙인가? `-1` 과 `-2` 를 하나로 합치면 클라이언트가 무엇을 못 하게 되는가? 아무도 접근하지 않는 만료 키는 언제 사라지는가? |
| **R4-11 (stale 항목)** | lazy deletion 등 구현 선택 자유 | **무한히 쌓이는 쓰레기(unbounded garbage)와 그 유계화.** 같은 키에 EXPIRE를 반복하거나 TTL 키를 DEL 하면 힙에 stale 항목이 남는다. 언제 정리되고 언제 안 되는지의 경계 | 힙 크기가 실제 TTL 키 수보다 훨씬 커지는 시나리오를 만들어 보라. 이를 유계로 만드는 방법 한 가지를 제시해 보라(예: 힙 크기가 실제 TTL 키 수의 배수를 넘으면 재구축, 키→힙 인덱스 역참조 테이블) |
| **R5-1 ~ R5-9** | 프롬프트·파싱·표준 에러 4종 | **REPL과 파서의 견고성(robustness).** 토크나이징(따옴표 안의 공백 보존), 명령어 디스패치, 그리고 **어떤 입력에도 프로세스가 죽지 않는다**는 서버 프로그램의 기본기 | `EXPIRE k 10**400` 같은 거대 정수, 닫히지 않은 따옴표, 빈 입력, Ctrl+C, EOF(Ctrl+D)를 넣으면 어떻게 되는가? 예외를 어디서 잡아야 REPL이 살아남는가? |
| **C1, C2** | dict/set/collections 금지 | **"라이브러리는 누군가 만든 자료구조일 뿐"이라는 감각.** 파이썬 `dict` 자체가 해시 테이블(개방 주소법 + 압축 엔트리 배열)이라는 사실을 알고 나면, 내가 만든 체이닝 해시맵과 비교할 수 있게 된다 | CPython 의 `dict` 는 체이닝인가 개방 주소법인가? 내 해시맵과 무엇이 다른가? `set` 은 `dict` 와 어떻게 다른가? |
| **C3, C4** | 자료구조를 독립 모듈로 분리 + docstring | **의존성 방향과 계층 분리.** 범용 자료구조(하위 계층)가 응용 로직(상위 계층)을 알면 재사용이 불가능해진다. 단방향 의존이 곧 재사용 가능성 | 내 `hash_map.py` 를 다른 프로젝트에 복사해 붙이면 바로 동작하는가? 아니라면 무엇을 import 하고 있는가? |
| **확장 사고** | (명세 밖) 10만 건 규모 | **스케일이 바꾸는 것.** 전체 rehash가 특정 SET 한 번을 O(n)으로 튀게 하는 문제 → 점진적 리해싱(incremental rehashing, 실제 Redis 방식). 대량 축출 후 해시맵이 축소되지 않으면 `KEYS` 가 capacity 비례 시간을 쓰는 문제 | 데이터가 10만 건이면 현재 구조의 병목은 어디인가? 점진적 리해싱은 어떻게 구현하는가(두 개의 테이블을 동시에 유지)? 해시맵 축소(shrink) 조건은 어떻게 잡아야 진동하지 않는가? |
| **확장 사고** | (명세 밖) 접근 없는 만료 키 | **Passive expire vs Active expire.** 접근 시점 검사에만 의존하면 아무도 안 건드리는 만료 키가 메모리를 영원히 점유한다. 실제 Redis는 주기적 샘플링(랜덤 20개 검사 → 만료 비율 25% 초과 시 반복)으로 보완한다 | 내 구현에서 만료 키가 회수되는 트리거는 몇 가지인가? active expire를 추가한다면 CLI 루프 어디에 넣겠는가? |

---

### 0.9 자주 놓치는 함정

1. **`SET` 이 기존 키를 덮어쓰면 TTL이 사라진다 (R2-5 / R4-8).**
   `SET k v` → `EXPIRE k 100` → `SET k v2` → `TTL k` 는 **`(integer) -1`** 이어야 한다. 값만 갈아끼우고 TTL을 그대로 두면 틀린다. 힙에 남는 stale 항목 처리까지 생각해야 한다.

2. **만료 키를 GET 할 때 LRU를 갱신하면 안 된다 (R2-8 / R4-7).**
   "GET 성공 시 LRU 갱신"만 읽고 모든 GET 경로에서 갱신하면 위반이다. 명세는 **"반환이 성공한 경우에만"**, **"만료로 삭제된 경우는 갱신하지 않음"** 이라고 두 번 못 박았다.

3. **`maxmemory 0` 은 "메모리 0바이트"가 아니라 "무제한"이다 (R3-2).**
   `maxmemory > 0` 조건을 빼먹고 축출 로직을 돌리면, 0으로 설정한 순간 모든 키가 축출된다.

4. **used_memory는 문자 수가 아니라 **UTF-8 바이트 수**다 (R3-5).**
   `len(s)` 를 쓰면 ASCII 값으로만 테스트할 때는 통과하지만 한글/이모지에서 즉시 어긋난다. 반드시 `len(s.encode('utf-8'))`.

5. **단일 엔트리 OOM은 "축출"이 아니라 "거절"이다 (R3-9).**
   키+값 하나가 maxmemory보다 크면 **저장하지 않고** OOM 에러를 낸다. 이때 `evicted_keys` 는 증가하면 안 되고, 덮어쓰려던 기존 키의 값·TTL도 보존되어야 한다. "일단 넣고 축출로 해결"하면 기존 데이터를 다 날린 뒤 결국 실패하는 최악의 동작이 된다.

6. **`TTL` 의 `-1` 과 `-2` 를 헷갈리지 말 것 (R4-4 / R4-5).**
   `-2` = 키가 아예 없음, `-1` = 키는 있는데 만료 시간이 없음. 반대로 구현하는 실수가 흔하다.

7. **에러 문자열의 꼬리와 접두어 (R5-5 / R5-7).**
   인자 개수 오류는 `... for 'GET' command` 로 **`command` 가 뒤에 붙고**, OOM은 `ERR` 가 아니라 **`OOM` 으로 시작**한다. `(error) ` 접두어는 네 종류 모두에 붙는다.

8. **축출 전에 만료 키를 회수하지 않으면 살아 있는 키가 희생된다.**
   > 💡 (해설 — PDF가 명시하지 않은 추론) PDF는 "축출 직전 만료 키 회수"를 직접 요구하지 않는다. 하지만 R3-5(used_memory 공식)와 R2-1(만료 키는 '없는 키'처럼 처리)을 동시에 만족시키려면, 만료된 키는 used_memory에서 빠져 있어야 한다. 평가 체크리스트는 이 상황(만료 키가 예산을 점유해 살아 있는 키가 대신 축출되는 일)을 별도 항목으로 확인한다.

9. **`DBSIZE`/`KEYS`/`INFO memory` 도 만료 키를 빼고 답해야 한다.**
   > 💡 (해설 — 추론) R2-1의 "키 기반 명령어는 실행 전 만료 여부를 먼저 확인"을 넓게 읽으면, 한 번도 접근한 적 없는 만료 키가 DBSIZE 카운트나 KEYS 목록, used_memory 에 남아 있으면 안 된다. 접근 시점 검사(lazy)만 구현하면 여기서 어긋나기 쉽다.

10. **어떤 입력에도 REPL이 traceback과 함께 죽으면 안 된다 (R5-2).**
    빈 입력, 닫히지 않은 따옴표, `EXPIRE k 10**400` 같은 거대 정수, 인자 개수 오류, Ctrl+C, EOF 모두 에러 메시지를 출력하고 프롬프트로 돌아와야 한다.

11. **빈 dict 리터럴 `{}` 하나가 즉시 불합격이다 (C1).**
    정규식 검색은 `{}` 를 놓치지만 AST 검사는 잡는다. `Counter`, `deque`, `OrderedDict`, `defaultdict` 도 전부 금지 목록에 포함된다.

12. **힙이 "장식"이면 안 된다 (R1-8 ~ R1-10, R4-11).**
    최소 힙 클래스를 만들어 두고 실제 TTL 만료 판정은 전체 키 선형 스캔으로 하는 구현은, 블랙박스 테스트는 통과하지만 코드 확인에서 걸린다. **힙을 no-op 스텁으로 바꿨을 때 실패하는 경로**가 있어야 한다.

### 0.10 ✅ 과제 수행 점검 (명세 대조)

> 점검 방식: 저장소의 실제 소스를 명세의 요구사항 ID 와 1:1 대조. 판정 근거는 파일 경로로 명시.
> README 의 주장은 근거로 채택하지 않았고, 전부 소스 코드 · 실제 REPL 실행 · AST 검사 · 뮤테이션 검증으로 재확인했다.

**종합 판정: 충족** — 필수 53개 중 충족 53 / 부분 0 / 미충족 0 / 로컬검증불가 0
**보너스: 5개 중 충족 0 / 미충족 5** (보너스는 선택 항목이며 종합 판정에 반영하지 않았다)

#### 제약 사항 (Fail-fast 항목) 선검사

| ID | 제약 | 판정 | 근거 / 비고 |
| --- | --- | --- | --- |
| C1 | `dict`/`set`/`collections` 사용 금지 | ✅ 충족 | 저장소 전 `.py` 파일을 AST 로 직접 훑어 **금지 이름·dict/set 리터럴·컴프리헨션·`collections` import 0건** 확인. 저장소 자체도 동일 검사를 테스트로 들고 있다 — `tests/test_cli.py:286-323` (`TestConstraints.test_no_banned_builtins_anywhere`) |
| C2 | 내장 컬렉션으로 해시맵/캐시 대체 금지 | ✅ 충족 | `list` 는 ① 버킷 테이블 (`hashmap.py:165-172`, `[None] * capacity`) ② 힙 백업 배열 (`heap.py:22`) ③ 임시 스냅샷 (`hashmap.py:100-104`) 로만 쓰인다. 키→값 매핑·체이닝·노드 연결·힙 순서 유지는 전부 직접 구현 코드가 수행한다 |
| C3 | 자료구조를 독립 모듈로 분리 (단방향 의존) | ✅ 충족 | `linked_list.py` (import 없음) ← `hashmap.py:12` ← `mini_redis.py:30-32` ← `main.py:17`. `heap.py` 는 import 0건. 자료구조 모듈이 `mini_redis`/`main` 을 역참조하는 곳 없음 (전 파일 import 목록 확인) |
| C4 | 핵심 클래스/함수에 주석 또는 docstring | ✅ 충족 | 5개 모듈 전부 모듈 docstring + 클래스/메서드 docstring 보유. 예: `linked_list.py:1-9,13-20,32-41`, `hashmap.py:1-10,16-31,119-141`, `heap.py:1-10,14`, `mini_redis.py:1-26,42`, `main.py:1-13,26-31` |
| C5 | 네트워크 미구현 | ✅ 충족 | `socket`/`http`/`asyncio` import 0건. 입력은 `main.py:247` 의 `input()` 뿐 |
| C6 | 영속성 미구현 | ✅ 충족 | 파일 쓰기 호출 없음 (`open(` 은 테스트의 AST 검사에서만 등장 — `tests/test_cli.py:304`) |
| C7 | List/Set/Sorted Set 미구현 | ✅ 충족 | `main.py:163-235` 디스패처가 String + 메모리 + TTL 명령만 다룬다 |
| C8 | 동시성 미구현 | ✅ 충족 | `threading`/`lock` 사용 0건 |
| — | Python 3.8 호환 (3.9+ 문법 금지) | ✅ 충족 | walrus·`match`·`list[str]`/`dict[str,int]`·`X \| Y`·`removeprefix/removesuffix` 전부 grep 0건. `tests/test_cli.py:318-321` 이 walrus·match 를 AST 로 자체 차단 |
| — | `python main.py` 실행 가능 | ✅ 충족 | 실제 실행해 REPL 동작 확인 (아래 🧪 절). `main.py:288-289` |

#### R1. 기본 자료구조 직접 구현

| ID | 요구사항 (요약) | 판정 | 근거 / 비고 |
| --- | --- | --- | --- |
| R1-1 | 노드 구조: `prev`/`next`/`data` | ✅ 충족 | `linked_list.py:22` — `__slots__ = ('prev','next','data','owner')`. `owner` 는 "남의 리스트 노드 제거" 방어용 추가 필드이며 명세 3필드는 그대로 존재 |
| R1-2 | `insert_front`/`insert_back`/`remove_front`/`remove_back`/`remove_node`/`move_to_front` | ✅ 충족 | `linked_list.py:73,81,89,95,101,118` — 6개 전부 존재. `tests/test_linked_list.py` 가 6종 전수 검증 |
| R1-3 | 모든 삽입/삭제/이동 O(1) | ✅ 충족 | head/tail sentinel (`linked_list.py:46-49`) 덕에 분기·탐색 없음. `remove_node`(`:107-116`) 는 포인터 4개 재연결만, `move_to_front`(`:123-131`) 는 떼내고 다시 끼우기만. `remove_front/back` 도 sentinel 이웃을 바로 잡아 `remove_node` 에 넘긴다 (`:93,99`) |
| R1-4 | `put`/`get`/`remove`/`contains`/`keys`/`size` | ✅ 충족 | `hashmap.py:52,68,76,88,93,106` — 6개 전부 존재 |
| R1-5 | 해시 함수 직접 설계 | ✅ 충족 | `hashmap.py:119-152` — FNV-1a 64비트를 바이트 루프로 직접 구현 (`h ^= byte; h = (h * PRIME) & MASK64`). 파이썬 내장 `hash()` 호출 0건. 해시값 생성(`_hash`)과 버킷 인덱스 산출(`_index`, `:154-163`)이 분리되어 있다 |
| R1-6 | 체이닝 (권장: 이중 연결 리스트 재사용) | ✅ 충족 | `hashmap.py:12` 로 `DoublyLinkedList` 를 import, `:165-172` 에서 버킷마다 리스트 생성, `:62` `bucket.insert_back(...)`, `:174-180` `_find_in_bucket` 이 체인을 선형 탐색. 권장안을 그대로 따랐다 |
| R1-7 | 로드 팩터 0.75 초과 시 버킷 2배 | ✅ 충족 | `hashmap.py:34` `_LOAD_FACTOR = 0.75`, `:64-65` `if self._size > self._capacity * self._LOAD_FACTOR: self._resize(self._capacity * 2)`. **"초과"(`>`)** 조건까지 정확. `_resize`(`:196-214`)가 전 키를 새 capacity 로 **재해싱**한다. 확장 시점은 `tests/test_hashmap.py` 가 7/13/25/49 로 고정 |
| R1-8 | `push`/`pop`/`peek`/`size` | ✅ 충족 | `heap.py:35,40,54,27` — 4개 전부 존재 |
| R1-9 | `_heapify_up`/`_heapify_down` | ✅ 충족 | `heap.py:62-70`, `:72-86`. 부모 `(i-1)//2`, 자식 `2i+1`/`2i+2` 인덱스 산술 사용 |
| R1-10 | `(expire_at, key)` 형태 요소 처리 | ✅ 충족 | `mini_redis.py:318` `self._ttl_heap.push((expire_at, key))`, `:122` `expire_at, key = self._ttl_heap.peek()`. 힙은 튜플 비교만 쓰므로(`heap.py:66,79,81`) 타입 결합 없이 동작 |

#### R2. String 타입 명령어

| ID | 요구사항 (요약) | 판정 | 근거 / 비고 |
| --- | --- | --- | --- |
| R2-1 | 키 명령은 실행 전 만료 확인, 만료 키는 삭제 후 '없는 키' 취급 | ✅ 충족 | `mini_redis.py:101-109` `_get_live_entry` 가 만료 시 `_hard_delete` 후 `None` 반환. GET/DEL/EXISTS/EXPIRE/TTL 전부 이 경로를 탄다 (`:234,247,258,307,333`). 접근 없는 만료 키까지 훑어야 하는 DBSIZE/KEYS/INFO 는 `_purge_expired_via_heap()` 선행 (`:265,274,298`) |
| R2-2 | Redis 스타일 출력 `OK`/`(nil)`/`(integer) N`/`(error) ...` | ✅ 충족 | `main.py:87-113` `format_result`. 실행으로 4종 전부 확인 |
| R2-3 | SET 성공 시 `OK` | ✅ 충족 | `mini_redis.py:225` → `main.py:90-91`. 실행 확인 |
| R2-4 | 메모리 초과 시 LRU 제거 | ✅ 충족 | `mini_redis.py:213` `self._evict_to_fit(new_size)` |
| R2-5 | 덮어쓰기 시 기존 TTL 초기화 | ✅ 충족 | `mini_redis.py:208-210` 에서 기존 엔트리를 통째로 제거하고 `:222` 에서 `expire_at=None` 인 새 `_Entry` 생성. 실행 검증: `SET k1 v1` → `EXPIRE k1 100` → `TTL k1`=99 → `SET k1 v2` → **`TTL k1`=`-1`** |
| R2-6 | 없거나 만료 시 `(nil)` | ✅ 충족 | `mini_redis.py:234-236`. 실행 확인 |
| R2-7 | 존재 시 `"value"` | ✅ 충족 | `mini_redis.py:238` `('bulk', ...)` → `main.py:97` `f'"{result[1]}"'` |
| R2-8 | **반환 성공 시에만** LRU 갱신 | ✅ 충족 | `mini_redis.py:234-238` — `move_to_front` 는 `entry is None` 가드를 **통과한 뒤에만** 호출된다. 만료 삭제 경로(`:107`)는 갱신하지 않음 |
| R2-9 | DEL `(integer) 1` / `(integer) 0` | ✅ 충족 | `mini_redis.py:247-251`. 실행 확인 (연속 DEL → 1, 0) |
| R2-10 | DEL 시 LRU/TTL 구조에서도 함께 제거 | ✅ 충족 | `mini_redis.py:91-99` `_hard_delete` 가 LRU 노드 제거 + store 제거 + `used_memory` 보정. TTL 은 lazy deletion (R4-11 이 명시적으로 허용) 이며 `:129-130` 의 `expire_at` 일치 검사로 stale 이 걸러지고 `:134-155` 컴팩션이 상한을 잡는다. 실행 검증: TTL 걸린 키 DEL 후 `lru=0, store=0, used=0, TTL=-2` |
| R2-11 | EXISTS 1/0 | ✅ 충족 | `mini_redis.py:253-258` |
| R2-12 | DBSIZE `(integer) N` | ✅ 충족 | `mini_redis.py:260-266` |
| R2-13 | 전체 키를 배열 형태로 출력 | ✅ 충족 | `main.py:104-107` — `N) "key"` 형식 (명세 해설이 권장한 형식). 실행 출력 `1) "user:3"` / `2) "user:2"` |
| R2-14 | 키 없으면 `(empty array)` 류 표현 | ✅ 충족 | `main.py:102-103` — 정확히 `(empty array)`. 실행 확인 |

#### R3. 메모리 관리 + LRU 자동 제거

| ID | 요구사항 (요약) | 판정 | 근거 / 비고 |
| --- | --- | --- | --- |
| R3-1 | `bytes` 는 0 이상의 정수 | ✅ 충족 | `mini_redis.py:285-286` 음수 거부. 실행 검증: `CONFIG SET maxmemory -1` → `(error) ERR value is not an integer or out of range`, 기존 설정·데이터 불변 |
| R3-2 | 0 = 무제한 | ✅ 충족 | `mini_redis.py:65` 주석, `:164` `if self._maxmemory <= 0: return` (축출 차단), `:203`·`:217` OOM 판정도 `> 0` 가드. 실행 검증: maxmemory 0 에서 48바이트 SET 성공, 축출 0 |
| R3-3 | 성공 시 `OK`, 정수 파싱 실패 시 에러 표준 | ✅ 충족 | `main.py:206-210` → `mini_redis.py:291`. 실행 검증: `CONFIG SET maxmemory abc` → `(error) ERR value is not an integer or out of range` |
| R3-4 | `used_memory`/`maxmemory`/`evicted_keys` 3줄 출력 | ✅ 충족 | `main.py:108-112` — 정확히 3줄. 실행 출력 `used_memory:22 / maxmemory:30 / evicted_keys:1` |
| R3-5 | `used_memory = Σ(len(utf8(k)) + len(utf8(v)))` | ✅ 충족 | `mini_redis.py:74-85` — `len(s.encode('utf-8'))` 사용 (문자 수 아님). 실행 검증: `SET 안녕 하이` → `used_memory:12` (3+3+3+3) |
| R3-6 | 노드/포인터/버킷 오버헤드 제외 | ✅ 충족 | `_entry_size`(`mini_redis.py:79-85`)가 key+value 만 더한다. `_used_memory` 갱신 지점은 `:99`, `:224` 두 곳뿐이며 둘 다 `_entry_size` 기준 |
| R3-7 | maxmemory 이하가 될 때까지 LRU 부터 제거 | ✅ 충족 | `mini_redis.py:175-186` — `while used + additional > maxmemory and not lru.is_empty()` 루프로 **연쇄 축출** 가능. 희생자는 `self._lru.back()` (LRU 말단). 축출 직전 `:172` 에서 만료 키를 먼저 회수해 살아있는 키가 대신 희생되는 것을 막는다 (명세 함정 8번 대응) |
| R3-8 | 제거 키를 `evicted_keys` 에 누적 | ✅ 충족 | `mini_redis.py:186` `self._evicted_keys += 1`. 만료 삭제 경로(`_hard_delete` 단독)는 카운트하지 않으므로 오염 없음. 실행 검증: 만료 키가 낀 축출 시나리오에서 `evicted_keys:0` 유지 |
| R3-9 | 단일 엔트리 > maxmemory → 저장 안 하고 OOM | ✅ 충족 | `mini_redis.py:203-204` — **기존 키 삭제·축출보다 먼저** 검사하고 즉시 반환하므로 원자성이 지켜진다. 실행 검증: maxmemory 10, `k1="v2"` 상태에서 `SET k1 waytoolongvalueforthelimit` → OOM 출력 + `GET k1`=`"v2"` + `TTL k1`=`-1` + `evicted_keys:0` (기존 값·TTL·카운터 전부 보존) |

#### R4. TTL 관리 (힙 기반)

| ID | 요구사항 (요약) | 판정 | 근거 / 비고 |
| --- | --- | --- | --- |
| R4-1 | 없는 키 EXPIRE → `(integer) 0` | ✅ 충족 | `mini_redis.py:307-309`. 실행 확인 |
| R4-2 | seconds ≤ 0 → 즉시 만료, 존재하면 삭제 후 `(integer) 1` | ✅ 충족 | `mini_redis.py:310-313`. 실행 검증: `EXPIRE k2 0` → `(integer) 1`, 직후 `EXISTS k2` → `(integer) 0` |
| R4-3 | 정상 설정 시 `(integer) 1` | ✅ 충족 | `mini_redis.py:324`. 실행 확인 |
| R4-4 | 없는 키 TTL → `(integer) -2` | ✅ 충족 | `mini_redis.py:333-335`. 실행 확인 |
| R4-5 | 키는 있고 만료 없음 → `(integer) -1` | ✅ 충족 | `mini_redis.py:336-337`. 실행 확인 (`TTL user:3` → `-1`) |
| R4-6 | 남은 초를 `(integer) N` | ✅ 충족 | `mini_redis.py:338-341` — 내림(floor). 실행 검증 `EXPIRE user:2 3` 직후 `TTL user:2` → `(integer) 2` (명세 예시와 동일, 체크리스트는 2·3 모두 인정) |
| R4-7 | 만료 키는 GET 시 먼저 삭제 후 `(nil)`, LRU 갱신 없음 | ✅ 충족 | `mini_redis.py:105-108` (삭제) → `:234-236` (`(nil)` 반환, `move_to_front` 미도달) |
| R4-8 | SET 덮어쓰기 시 TTL 초기화 | ✅ 충족 | R2-5 와 동일 근거. 실행으로 `-1` 확인 |
| R4-9 | 없는 키 EXPIRE → `(integer) 0` | ✅ 충족 | R4-1 과 동일. 실행 검증 `EXPIRE nosuchkey 10` → `(integer) 0` |
| R4-10 | DEL 은 데이터/TTL/LRU 모두에서 제거 | ✅ 충족 | `mini_redis.py:91-99` + `:247-251`. 힙은 lazy deletion 이지만 **관측되는 상태는 완전 제거와 동일**함을 실행으로 확인 (store 0, lru 0, used 0, TTL -2). R4-11 이 이 전략을 명시적으로 허용 |
| R4-11 | 힙으로 가장 빠른 만료를 빠르게 찾을 것 | ✅ 충족 | `mini_redis.py:111-132` `_purge_expired_via_heap` 이 `peek()` 로 최소 만료를 O(1) 확인하고 미래면 즉시 break(`:123-124`). **힙이 장식이 아님을 뮤테이션으로 실증**: `MinHeap.push` 를 no-op 으로 바꾼 사본에서 **테스트 11개 실패** (아래 🧪 절). 추가로 `:134-155` 컴팩션이 stale 무한 누적을 유계화 |

#### R5. 에러 처리 표준 + CLI

| ID | 요구사항 (요약) | 판정 | 근거 / 비고 |
| --- | --- | --- | --- |
| R5-1 | `mini-redis> ` 프롬프트 | ✅ 충족 | `main.py:240` 기본 인자 `prompt='mini-redis> '` (끝 공백 포함). `tests/test_cli.py:252-270` 이 문자열을 리터럴로 고정. 실행 출력에서 확인 |
| R5-2 | 입력 읽고 파싱·실행 | ✅ 충족 | `main.py:245-285` REPL 루프 + `:25-82` 토크나이저 + `:149-235` 디스패처. `:275-284` 최상위 예외 가드로 어떤 입력에도 프로세스가 죽지 않는다 |
| R5-3 | `exit`/`quit` 종료 | ✅ 충족 | `main.py:160-161` (대소문자 무관). EOF(`:248-250`)·Ctrl+C(`:251-254`)도 처리. 실행 확인 |
| R5-4 | `(error) ERR unknown command '<cmd>'` | ✅ 충족 | `main.py:235`. 실행 출력 `(error) ERR unknown command 'HELLO'` — 명세 예시와 바이트 단위 일치 |
| R5-5 | `(error) ERR wrong number of arguments for '<cmd>' command` | ✅ 충족 | `main.py:118-119` — 꼬리 ` command` 포함. 실행 출력 `(error) ERR wrong number of arguments for 'GET' command` 일치 |
| R5-6 | `(error) ERR value is not an integer or out of range` | ✅ 충족 | `mini_redis.py:37` 상수 단일 정의, `main.py:209,227` 에서 사용. `_parse_int`(`main.py:130-146`)가 `1_000`·`" 12 "`·`1e3`·유니코드 숫자·int64 범위 초과를 전부 거부. 실행 확인 |
| R5-7 | `(error) OOM command not allowed when used_memory > 'maxmemory'` | ✅ 충족 | `mini_redis.py:38` — **`ERR` 가 아니라 `OOM` 으로 시작**, `'maxmemory'` 작은따옴표까지 정확. 실행 출력 일치 |
| R5-8 | `"Alice"` 같은 따옴표 입력 허용 | ✅ 충족 | `main.py:40-69` — 큰따옴표 묶음 + `\"`/`\\`/`\n`/`\t` 이스케이프. 실행 검증: `SET k "hello world"` → `GET k` → `"hello world"` (공백 보존). 따옴표는 파싱에서 벗겨져 `used_memory` 에 포함되지 않음 (`"Bob"`→3바이트, 실행 `used_memory:22` 로 확인) |
| R5-9 | 공백 없는 값 / 큰따옴표 값 중 하나 지원 | ✅ 충족 | `main.py:70-81`(공백 없는 값) + `:40-69`(따옴표) — **둘 다** 지원 |

#### 보너스 과제

| ID | 요구사항 (요약) | 판정 | 근거 / 비고 |
| --- | --- | --- | --- |
| B1 | 동적 배열 직접 구현 (`append`/`get`/`set`/`remove` + capacity 2배 확장) | ❌ 미충족 | 저장소 전체에 동적 배열 클래스 없음 (`DynamicArray`/`dynamic_array` grep 0건). 힙 백업 저장소는 파이썬 `list` 의 `append`/`pop` 에 의존한다 (`heap.py:22,37,48`) — B1 이 겨냥한 바로 그 지점이 미대체 상태 |
| B2 | `STACK_QUEUE_DEQUE.md` 작성 | ❌ 미충족 | 파일 없음 (`ls -a` 로 확인, 저장소 내 `.md` 는 `README.md` 하나). README 에도 스택/큐/덱 서술 없음 |
| B3 | 이진 트리 + 전위/중위/후위/레벨 순회 | ❌ 미충족 | 트리 클래스·순회 함수 없음. `heap.py:3` 의 "완전 이진 트리" 는 서술 한 줄일 뿐 구현이 아니다 |
| B4 | BST 삽입/탐색/삭제 + 중위 순회 정렬 | ❌ 미충족 | grep 0건 |
| B5 | `PUBLISH`/`SUBSCRIBE` 채널 메시징 | ❌ 미충족 | `main.py:163-235` 디스패처에 해당 명령 없음. `PUBLISH`/`SUBSCRIBE` grep 0건 |

#### 🔍 발견된 격차와 보완 제안

**필수 요구사항(R1~R5, C1~C8)에서 부분/미충족 항목은 없다.** 53개 전부 코드 근거 + 실행 검증으로 확인했고, 명세가 "자주 놓치는 함정"으로 꼽은 12개 항목(덮어쓰기 TTL 소멸, 만료 GET 의 LRU 비갱신, `maxmemory 0`=무제한, UTF-8 바이트, OOM 은 거절이지 축출이 아님, `-1`/`-2` 구분, 에러 문자열 꼬리·접두어, 축출 전 만료 회수, DBSIZE/KEYS/INFO 의 만료 제외, REPL 무사망, `{}` 리터럴, 힙이 장식이 아닐 것)도 모두 방어되어 있다. 특히 8·9·12번은 대부분의 제출물이 놓치는 지점인데 전용 회귀 테스트와 컴팩션까지 갖췄다.

아래는 남은 격차다.

1. **보너스 5개 전부 미구현 (B1~B5) — 선택 항목이므로 감점 사유는 아니다.**
   - 가장 저렴한 것은 **B2** 다. `STACK_QUEUE_DEQUE.md` 한 파일이면 되고, 저장소에 이미 재료가 있다 — TTL 힙이 우선순위 큐, `DoublyLinkedList` 가 덱의 완전한 구현체(`insert_front`/`insert_back`/`remove_front`/`remove_back` 4연산이 곧 덱 API)다. "이 저장소의 어떤 코드가 스택/큐/덱으로 이미 동작하는가" 를 파일:라인으로 짚으면 문서가 채워진다.
   - **B1** 은 `heap.py:22` 의 `list` 를 `DynamicArray` 로 갈아끼우면 끝난다. `append`/`get`/`set`/`remove` + capacity 2배 확장을 만들고 `MinHeap._data` 를 교체하면, 힙 테스트 `tests/test_heap.py` 가 그대로 회귀 검증이 된다. 덤으로 `hashmap.py:169` 의 `[None] * capacity` 도 같은 클래스로 통일할 수 있어 "내장 자료형 의존"이 한 단계 더 걷힌다.
   - **B3/B4** 는 독립 모듈(`binary_tree.py`, `bst.py`) 추가. 힙이 "완전 이진 트리의 배열 표현"이라는 관점과 대조하면 학습 효과가 크다.
   - **B5** 는 `HashMap<channel → DoublyLinkedList>` 로 구독자 버퍼를 만들면 되고, 연결 리스트를 메시지 큐로 재활용하라는 명세 의도와 정확히 맞는다.

2. **README 에 과제 명세(0절)가 아직 없다 — 경미.**
   `README.md` 는 `# Mini Redis` 로 바로 시작하고, 요구사항 원문·학습 지도·제약 사항이 들어 있지 않다. 구현 설명·설계 근거·체크포인트는 대단히 충실하지만, "이 과제가 무엇을 요구했는가" 를 README 만 보고는 역추적할 수 없다. 추출된 명세 문서를 README 최상단에 `## 0. 과제 명세` 로 붙이면 해결된다.

3. **README 의 뮤테이션 수치가 실측과 어긋난다 — 경미.**
   `README.md` 의 "특히 `MinHeap.push` 를 no-op 으로 바꾸면 **9개** 테스트가 실패한다" 는 서술에 대해, 실제로 사본에서 `push` 를 no-op 으로 만들어 돌린 결과는 **11개 실패**였다. 주장보다 강한 방향의 오차라 결론(힙이 실동작 경로에 있다)은 그대로 성립하지만, 문서에 박아 둔 실측치는 재측정해 갱신하는 편이 낫다.

4. **참고(결함 아님) — `_evict_to_fit` 의 무제한 모드 조기 반환.**
   `mini_redis.py:164` 가 `maxmemory <= 0` 일 때 만료 회수 없이 반환하므로, 무제한 모드에서는 `SET` 이 만료 키를 회수하지 않는다. 다만 `DBSIZE`/`KEYS`/`INFO memory` 가 `_purge_expired_via_heap()` 을 먼저 부르고(`:265,274,298`) 힙 상한은 `cmd_expire` 의 컴팩션(`:323`)이 지키므로 **외부에서 관측되는 출력은 명세와 어긋나지 않는다.** 꼬리 지연을 막기 위한 의도된 트레이드오프이며 README 에 근거와 실측(만료 키 5만 개 기준 1.5초)까지 명시되어 있다. 정공법은 active expire cycle 이고 README 가 이미 그 경로를 적어 두었다.

#### 🧪 실행 검증 기록

모두 네트워크·설치 없이, 저장소를 변경하지 않고 수행했다. (뮤테이션 검증만 scratchpad 사본에서 수행)

**1) 컴파일 — 통과**
```
$ python3 -m py_compile main.py mini_redis.py hashmap.py heap.py linked_list.py tests/*.py
COMPILE OK      (python3 3.14.4)
```

**2) 테스트 스위트 — 105개 전부 통과**
```
$ python3 -m unittest discover -s tests -t .
Ran 105 tests in 0.353s
OK
```
표준 라이브러리(`unittest`)만 사용하며 외부 의존성 없음. `FakeClock` 주입(`tests/helpers.py:15-30`)으로 TTL 테스트가 `sleep` 없이 결정적으로 돈다.

**3) 금지 자료형 AST 검사 — 위반 0건 (독립 스크립트로 재확인)**
저장소의 자체 검사(`tests/test_cli.py:286-323`)를 신뢰하지 않고, 별도 스크립트로 전 `.py` 파일을 AST 파싱해 `Name`/`Attribute`/`Dict`/`Set`/`DictComp`/`SetComp`/`collections` import 를 검사했다.
```
TOTAL BANNED HITS: 0
```

**4) 명세 실행 예시(0.7절) 재현 — 완전 일치**
```
$ printf 'CONFIG SET maxmemory 30\nSET user:1 "Alice"\n...' | python3 main.py
mini-redis> OK
mini-redis> OK / OK / OK
mini-redis> (nil)                      # GET user:1 → LRU 축출됨
mini-redis> used_memory:22
maxmemory:30
evicted_keys:1
mini-redis> 1) "user:3"
2) "user:2"
mini-redis> (integer) 1                # EXPIRE user:2 3
mini-redis> (integer) 2                # TTL user:2
```
`used_memory:22`, `evicted_keys:1` 이 명세 예시와 정확히 같다.

**5) 에러 문자열 4종 — 명세와 바이트 단위 일치**
```
(error) ERR unknown command 'HELLO'
(error) ERR wrong number of arguments for 'GET' command
(error) ERR value is not an integer or out of range
(error) OOM command not allowed when used_memory > 'maxmemory'
```

**6) R3-9 원자성 실검증 — 통과**
`CONFIG SET maxmemory 10` → `SET k1 v1` → `EXPIRE k1 100`(TTL 99) → `SET k1 v2`(TTL `-1`) → `SET k1 waytoolongvalueforthelimit`
→ OOM 출력, `GET k1`=`"v2"`, `TTL k1`=`-1`, `INFO memory` 의 `evicted_keys:0`.
**거절 시 기존 값·TTL·카운터가 전부 보존**된다.

**7) 만료 키의 축출 오염 실검증 — 통과**
maxmemory 20, `a`(TTL 만료됨) + `b` 상태에서 `SET c 3` 실행 → `evicted_keys:0`, 살아있는 `b` 보존, 만료된 `a` 만 사라짐. 명세 함정 8번이 요구하는 동작.

**8) 불변식 퍼징 (자체 작성, 30 trial × 400 step = 12,000 연산) — 통과**
랜덤 SET/GET/DEL/EXPIRE/TTL/DBSIZE/KEYS/INFO + 시계 전진을 섞어 돌린 뒤 매 trial 마다 검사:
- `used_memory == Σ(len(utf8(k)) + len(utf8(v)))` (실제 생존 키 재계산과 일치)
- `len(LRU 리스트) == HashMap.size()` (세 구조 간 일관성)
- `maxmemory > 0` 이면 `used_memory <= maxmemory`
```
fuzz OK: used_memory / LRU-store 일치 / maxmemory 상한 전부 성립
```

**9) 뮤테이션 검증 — 힙이 실동작 경로에 있음 (명세 함정 12번)**
저장소를 건드리지 않기 위해 scratchpad 사본에서 `MinHeap.push` 를 no-op 으로 치환 후 테스트 실행:
```
Ran 105 tests ... FAILED (failures=11)
```
힙을 무력화하면 11개 테스트가 깨진다 = **힙이 장식이 아니라 TTL 동작 경로에 실제로 놓여 있다.** (README 는 9개라고 적어 두었으나 실측은 11개)

**10) 추가 엣지 입력 — REPL 무사망 확인**
빈 줄 / 공백만 / 닫히지 않은 따옴표(`SET k "abc`) / `EXPIRE k 1e3` / `EXPIRE k 10^400` / `KEYS *` / `DBSIZE x` / `INFO cpu` / `CONFIG GET maxmemory` / 빈 문자열 키(`SET "" v`) / 빈 문자열 값 / EOF — 전부 에러 메시지 출력 후 프롬프트로 복귀하거나 정상 종료. traceback 0건.

**미실행 항목:** 없음. 외부 계정·서버·네트워크가 필요한 요구사항이 이 과제에는 존재하지 않아 `⬜ 로컬 검증 불가` 판정은 0건이다.

---

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
  이렇게 얻은 64비트 해시값을 `% capacity`로 접어 버킷 인덱스를 만든다.
  `capacity`는 항상 2의 거듭제곱이라 이 나머지 연산은 사실상 **하위
  `log2(capacity)`비트만 취하는 것**과 같다
- **왜 FNV-1a인가**: XOR을 곱셈 *앞*에 둔다. 바이트를 먼저 섞어 넣고 곱하면
  그 바이트가 곱셈의 자리올림을 타고 상위 비트까지 퍼지지만, 원조 FNV-1
  (곱한 뒤 XOR)은 마지막 바이트가 XOR된 자리에만 남는다
- **분포 실측** (키 1.2만 개, `capacity` 16384, 로드 팩터 0.73 — 확장 직전의
  가장 빡빡한 조건). 기준선은 이상적 난수 해시를 200회 시뮬레이션한
  `chi2/df` 0.966~1.025, 최장 체인 6:

  | 키 집합 | `chi2/df` | 최장 체인 |
  | --- | --- | --- |
  | `key:0` ~ `key:11999` | 0.921 | 5 |
  | `user:1` ~ `user:12000` | 1.165 | 7 |
  | 랜덤 8자 | 0.996 | 6 |
  | 31자 공통 접두사 + 3자 | **1.552** | 5 |

  구조적인 키는 균등도가 기준선을 벗어나지만 **최장 체인은 5~7로 이상적 난수
  해시와 같다.** 체이닝 조회가 O(n)으로 무너지는 일은 이 부하에서 일어나지 않는다
- **알려진 약점과 판단**: 마지막 바이트만 다른 키(위 표 4행)는 곱셈을 한 번밖에
  거치지 못하고 `FNV_PRIME`의 set bit가 7개뿐이라 확산이 부족하다. 마지막
  바이트에서 1비트를 바꿨을 때 달라지는 해시 비트가 평균 **9.4/64**다(첫 바이트를
  바꾸면 이상치 32에 근접). `h ^= h >> 32` 한 줄(xor-fold)을 더하면 균등도가
  1.552 → 0.851로 기준선 안에 들어오지만 **최장 체인은 5 그대로**라 실측 이득이
  없어서 넣지 않았다. 부하가 더 높거나 키가 더 구조적이면 다시 볼 지점이다.
  덧붙여 FNV-1a는 seed 없는 해시라 **의도적 충돌 공격은 막지 못한다** —
  공개 서버라면 SipHash 같은 keyed hash가 필요하다
- **충돌 해결**: 체이닝. 각 버킷이 이중 연결 리스트를 가짐
- **노드 정책**: 새 키는 노드를 새로 만들고, 같은 키 덮어쓰기는 노드를 재사용해
  `data` 튜플만 바꾼다. 삭제는 `remove_node`가 앞뒤를 다시 이은 뒤
  `prev`/`next`/`owner`를 전부 `None`으로 끊어서, 제거된 노드가 리스트를 붙들지
  않게 하고 이중 삭제도 무해하게 만든다. 노드 풀(free list)은 두지 않고 파이썬
  GC에 맡긴다. `_resize`는 노드를 재사용하지 않아 재배치마다 노드 n개가 새로 생긴다
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

## 설계 확장 노트

과제 범위 밖이지만 "이 구조를 실제로 키우면 어디가 먼저 무너지는가"를 정리해
둔다. 아래 세 절이 학습 체크포인트 7·8·9번의 답이다.
측정은 전부 Python 3.14 / 키 10만 개 기준이다.

### 1) LRU 대신 LFU를 구현한다면

**빈도 카운트를 어디에 두나.** `_Entry`에 필드로 붙인다
([mini_redis.py](mini_redis.py)의 `__slots__`에 `freq` 추가). 갱신 지점은 지금
`move_to_front`를 부르는 자리와 정확히 같다 — `cmd_get`의 성공 경로 한 곳뿐이고,
`SET`은 신규 삽입이므로 초기값을 준다.

**자료구조는 어떻게 바뀌나.** LRU 리스트 하나로는 "빈도가 가장 낮은 키"를 O(1)에
찾을 수 없다. 두 가지 선택지가 있다.

| 방식 | 축출 대상 찾기 | 접근 시 갱신 | 비고 |
| --- | --- | --- | --- |
| 최소 힙에 `(freq, key)` | O(log n) | O(log n) + stale 누적 | **이미 있는 TTL 힙과 같은 패턴.** 무조건 push하고 pop 때 현재 `freq`와 일치하는지 검사, 컴팩션으로 상한 유지 |
| 빈도별 리스트 버킷 | **O(1)** | **O(1)** | `HashMap<freq → DoublyLinkedList>` + `_min_freq` 정수 |

두 번째가 정석이고, **이 저장소는 이미 필요한 부품을 다 갖고 있다.**
접근이 일어나면 `f` 리스트에서 `remove_node`, `f+1` 리스트에 `insert_front`.
축출은 `_min_freq` 리스트의 `back()`. `DoublyLinkedList`가 sentinel 기반 O(1)
제거/삽입을 제공하고, "해시맵 엔트리가 자기 노드 참조를 들고 있어 탐색이 필요
없다"는 지금 `_Entry.lru_node`의 구조가 그대로 쓰인다. 리스트를 하나에서
빈도별 여러 개로 늘리는 것이 변경의 전부다. `_min_freq`는 축출 직후와
`f == _min_freq`인 리스트가 비었을 때만 올려주면 되므로 스캔이 필요 없다.

같은 빈도 안에서는 리스트 순서가 그대로 최근성이라 **LFU + 동률 시 LRU**
타이브레이크가 공짜로 따라온다.

**진짜 어려운 건 자료구조가 아니라 정책이다.** 카운트를 단순 증가시키면:

- **캐시 오염** — 과거 한때 뜨거웠던 키가 카운터를 쌓아둔 채 영원히 축출되지
  않는다. 실제 Redis는 8비트 **로그 확률 카운터**(`lfu-log-factor`)로 증가를
  포화시키고 `lfu-decay-time`(분 단위)마다 감쇠시킨다. 24비트 LRU 필드를
  16비트 최종 접근 분 + 8비트 카운터로 쪼개 쓴다.
- **신규 키 역차별** — `freq = 1`로 시작하면 갓 들어온 키가 즉시 축출 1순위라
  자리를 잡지 못한다. Redis는 신규 키를 `LFU_INIT_VAL = 5`에서 출발시켜 유예를 준다.

**바뀌지 않는 것.** `_hard_delete`의 `used_memory` 회계, `evicted_keys` 계상,
**축출 직전 만료 회수 순서**, TTL 힙은 전부 그대로다. `_evict_to_fit`에서
희생자를 고르는 한 줄(`self._lru.back()`)만 교체된다. 테스트는 LRU 순서를
검증하는 것들만 빈도 기준으로 다시 쓰면 된다.

### 2) 데이터가 10만 건으로 늘어나면

| 병목 | 실측 | 원인 | 완화 |
| --- | --- | --- | --- |
| **일괄 rehash** | 단일 `SET` **269 ms** (98,304번째 삽입. p50 4.4 µs의 **6만 배**) | `_resize`가 10만 키를 한 번에 재배치 | incremental rehash |
| **빈 버킷 선할당** | 빈 버킷 179,706개 = 객체 539,118개 = **31.5 MB** (`used_memory`는 0.94 MB) | `_make_buckets`가 버킷마다 리스트 + sentinel 2개를 미리 만든다 | 지연 할당 |
| **TTL 힙 컴팩션** | 1회 **293 ms** (그중 163 ms가 불필요한 재해싱) | `_maybe_compact_ttl_heap`이 `keys()` 스냅샷을 만든 뒤 키마다 `get()`으로 **다시 해싱**한다 | 내부 `items()` 이터레이터 |
| **미접근 만료 키** | — | 무제한 모드 `SET`은 회수하지 않는다(의도된 트레이드오프) | active expire cycle |
| **단일 스레드** | — | 모든 명령이 한 스레드에서 직렬 처리 | 샤딩 |

상각 복잡도는 전부 O(1)이 맞다. **무너지는 건 평균이 아니라 꼬리 지연이다.**
269 ms 동안 서버는 다른 명령을 하나도 처리하지 못한다.

- **incremental rehash** — 새 테이블을 만들되 옛 테이블을 즉시 버리지 않고,
  명령 하나마다 버킷 몇 개씩만 옮긴다(Redis의 `rehashidx`). 조회는 두 테이블을
  모두 본다. 최악 지연이 O(n) → O(1)이 되는 대신 `get`/`put`/`keys` 전부에
  "이사 중" 분기가 생긴다.
- **지연 할당** — 버킷을 `None`으로 두고 첫 삽입에서만 `DoublyLinkedList`를
  만든다. `_find_in_bucket`·`keys()`·`_resize`가 `None`을 건너뛰면 되고, 위
  31.5 MB와 `keys()` 순회 비용이 함께 줄어든다. **변경 범위 대비 효과가 가장 좋다.**
- **active expire cycle** — 회수 예산 상한을 둔 주기적 만료 처리(Redis는 100 ms
  주기로 20개 표본, 그중 25% 이상이 만료면 반복). 접근이 없어도 만료 키가 조금씩
  회수되면서 단일 명령 지연은 억제된다. 지금 "무제한 모드의 회수는 조회 명령이
  맡는다"는 절충을 대체하는 정공법이다.
- **샤딩** — 키 해시 상위 비트로 N개 샤드를 나누고 각 샤드가 자기 `HashMap`·LRU
  리스트·TTL 힙·`used_memory`를 갖는다. rehash 스파이크가 1/N로 쪼개지고
  (269 ms → 16샤드면 약 17 ms) 스레드·프로세스로 병렬화할 길이 열린다.
  **대신 전역 LRU를 포기해야 한다** — `maxmemory`는 전역인데 축출 판정은 샤드
  로컬이라, 샤드별 쿼터로 나누면 "전체에서 가장 오래된 키"가 아니라 "그 샤드에서
  가장 오래된 키"가 희생된다. 실제 Redis Cluster도 노드별로 독립 축출한다.
  이 구현의 `used_memory`·`evicted_keys` 불변식 테스트는 전역 합산으로 다시 써야 한다.

### 3) `used_memory`에 자료구조 오버헤드를 포함한다면

지금은 순수 페이로드 모델이다: `Σ(len(utf8(key)) + len(utf8(value)))`
(`_entry_size`). 실제 Redis는 allocator 실사용량이라 오버헤드를 포함한다.

**얼마나 차이 나나.** 엔트리 하나당 `_Entry` + LRU `Node` + 버킷 `Node` +
`(key, value)` 튜플 = **256 B**인데 같은 엔트리의 페이로드는 **6 B**다
(`SET key:0 v` 기준, TTL이 걸리면 힙 항목 64 B 추가). 여기에 **엔트리 수에
비례하지 않는** 버킷 테이블 몫(위 31.5 MB)이 따로 붙는다.

**보정이 왜 어려운가.** 상수 오버헤드를 `_entry_size`에 더하는 건 쉽다.
문제는 버킷 테이블이다.

1. 테이블은 rehash에서 한 번에 2배가 된다. `used_memory`가 `SET` 하나로 계단식
   점프하고 **그 점프가 축출을 유발한다.** 축출로 키가 줄면 `_maybe_shrink`가
   테이블을 되돌리고 `used_memory`가 다시 내려가는 되먹임이 생긴다. 진동을
   막으려면 축소 임계를 더 벌리거나 축출 판정에서 테이블 몫을 빼야 한다.
2. `_resize`는 `HashMap.put()` 안에서 일어난다. 거기서 `used_memory`를 갱신하고
   `_evict_to_fit`을 부르려면 **`HashMap`이 `MiniRedis`를 되불러야 한다** —
   단방향 의존(`main → mini_redis → hashmap`)이 깨진다. 콜백을 주입하거나
   `cmd_set`이 `put()` 전후로 `capacity()` 변화를 감지해 보정하는 우회가 필요하다.
3. `sys.getsizeof` 실측값은 파이썬 버전·플랫폼마다 다르다. `used_memory` 불변식
   퍼징(3000스텝)이 환경 의존이 되어 회귀 테스트로서 죽는다.

**채점에 미치는 영향이 결정적이다.** 명세 실행 예시는 `CONFIG SET maxmemory 30`
에서 11바이트짜리 키 3개로 `used_memory:22`, `evicted_keys:1`을 요구한다.
오버헤드를 포함하면 엔트리 하나가 이미 256 B라 **첫 `SET`부터 OOM**이고,
명세에 박힌 `30`을 바꿀 수 없으므로 예시 재현이 원천적으로 불가능하다.

**그래서 이 구현은 순수 페이로드를 택했다.** 목적이 다르기 때문이다 — 실제
Redis는 서버가 자기 메모리를 지키는 것이 목적이고, 여기서는 명세 재현성과
결정성이 목적이다.

**그래도 바꾼다면** Redis와 같은 분리 보고가 권장 경로다. 축출 판정은 페이로드
기준을 유지해 명세 예시를 살리고, 오버헤드는 (`sys.getsizeof`가 아니라) 고정
상수 모델로 계산해 `INFO memory`에 별도 필드로 낸다 — Redis의
`used_memory_overhead`가 정확히 그것이다. 관측치는 풍부해지고 채점은 깨지지 않는다.

## 학습 체크포인트

이 과제를 마친 뒤 아래 질문에 **코드의 파일:라인을 지목하며** 답할 수 있어야 한다.

1. FNV-1a 해시는 충돌을 어떻게 줄이는가? 해시값 생성과 인덱스 산출은 어떻게 나뉘는가?
   충돌이 났을 때 체이닝은 어떤 비용을 가지는가? FNV-1a가 못 하는 것은 무엇인가?
   (답: 위 "자료구조 설명" 2절)
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
   빈도 카운트는 어디에 저장하고, 카운터를 단순 증가시키면 무엇이 망가지는가?
   (답: 위 "설계 확장 노트" 1절)
8. 데이터가 10만 건으로 늘어나면 현재 구조에서 병목은 어디인가?
   상각 복잡도가 O(1)인데도 왜 문제가 되는가? 샤딩으로 나누면 무엇을 잃는가?
   (답: 위 "설계 확장 노트" 2절)
9. `used_memory`에 자료구조 오버헤드를 포함하면 무엇이 깨지는가?
   그래도 포함하려면 어떻게 보정해야 하는가? (답: 위 "설계 확장 노트" 3절)
