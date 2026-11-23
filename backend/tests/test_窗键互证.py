import json
import threading
from pathlib import Path

import pytest

from app.services import 装载, 窗键互证, 热度窗

夹具根 = Path("/workspace/fixtures")


def 读夹具(名):
    return json.loads((夹具根 / f"{名}.json").read_text(encoding="utf-8"))


def 制造错挂凑齐合计(conn):
    """人造脏数据：交换两窗各一条事件的落库窗键，并同步交换窗表合计。

    结果：每个窗的窗表合计仍等于【当前挂在它名下】事件的求和（只核合计的口径甲会放行），
    但两条事件的落库窗键都不等于按事件时重算的窗键（口径乙必须失败）。
    """
    wk1 = "房A|2026-11-23T10:00:00Z"
    wk2 = "房A|2026-11-23T10:01:00Z"
    conn.execute("UPDATE 互动事件 SET 窗键=? WHERE 事件编号='W2'", (wk2,))
    conn.execute("UPDATE 互动事件 SET 窗键=? WHERE 事件编号='W4'", (wk1,))
    conn.execute("UPDATE 热度窗 SET 点赞合计=8 WHERE 窗键=?", (wk1,))
    conn.execute("UPDATE 热度窗 SET 点赞合计=9 WHERE 窗键=?", (wk2,))
    conn.commit()
    return wk1, wk2


def test_甲可过乙必败_合计凑齐但窗键错挂(临时库):
    连接 = 临时库
    装载.装一批(读夹具("双窗错挂夹具"))
    conn = 连接()
    wk1, wk2 = 制造错挂凑齐合计(conn)
    conn.close()

    # 口径甲（只核合计）：窗表合计 == 名下事件求和 → 会通过
    conn = 连接()
    for wk in (wk1, wk2):
        窗 = conn.execute("SELECT * FROM 热度窗 WHERE 窗键=?", (wk,)).fetchone()
        agg = conn.execute(
            "SELECT COALESCE(SUM(点赞增量),0) z FROM 互动事件 WHERE 窗键=? AND 命运='已入窗'",
            (wk,),
        ).fetchone()
        assert agg["z"] == 窗["点赞合计"], "夹具前提：只核合计应凑齐"
    conn.close()

    # 口径乙（合计+归属）：重算窗键不一致 → 必须失败并列出错挂明细
    果 = 窗键互证.跑互证()
    assert 果["valid"] is False
    错挂事件 = {x["事件编号"] for x in 果["错挂列表"]}
    assert 错挂事件 == {"W2", "W4"}
    明细 = {x["事件编号"]: x for x in 果["错挂列表"]}
    assert 明细["W2"]["落库窗键"] == wk2 and 明细["W2"]["应属窗键"] == wk1
    assert 明细["W4"]["落库窗键"] == wk1 and 明细["W4"]["应属窗键"] == wk2
    # 每个窗仍报合计同源（证明分歧点只在归属，不是数字没凑齐）
    assert all(w["事件求和"] == w["窗表"] for w in 果["窗"])
    assert {w["窗键"] for w in 果["窗"] if not w["valid"]} == {wk1, wk2}

    # 失败闭：两窗被置阻断
    conn = 连接()
    for wk in (wk1, wk2):
        assert conn.execute(
            "SELECT 互证状态 FROM 热度窗 WHERE 窗键=?", (wk,)
        ).fetchone()["互证状态"] == 窗键互证.阻断
    conn.close()


def test_互证失败后关窗扫描不得标发射成功(临时库):
    连接 = 临时库
    装载.装一批(读夹具("双窗错挂夹具"))
    conn = 连接()
    wk1, _wk2 = 制造错挂凑齐合计(conn)
    conn.close()
    窗键互证.跑互证()  # 置阻断

    conn = 连接()
    # 水位已远超两窗窗止：wk2 仍开启，阻断窗必须保持「开启」不得关；
    # wk1 此前已正常关闭，关窗扫描本就不会再碰它（也不得翻成功口径）。
    r = 热度窗.尝试关窗(
        conn, "房A", "2026-11-23T10:09:00Z", 30, 60, "2026-11-23T10:09:01Z"
    )
    conn.commit()
    assert r == {"关窗": 0, "阻断": 1}
    wk2 = conn.execute("SELECT * FROM 热度窗 WHERE 窗键=?", ("房A|2026-11-23T10:01:00Z",)).fetchone()
    assert wk2["状态"] == "开启" and wk2["互证状态"] == 窗键互证.阻断
    assert wk2["关闭处理时"] == ""
    wk1row = conn.execute("SELECT * FROM 热度窗 WHERE 窗键=?", (wk1,)).fetchone()
    assert wk1row["互证状态"] == 窗键互证.阻断
    conn.close()

    # 再走真实入流：事件落在仍开启的阻断窗 wk2 且仍在允许迟到内，
    # 写闸必须拦下（不能走旁路侥幸，也不得让脏窗扩大、出成功口径）
    conn.close()
    报告 = 装载.装一批(
        {
            "批次编号": "批-撞阻断",
            "事件": [
                {
                    "事件编号": "LATE1",
                    "房间键": "房A",
                    "事件类型": "点赞",
                    "事件时": "2026-11-23T10:01:25Z",
                    "处理时": "2026-11-23T10:01:35Z",
                    "点赞增量": 100,
                }
            ],
        }
    )
    assert 报告["入窗"] == 0
    assert 报告["阻断"] >= 1
    conn = 连接()
    ev = conn.execute("SELECT * FROM 互动事件 WHERE 事件编号='LATE1'").fetchone()
    assert ev["命运"] == "已阻断" and ev["窗键"] == ""
    wk2 = conn.execute("SELECT * FROM 热度窗 WHERE 窗键=?", ("房A|2026-11-23T10:01:00Z",)).fetchone()
    assert wk2["点赞合计"] == 9  # 未被 +100 污染
    匣 = conn.execute(
        "SELECT 原因 FROM 旁路匣 WHERE 原因='阻断窗禁写'"
    ).fetchall()
    assert 匣
    conn.close()


