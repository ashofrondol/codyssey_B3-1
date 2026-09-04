"""체이닝(chaining) 방식으로 구현한 해시맵.

각 버킷은 이중 연결 리스트(DoublyLinkedList)를 사용해 충돌을 해결한다.
로드 팩터(저장된 키 개수 / 버킷 개수)가 0.75를 넘으면 버킷을 2배로
늘려서 다시 재배치(rehash)하고, 반대로 0.1875 아래로 헐거워지면
버킷을 절반으로 줄인다.

내장 dict 사용은 금지되어 있으므로, 버킷 테이블 자체는 '고정 길이
인덱스 접근 배열' 용도로 파이썬 list를 사용한다.
"""

from linked_list import DoublyLinkedList


class HashMap:
    """문자열 키 기반의 해시맵.

    충돌 해결: 체이닝(같은 버킷 안에서 이중 연결 리스트로 노드 연결).
    로드 팩터가 0.75를 넘으면 버킷 수를 2배로 확장하고,
    0.1875 밑으로 떨어지면 절반으로 축소한다.

    노드 정책:
        - 새 키는 insert_back으로 노드를 새로 만든다.
        - 같은 키를 덮어쓸 때는 노드를 재사용하고 data 튜플만 교체한다.
        - remove는 remove_node로 앞뒤를 다시 이은 뒤 prev/next/owner를 전부
          None으로 끊는다. 제거된 노드가 리스트를 붙들지 않으므로 참조가
          사라지는 즉시 회수되고, 같은 노드를 두 번 지워도 무해하다.
          별도의 노드 풀(free list)은 두지 않고 파이썬 GC에 맡긴다.
        - _resize는 노드를 재사용하지 않는다. data만 꺼내 새 버킷 리스트에
          다시 넣으므로 재배치할 때마다 노드 n개가 새로 생긴다.
    """

    _INITIAL_CAPACITY = 8
    _LOAD_FACTOR = 0.75
    # 축소 임계는 확장 임계의 1/4로 잡는다. 축소 직후 로드 팩터가
    # size/(cap/2) < 0.375 라 확장 임계 0.75의 절반에 머물러
    # '축소 -> 즉시 재확장'이 반복되는 진동이 생기지 않는다.
    _SHRINK_FACTOR = 0.1875

    # FNV-1a 해시 상수(64비트)
    _FNV_OFFSET = 0xcbf29ce484222325
    _FNV_PRIME = 0x100000001b3
    _MASK64 = (1 << 64) - 1

    def __init__(self):
        self._capacity = self._INITIAL_CAPACITY
        self._size = 0
        self._buckets = self._make_buckets(self._capacity)

    # ------- public API -------

    def put(self, key, value):
        """key에 value를 저장한다. 같은 키가 있으면 덮어쓴다.

        반환: 새로 삽입했으면 True, 기존 키를 덮어썼으면 False.
        """
        bucket = self._buckets[self._index(key, self._capacity)]
        node = self._find_in_bucket(bucket, key)
        if node is not None:
            node.data = (key, value)
            return False  # 신규가 아님
        bucket.insert_back((key, value))
        self._size += 1
        if self._size > self._capacity * self._LOAD_FACTOR:
            self._resize(self._capacity * 2)
        return True

    def get(self, key, default=None):
        """key의 value를 반환. 없으면 default."""
        bucket = self._buckets[self._index(key, self._capacity)]
        node = self._find_in_bucket(bucket, key)
        if node is None:
            return default
        return node.data[1]

    def remove(self, key):
        """key를 제거하고 그 value를 반환. 없으면 None."""
        bucket = self._buckets[self._index(key, self._capacity)]
        node = self._find_in_bucket(bucket, key)
        if node is None:
            return None
        _, value = node.data
        bucket.remove_node(node)
        self._size -= 1
        self._maybe_shrink()
        return value

    def contains(self, key):
        """key가 저장되어 있으면 True. 값이 None이어도 True다."""
        bucket = self._buckets[self._index(key, self._capacity)]
        return self._find_in_bucket(bucket, key) is not None

    def keys(self):
        """저장된 모든 key를 리스트로 반환(순서 보장 없음).

        버킷 순회 순서에 의존하므로 삽입 순서도, 정렬 순서도 아니다.
        호출자는 순서에 의존해서는 안 된다.
        반환 리스트는 호출 시점의 스냅샷이라 순회 중 원본을 수정해도 안전하다.
        """
        result = []
        for bucket in self._buckets:
            for data in bucket.iter_data():
                result.append(data[0])
        return result

    def size(self):
        """저장된 키의 개수."""
        return self._size

    def capacity(self):
        """현재 버킷 테이블의 길이(디버깅/테스트용)."""
        return self._capacity

    def __len__(self):
        return self._size

    # ------- internals -------

    def _hash(self, key):
        """FNV-1a 해시 함수(64비트).

        문자열을 UTF-8 바이트로 변환한 뒤 각 바이트마다:
            h = (h XOR byte) * FNV_PRIME (mod 2^64)
        를 반복해서 분포가 좋은 해시값을 얻는다.

        XOR을 곱셈 '앞'에 두는 것이 FNV-1a이고, 그게 원조 FNV-1(곱한 뒤 XOR)
        보다 나은 이유다. 바이트를 먼저 섞어 넣고 곱하면 그 바이트가 곱셈의
        자리올림을 타고 상위 비트까지 퍼지지만, FNV-1은 마지막 바이트가 XOR된
        자리에만 남는다.

        한계도 분명하다. 확산은 남은 곱셈 횟수에 비례하므로 '마지막' 바이트만
        다른 키들은 곱셈을 한 번밖에 거치지 못하고, FNV_PRIME은 set bit가 7개뿐
        이라 그 한 번으로는 거의 퍼지지 않는다 — 마지막 바이트에서 1비트를
        바꿨을 때 실제로 달라지는 해시 비트는 평균 9.4/64다(첫 바이트를 바꾸면
        이후 곱셈을 여러 번 거쳐 이상치 32에 근접한다). 실측 영향과 대응 판단은
        README '자료구조 설명' 2절 참고.

        그리고 FNV-1a는 seed 없는 해시라 의도적 충돌 공격을 막지 못한다.
        공개된 서버라면 SipHash 같은 keyed hash가 필요하다(파이썬의 문자열
        해시가 랜덤 시드 SipHash를 쓰는 이유가 그것이다).
        """
        if isinstance(key, str):
            data = key.encode('utf-8')
        elif isinstance(key, (bytes, bytearray)):
            data = bytes(key)
        else:
            data = str(key).encode('utf-8')
        h = self._FNV_OFFSET
        for byte in data:
            h ^= byte
            h = (h * self._FNV_PRIME) & self._MASK64
        return h

    def _index(self, key, capacity):
        """해시값을 버킷 테이블 인덱스로 접는다.

        capacity는 항상 2의 거듭제곱이라 % capacity는 사실상 '하위
        log2(capacity)비트만 취하기'다. 곱셈의 확산이 하위→상위 방향이라
        하위 비트가 덜 섞이지 않을까 싶지만, 실측한 하위 14비트의 avalanche는
        42~47%로 이상치 50%에 충분히 가깝고 최장 체인도 이상적 난수 해시와
        같은 5~7에 머문다.
        """
        return self._hash(key) % capacity

    @staticmethod
    def _make_buckets(capacity):
        # list는 '고정 길이 인덱스 접근 배열' 용도로만 사용한다.
        # 키-값 저장 자료구조로 사용하는 것은 금지된 영역.
        buckets = [None] * capacity
        for i in range(capacity):
            buckets[i] = DoublyLinkedList()
        return buckets

    @staticmethod
    def _find_in_bucket(bucket, key):
        """버킷(연결 리스트) 안에서 key를 가진 노드를 찾는다."""
        for node in bucket.iter_nodes():
            if node.data[0] == key:
                return node
        return None

    def _maybe_shrink(self):
        """너무 헐거워진 버킷 테이블을 목표 용량까지 줄인다.

        축소 경로가 없으면 대량 삭제(예: LRU eviction) 후에도 버킷 배열이
        최대 크기로 남아 keys() 순회가 실제 키 수와 무관하게 느려지고
        메모리도 회수되지 않는다.
        """
        new_capacity = self._capacity
        while (new_capacity > self._INITIAL_CAPACITY
               and self._size < new_capacity * self._SHRINK_FACTOR):
            new_capacity //= 2
        if new_capacity != self._capacity:
            self._resize(new_capacity)

    def _resize(self, new_capacity):
        """버킷 테이블을 new_capacity 크기로 다시 만들고 모든 키를 재배치한다.

        비용은 키 n개를 전부 다시 해싱하므로 이 호출 하나가 O(n)이다. 확장이
        용량을 2배로 키우므로 다음 확장까지 최소 n번의 삽입이 들어오고, 따라서
        put() 한 번당 상각 비용은 O(1)에 머문다.

        다만 상각이 감추는 것은 '평균'이지 '개별 지연'이 아니다. 재배치가 걸리는
        그 한 번의 put()은 통째로 O(n)이다(키 10만 개 기준 단일 SET 269 ms 측정).
        완화책은 README '설계 확장 노트' 2절 참고.
        """
        new_buckets = self._make_buckets(new_capacity)
        for bucket in self._buckets:
            for data in bucket.iter_data():
                key, _ = data
                idx = self._hash(key) % new_capacity
                new_buckets[idx].insert_back(data)
        self._buckets = new_buckets
        self._capacity = new_capacity
