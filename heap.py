"""배열 기반 최소 힙(Min Heap).

힙은 '완전 이진 트리'를 1차원 배열로 표현하는 자료구조이다.
인덱스 i의 부모는 (i - 1) // 2, 자식은 2*i + 1, 2*i + 2.
push/pop은 트리 높이만큼만 비교/교환을 하므로 O(log n)이다.

Mini Redis에서는 TTL(만료 시간) 관리에 사용한다. (expire_at, key)
형태의 튜플을 원소로 넣어두면 expire_at이 가장 빠른 항목을 항상
peek 한 번으로 찾을 수 있다.
"""


class MinHeap:
    """최소 힙. 가장 작은 원소가 항상 인덱스 0에 위치한다."""

    def __init__(self):
        # list는 '인덱스 접근/append 가능한 배열'로만 사용한다.
        self._data = []

    def __len__(self):
        return len(self._data)

    def size(self):
        return len(self._data)

    def is_empty(self):
        return len(self._data) == 0

    def push(self, item):
        """원소 추가 후 위로 끌어올려 힙 성질을 회복한다."""
        self._data.append(item)
        self._heapify_up(len(self._data) - 1)

    def pop(self):
        """루트(최솟값)를 꺼낸다. 비어 있으면 None."""
        if not self._data:
            return None
        top = self._data[0]
        last = self._data.pop()
        if self._data:
            self._data[0] = last
            self._heapify_down(0)
        return top

    def peek(self):
        """루트(최솟값)를 꺼내지 않고 들여다본다. 비어 있으면 None."""
        if not self._data:
            return None
        return self._data[0]

    # ------- internals -------

    def _heapify_up(self, i):
        """인덱스 i의 원소를 부모와 비교하며 더 작으면 위로 올린다."""
        while i > 0:
            parent = (i - 1) // 2
            if self._data[i] < self._data[parent]:
                self._data[i], self._data[parent] = self._data[parent], self._data[i]
                i = parent
            else:
                break

    def _heapify_down(self, i):
        """인덱스 i의 원소를 두 자식 중 더 작은 쪽과 비교하며 아래로 내린다."""
        n = len(self._data)
        while True:
            left = 2 * i + 1
            right = 2 * i + 2
            smallest = i
            if left < n and self._data[left] < self._data[smallest]:
                smallest = left
            if right < n and self._data[right] < self._data[smallest]:
                smallest = right
            if smallest == i:
                break
            self._data[i], self._data[smallest] = self._data[smallest], self._data[i]
            i = smallest