def test_互证中的入流不得扩大脏窗也不得报成功(临时库):
    连接 = 临时库
    装载.装一批(读夹具("双窗错挂夹具"))
    conn = 连接()
    wk1, _wk2 = 制造错挂凑齐合计(conn)
    conn.close()

    入流结果 = {}
    线柄 = {}

    def 互证持锁时灌入(_conn):
        # 此刻互证已持主链锁+写事务：入流必须阻塞等待，不能插进来写脏窗
        t = threading.Thread(
            target=lambda: 入流结果.update(
                装载.装一批(
                    {
                        "批次编号": "批-互证中入流",
                        "事件": [
                            {
                                "事件编号": "MID1",
                                "房间键": "房A",
                                "事件类型": "点赞",
                                "事件时": "2026-11-23T10:01:30Z",
                                "处理时": "2026-11-23T10:01:32Z",
                                "点赞增量": 100,
                            }
                        ],
                    }
                )
            )
        )
        线柄["t"] = t
        t.start()
        t.join(timeout=2)
        assert t.is_alive(), "互证未结束时入流必须被主链锁挡住"

    果 = 窗键互证.跑互证(锁内回调=互证持锁时灌入)
    assert 果["valid"] is False
    线柄["t"].join(timeout=5)
    assert not 线柄["t"].is_alive()

    # 互证结束后入流才拿到锁；此时窗已阻断，事件必须被写闸拦下
    assert 入流结果["入窗"] == 0
    assert 入流结果["阻断"] >= 1
    conn = 连接()
    ev = conn.execute("SELECT * FROM 互动事件 WHERE 事件编号='MID1'").fetchone()
    assert ev["命运"] == "已阻断" and ev["窗键"] == ""
    wk2 = conn.execute("SELECT * FROM 热度窗 WHERE 窗键=?", ("房A|2026-11-23T10:01:00Z",)).fetchone()
    assert wk2["点赞合计"] == 9
    conn.close()


def test_干净主链端到端互证通过且修复后解除阻断(临时库):
    装载.装一批(读夹具("准时热度样例"))
    装载.装一批(读夹具("迟到修正样例"))
    装载.装一批(读夹具("超迟到旁路样例"))

    果 = 窗键互证.跑互证()
    assert 果["valid"] is True
    assert 果["错挂列表"] == []
    assert 果["合计"]["阻断窗数"] == 0
    assert all(w["valid"] for w in 果["窗"])

    # 修复路径：人为错挂→失败阻断；纠正回正确窗键与合计→重算通过、阻断解除
    from app.services import 时间

    conn = 临时库()
    e1 = conn.execute("SELECT * FROM 互动事件 WHERE 事件编号='E1'").fetchone()
    应属 = 时间.窗键(e1["房间键"], 时间.对齐窗起(e1["事件时"], 60))
    别的窗 = conn.execute(
        "SELECT 窗键 FROM 热度窗 WHERE 窗键!=?", (应属,)
    ).fetchone()["窗键"]
    conn.execute("UPDATE 互动事件 SET 窗键=? WHERE 事件编号='E1'", (别的窗,))
    conn.commit()
    conn.close()
    坏 = 窗键互证.跑互证()
    assert 坏["valid"] is False
    conn = 临时库()
    assert conn.execute(
        "SELECT 互证状态 FROM 热度窗 WHERE 窗键=?", (别的窗,)
    ).fetchone()["互证状态"] == 窗键互证.阻断

    # 纠正数据（把事件挂回应属窗键；合计本就随事件归属，窗表无需改）
    conn.execute("UPDATE 互动事件 SET 窗键=? WHERE 事件编号='E1'", (应属,))
    conn.commit()
    conn.close()
    好 = 窗键互证.跑互证()
    assert 好["valid"] is True
    conn = 临时库()
    assert conn.execute(
        "SELECT 互证状态 FROM 热度窗 WHERE 窗键=?", (别的窗,)
    ).fetchone()["互证状态"] == 窗键互证.通过
    conn.close()


def test_只读接口不写库不改阻断态(临时库):
    装载.装一批(读夹具("双窗错挂夹具"))
    conn = 临时库()
    制造错挂凑齐合计(conn)
    conn.close()
    窗键互证.跑互证()  # 先阻断

    conn = 临时库()
    前 = [dict(r) for r in conn.execute("SELECT * FROM 热度窗")]
    履历前 = conn.execute("SELECT COUNT(*) c FROM 窗贯验").fetchone()["c"]
    只读 = 窗键互证.读互证(conn)
    后 = [dict(r) for r in conn.execute("SELECT * FROM 热度窗")]
    履历后 = conn.execute("SELECT COUNT(*) c FROM 窗贯验").fetchone()["c"]
    assert 只读["valid"] is False
    assert 前 == 后 and 履历前 == 履历后  # 纯只读
    conn.close()
