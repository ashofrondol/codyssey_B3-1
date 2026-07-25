"""테스트 공용 도우미.

프로젝트 루트를 sys.path에 넣어, 어느 디렉터리에서 discover를 돌리든
`from mini_redis import MiniRedis`가 동작하게 한다.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class FakeClock:
    """time.time() 대체용 수동 시계.

    MiniRedis(now_fn=clock)로 주입하면 sleep 없이 TTL 만료를 결정적으로
    재현할 수 있다. 실제 시계에 의존하는 테스트는 느리고 불안정하다.
    """

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        """시계를 앞으로 감는다."""
        self.t += seconds
