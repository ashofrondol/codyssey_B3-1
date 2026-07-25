"""Mini Redis 본체.

세 가지 자료구조를 조합해 동작한다.
    - HashMap          : key -> _Entry 매핑 (메인 저장소)
    - DoublyLinkedList : LRU 추적 (앞 = MRU, 뒤 = LRU)
    - MinHeap          : (expire_at, key) 형태의 TTL 만료 시간 우선순위

각 명령 메서드는 결과를 '튜플' 형태로 반환한다. CLI 레이어가 이 튜플을
Redis 스타일 문자열로 변환해 출력한다. 자료구조 계층과 출력 계층을
분리해 두면 테스트하기도 쉽고 출력 형식이 바뀌어도 본체는 안 건드린다.

반환 튜플 종류:
    ('ok',)                      -> "OK"
    ('nil',)                     -> "(nil)"
    ('int', n)                   -> "(integer) n"
    ('bulk', s)                  -> "\"s\""
    ('array', [..])              -> 줄바꿈으로 구분된 목록
    ('info', used, max, evict)   -> INFO memory 출력
    ('error', msg)               -> "(error) msg"

만료 키에 대한 불변식:
    만료 시각이 지난 키는 '접근 여부와 무관하게 논리적으로 존재하지 않는다'.
    DBSIZE / KEYS / used_memory / eviction 판정 어디에도 포함되지 않으며,
    만료로 사라진 키는 evicted_keys에 계상하지 않는다. 내부적으로는 lazy
    deletion을 쓰지만, 외부에서 관측되는 출력은 항상 이 규칙과 같아야 한다.
"""

import time

from hashmap import HashMap
from heap import MinHeap
from linked_list import DoublyLinkedList


class _Entry:
    """저장소 내부에서 키 하나를 표현하는 객체."""

    __slots__ = ('key', 'value', 'lru_node', 'expire_at')

    def __init__(self, key, value, lru_node, expire_at=None):
        self.key = key
        self.value = value
        self.lru_node = lru_node  # LRU 리스트에서 이 키를 가리키는 노드(O(1) 제거/이동용)
        self.expire_at = expire_at  # 절대 만료 시각(time.time 기준). None이면 만료 없음


