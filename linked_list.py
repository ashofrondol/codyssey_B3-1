"""이중 연결 리스트(Doubly Linked List).

LRU 추적과 해시맵 체이닝(충돌 해결)에 동시에 사용한다.
앞/뒤 sentinel 노드를 두어 모든 삽입/삭제/이동 연산을 O(1)에 처리한다.
"""


class Node:
    """이중 연결 리스트의 노드.

    prev, next, data 세 필드를 가지며 외부에서 노드 참조를 직접 들고 있으면
    O(1)로 해당 노드를 제거하거나 앞으로 이동시킬 수 있다.
    """

    __slots__ = ('prev', 'next', 'data')

    def __init__(self, data):
        self.prev = None
        self.next = None
        self.data = data


class DoublyLinkedList:
    """양방향(이중) 연결 리스트.

    내부적으로 head/tail sentinel 노드를 사용한다. sentinel을 두면
    경계 조건(빈 리스트, 첫/마지막 노드) 처리가 사라져서 모든 연산이
    분기 없이 깔끔하게 O(1)이 된다.

    LRU 캐시에서 사용할 때:
        - front(앞쪽)  = 가장 최근에 사용된 항목(MRU)
        - back(뒤쪽)   = 가장 오래 사용되지 않은 항목(LRU)
    """

    def __init__(self):
        self._head = Node(None)
        self._tail = Node(None)
        self._head.next = self._tail
        self._tail.prev = self._head
        self._size = 0

    def __len__(self):
        return self._size

    def is_empty(self):
        return self._size == 0

    def front(self):
        """앞쪽 실제 노드(MRU)를 반환. 비어 있으면 None."""
        if self._size == 0:
            return None
        return self._head.next

    def back(self):
        """뒤쪽 실제 노드(LRU)를 반환. 비어 있으면 None."""
        if self._size == 0:
            return None
        return self._tail.prev

    def insert_front(self, data):
        """앞쪽에 새 노드를 만들어 삽입하고 그 노드를 반환한다."""
        node = Node(data)
        self._link(self._head, node, self._head.next)
        self._size += 1
        return node

    def insert_back(self, data):
        """뒤쪽에 새 노드를 만들어 삽입하고 그 노드를 반환한다."""
        node = Node(data)
        self._link(self._tail.prev, node, self._tail)
        self._size += 1
        return node

    def remove_front(self):
        """앞쪽 노드를 제거하고 그 data를 반환. 비어 있으면 None."""
        if self._size == 0:
            return None
        return self.remove_node(self._head.next)

    def remove_back(self):
        """뒤쪽 노드를 제거하고 그 data를 반환. 비어 있으면 None."""
        if self._size == 0:
            return None
        return self.remove_node(self._tail.prev)

    def remove_node(self, node):
        """임의의 노드(참조를 이미 들고 있는)를 O(1)에 제거한다."""
        if node is self._head or node is self._tail:
            return None
        node.prev.next = node.next
        node.next.prev = node.prev
        data = node.data
        node.prev = None
        node.next = None
        self._size -= 1
        return data

    def move_to_front(self, node):
        """이미 리스트에 있는 노드를 맨 앞으로 옮긴다(LRU 갱신용)."""
        if node is self._head or node is self._tail:
            return
        if node.prev is self._head:
            return
        # 1) 기존 자리에서 떼어낸다
        node.prev.next = node.next
        node.next.prev = node.prev
        # 2) 맨 앞에 다시 끼워 넣는다
        self._link(self._head, node, self._head.next)

    def iter_nodes(self):
        """앞에서 뒤 방향으로 모든 실제 노드를 순회한다.

        순회 도중 현재 노드를 제거해도 안전하도록 다음 노드를 미리 잡아둔다.
        """
        cur = self._head.next
        while cur is not self._tail:
            nxt = cur.next
            yield cur
            cur = nxt

    def iter_data(self):
        """앞에서 뒤 방향으로 모든 노드의 data를 순회한다."""
        for node in self.iter_nodes():
            yield node.data

    @staticmethod
    def _link(prev_node, new_node, next_node):
        """prev_node <-> new_node <-> next_node로 연결한다."""
        new_node.prev = prev_node
        new_node.next = next_node
        prev_node.next = new_node
        next_node.prev = new_node
