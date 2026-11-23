"""窗贯验履历的兼容入口。

实质互证逻辑（合计同源 + 窗键归属、失败闭阻断）统一在 services.窗键互证，
本模块仅保留旧路径 /api/贯验 的调用名与返回字段，避免两套口径并存。
"""

from app.db import 连接
from app.services import 窗键互证


def 跑贯验() -> dict:
    return 窗键互证.跑互证()


def 列履历() -> list:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 窗贯验 ORDER BY 编号 DESC LIMIT 20"
            )
        ]
    finally:
        conn.close()