class MiniRedis:
    """Mini Redis 코어 엔진."""

    _OOM_MSG = "OOM command not allowed when used_memory > 'maxmemory'"
    _RANGE_MSG = 'ERR value is not an integer or out of range'

    # TTL 힙이 '살아있는 키 수'의 몇 배를 넘으면 재구축할지. 재구축 사이에
    # 힙이 최소 2배로 벌어져야 하므로 상각 비용은 O(log n)에 머문다.
    _TTL_HEAP_SLACK = 2
    _TTL_HEAP_FLOOR = 32

    def __init__(self, now_fn=time.time):
        self._store = HashMap()
        self._lru = DoublyLinkedList()
        self._ttl_heap = MinHeap()
        self._maxmemory = 0        # 0이면 무제한
        self._used_memory = 0
        self._evicted_keys = 0
        self._now_fn = now_fn      # 테스트 주입용
        # 다음 컴팩션을 유발하는 힙 크기. 재구축 때마다 살아있는 TTL 항목 수에 맞춰 갱신된다.
        self._ttl_heap_limit = self._TTL_HEAP_FLOOR

    # ---------- helpers ----------

    @staticmethod
    def _utf8_len(s):
        """문자열의 UTF-8 인코딩 바이트 길이."""
        return len(s.encode('utf-8'))

    def _entry_size(self, key, value):
        """엔트리 하나가 차지하는 것으로 계산되는 바이트 수.

        스펙: used_memory = Σ( len(utf8(key)) + len(utf8(value)) )
        자료구조(노드/포인터/버킷) 오버헤드는 의도적으로 제외한다.
        """
        return self._utf8_len(key) + self._utf8_len(value)

    def _is_expired(self, entry):
        """엔트리의 만료 시각이 이미 지났으면 True."""
        return entry.expire_at is not None and entry.expire_at <= self._now_fn()

    def _hard_delete(self, key, entry):
        """저장소/LRU에서 엔트리를 제거하고 메모리 사용량을 보정한다.

        TTL 힙의 stale 항목은 lazy deletion으로 추후 정리한다
        (힙에서 임의 항목을 찾아 지우면 O(n)이 되기 때문).
        """
        self._lru.remove_node(entry.lru_node)
        self._store.remove(key)
        self._used_memory -= self._entry_size(key, entry.value)

    def _get_live_entry(self, key):
        """만료된 키는 그 자리에서 제거하고, 살아 있는 엔트리만 반환한다."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            self._hard_delete(key, entry)
            return None
        return entry

    def _purge_expired_via_heap(self):
        """힙의 머리부터 만료된 항목을 정리(lazy deletion).

        같은 키에 EXPIRE를 다시 걸면 힙에 새 항목이 추가되고 옛 항목은 남는다.
        그래서 pop 후에는 항상 '현재 엔트리의 expire_at과 일치하는지' 확인하여
        오래된(stale) 항목을 걸러낸다.

        만료 항목이 없으면 peek 1회로 즉시 빠져나오므로 호출 비용은 사실상 0이다.
        """
        now = self._now_fn()
        while not self._ttl_heap.is_empty():
            expire_at, key = self._ttl_heap.peek()
            if expire_at > now:
                break
            self._ttl_heap.pop()
            entry = self._store.get(key)
            if entry is None:
                continue  # 이미 DEL 등으로 제거됨
            if entry.expire_at != expire_at:
                continue  # 이미 다른 TTL로 갱신됨 (오래된 항목)
            self._hard_delete(key, entry)
        self._maybe_compact_ttl_heap()

    def _maybe_compact_ttl_heap(self):
        """stale 항목이 지나치게 쌓인 TTL 힙을 살아있는 엔트리만으로 재구축한다.

        같은 키에 EXPIRE를 반복하거나, TTL이 걸린 키를 DEL/eviction으로 지우면
        힙에는 아무도 회수하지 않는 항목이 남는다. 만료 시각이 먼 미래라면
        _purge_expired_via_heap이 건드리지도 못해 무한정 누적된다.

        임계는 '전체 키 수'가 아니라 '직전 재구축에서 실제로 살아남은 TTL 항목
        수'를 기준으로 잡는다. TTL 없는 키가 대다수인 저장소에서 상한이 필요
        이상으로 커지는 것을 막는다. 재구축 사이에 힙이 최소 2배로 벌어져야
        하므로 상각 비용은 push당 O(log n)에 머문다.
        """
        if self._ttl_heap.size() <= self._ttl_heap_limit:
            return
        fresh = MinHeap()
        for key in self._store.keys():
            entry = self._store.get(key)
            if entry is not None and entry.expire_at is not None:
                fresh.push((entry.expire_at, key))
        self._ttl_heap = fresh
        self._ttl_heap_limit = max(self._TTL_HEAP_FLOOR,
                                   self._TTL_HEAP_SLACK * fresh.size())

    def _evict_to_fit(self, additional_size):
        """maxmemory 제한 안에 들어갈 때까지 LRU(맨 뒤)부터 제거한다."""
        # 무제한 모드에서는 축출 자체가 없으므로 여기서 만료를 회수할 이유가 없다.
        # 가드보다 앞에 두면 무제한 SET 한 번이 '그동안 만료된 키 전부'를 회수하며
        # 통째로 멈춘다(만료 키 5만 개 기준 약 1.5초 측정). 무제한 모드의 만료
        # 회수는 DBSIZE/KEYS/INFO가 담당하고, 힙 상한은 cmd_expire의 컴팩션이
        # 지키므로 여기서 빠져도 관측되는 동작은 달라지지 않는다.
        if self._maxmemory <= 0:
            return
        # 만료됐지만 아직 lazy 정리되지 않은 키가 _used_memory와 LRU에 남아 있으면
        #   (1) 필요 없는 축출이 촉발되고
        #   (2) 죽은 키 대신 살아있는 키가 희생되며
        #   (3) 그 삭제가 evicted_keys에 잘못 집계된다.
        # 희생자를 고르기 전에 반드시 먼저 회수한다. 이 경로의 회수량은
        # maxmemory 안에 들어갈 수 있는 키 수로 자연히 상한이 잡힌다.
        self._purge_expired_via_heap()
        # 여기 도달하는 희생자는 정의상 전부 '살아있는' 키이므로
        # evicted_keys 증가에 별도 분기가 필요 없다.
        while (self._used_memory + additional_size > self._maxmemory
               and not self._lru.is_empty()):
            tail_node = self._lru.back()
            victim_key = tail_node.data
            victim = self._store.get(victim_key)
            if victim is None:
                # 방어적 정리: LRU에는 있는데 store에 없는 일은 정상 흐름에선 없어야 하지만
                # 어떤 경로로든 어긋났다면 노드만 제거하고 진행한다.
                self._lru.remove_node(tail_node)
                continue
            self._hard_delete(victim_key, victim)
            self._evicted_keys += 1

    # ---------- commands ----------

    def cmd_set(self, key, value):
        """key에 value를 저장한다.

        기존 키를 덮어쓰는 경우 기존 TTL은 초기화(삭제)된다.
        저장 후 maxmemory를 초과하면 초과분이 해소될 때까지 LRU부터 축출한다.
        단일 엔트리 자체가 maxmemory보다 크면 아무것도 바꾸지 않고 OOM을 반환한다.
        반환: ('ok',) | ('error', OOM)
        """
        new_size = self._entry_size(key, value)

        # 단일 엔트리 자체가 maxmemory보다 크면 저장하지 않고 OOM.
        # 이때 축출을 시도하지 않으므로 기존 키/값/TTL은 전부 그대로 살아남고
        # evicted_keys도 변하지 않는다.
        if self._maxmemory > 0 and new_size > self._maxmemory:
            return ('error', self._OOM_MSG)

        # 기존 키가 있고 만료되지 않았다면 먼저 제거한다.
        # (덮어쓰기 시 기존 TTL 초기화 → 새 엔트리는 expire_at=None이므로 자연 만족)
        existing = self._get_live_entry(key)
        if existing is not None:
            self._hard_delete(key, existing)

        # 들어올 크기만큼 자리를 만든다(만료 회수 후 LRU 축출)
        self._evict_to_fit(new_size)

        # 안전망: 모두 비웠는데도 안 들어간다면 OOM (이 분기는 사실상
        # 첫 줄의 단일 엔트리 검사로 이미 걸러진다)
        if self._maxmemory > 0 and self._used_memory + new_size > self._maxmemory:
            return ('error', self._OOM_MSG)

        # 신규/덮어쓰기와 무관하게 SET은 해당 키를 MRU로 만든다.
        lru_node = self._lru.insert_front(key)
        entry = _Entry(key, value, lru_node, expire_at=None)
        self._store.put(key, entry)
        self._used_memory += new_size
        return ('ok',)

    def cmd_get(self, key):
        """key의 값을 반환한다.

        만료된 키는 먼저 삭제한 뒤 ('nil',)을 돌려주며,
        이 경로에서는 LRU를 갱신하지 않는다(명세 규정).
        반환: ('bulk', value) | ('nil',)
        """
        entry = self._get_live_entry(key)
        if entry is None:
            return ('nil',)
        self._lru.move_to_front(entry.lru_node)
        return ('bulk', entry.value)

    def cmd_del(self, key):
        """key를 삭제한다. 데이터/LRU에서 즉시 제거되고 TTL은 무효화된다.

        (힙의 stale 항목은 expire_at 일치 검사로 무해하게 걸러지며
        _maybe_compact_ttl_heap이 주기적으로 회수한다.)
        반환: ('int', 1) 삭제함 | ('int', 0) 없거나 이미 만료
        """
        entry = self._get_live_entry(key)
        if entry is None:
            return ('int', 0)
        self._hard_delete(key, entry)
        return ('int', 1)

    def cmd_exists(self, key):
        """key의 존재 여부. 만료된 키는 삭제 후 '없음'으로 취급한다.

        반환: ('int', 1) | ('int', 0)
        """
        return ('int', 1 if self._get_live_entry(key) is not None else 0)

    def cmd_dbsize(self):
        """저장된 키 개수. 만료 키를 먼저 회수하므로 항상 '살아있는' 수다.

        반환: ('int', n)
        """
        self._purge_expired_via_heap()
        return ('int', self._store.size())

    def cmd_keys(self):
        """전체 키 목록. 만료 키를 먼저 회수한다.

        순서는 해시 버킷 순회 순서라 삽입 순서도 정렬 순서도 아니다.
        반환: ('array', [key, ...])
        """
        self._purge_expired_via_heap()
        return ('array', self._store.keys())

    def cmd_config_set_maxmemory(self, bytes_value):
        """maxmemory를 설정한다. 0은 무제한.

        한도를 현재 사용량보다 낮추면 그 자리에서 LRU 축출을 수행해
        maxmemory 이하로 맞춘다. 음수는 거부하며 기존 설정과 데이터를
        전혀 건드리지 않는다.
        반환: ('ok',) | ('error', ...)
        """
        if bytes_value < 0:
            return ('error', self._RANGE_MSG)
        self._maxmemory = bytes_value
        # 새 제한이 현재 사용량보다 작으면 즉시 만료 회수 + LRU 축출을 수행한다.
        if self._maxmemory > 0:
            self._evict_to_fit(0)
        return ('ok',)

    def cmd_info_memory(self):
        """메모리 통계. 만료 키를 먼저 회수하므로 used_memory는 살아있는 합이다.

        반환: ('info', used_memory, maxmemory, evicted_keys)
        """
        self._purge_expired_via_heap()
        return ('info', self._used_memory, self._maxmemory, self._evicted_keys)

    def cmd_expire(self, key, seconds):
        """key에 만료 시간(초)을 건다.

        seconds가 0 이하면 즉시 만료로 처리해 그 자리에서 삭제한다.
        반환: ('int', 1) 설정/즉시만료 | ('int', 0) 키 없음
        """
        entry = self._get_live_entry(key)
        if entry is None:
            return ('int', 0)
        if seconds <= 0:
            # 즉시 만료: 존재하던 키를 삭제하고 1 반환
            self._hard_delete(key, entry)
            return ('int', 1)
        expire_at = self._now_fn() + seconds
        entry.expire_at = expire_at
        # 옛 항목을 찾아 지우면 O(n)이므로 무조건 push하고, 회수 시점에
        # expire_at 일치 검사로 stale을 걸러낸다.
        self._ttl_heap.push((expire_at, key))
        # 힙이 커지는 유일한 지점이므로 상한도 여기서 지킨다. 이게 없으면
        # purge 계열 명령(SET/DBSIZE/KEYS/INFO)이 한 번도 섞이지 않는
        # "GET 후 EXPIRE로 세션 연장" 같은 워크로드에서 stale이 무한 누적된다.
        # 임계 이하이면 size() 비교 한 번으로 끝나므로 O(1)이다.
        self._maybe_compact_ttl_heap()
        return ('int', 1)

    def cmd_ttl(self, key):
        """key의 남은 만료 시간(초).

        남은 시간은 내림(floor)한다. 따라서 EXPIRE 직후 값을 조회하면
        경과 시간만큼 줄어든 값이 나온다(예: EXPIRE k 3 -> 2).
        반환: ('int', n) 남은 초 | ('int', -1) TTL 없음 | ('int', -2) 키 없음
        """
        entry = self._get_live_entry(key)
        if entry is None:
            return ('int', -2)
        if entry.expire_at is None:
            return ('int', -1)
        remaining = entry.expire_at - self._now_fn()
        if remaining < 0:
            return ('int', -2)
        return ('int', int(remaining))
