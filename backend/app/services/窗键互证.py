"""窗键对齐互证（口径乙：合计 + 窗键归属，全局唯一口径）

互证必须同时证明两件事：
1. 合计同源：每个热度窗的窗表点赞/送礼/笔数 = 落该窗（命运='已入窗'）事件求和；
2. 窗键归属：每条已入窗事件，按其【事件时】与当前对齐规则重算窗键，须与落库窗键一致。

「合计正确但窗键错挂」在本口径下必须失败（口径甲「只核合计」会放行，本项目不采用）。
失败即列出错挂明细，并把涉事窗置为「阻断」：关窗扫描不得标发射成功，入流不得再写入，
直至数据修复后重算互证通过解除。失败闭，不半截。

并发：跑互证与入流装一批共用 services.主链锁，且互证以 BEGIN IMMEDIATE 立即取写锁，
整事务提交/回滚，杜绝互证中途入流继续灌脏窗。
"""

from app.db import 连接
from app.seed import 此刻
from app.services import 时间
from app.services.主链锁 import 主链锁

未核 = "未核"
通过 = "通过"
阻断 = "阻断"
口径名 = "合计加窗键归属"


def _重算窗键(事件行, 窗长秒: int) -> str:
    窗起 = 时间.对齐窗起(事件行["事件时"], 窗长秒)
    return 时间.窗键(事件行["房间键"], 窗起)


def 读互证(conn) -> dict:
    """只读互证：错挂列表、各窗合计、valid。不写库、不取主链锁。"""
    窗长秒 = int(
        conn.execute("SELECT 值 FROM 站规 WHERE 键='窗长秒'").fetchone()["值"]
    )
    窗列 = conn.execute("SELECT * FROM 热度窗 ORDER BY 房间键, 窗起事件时").fetchall()
    错挂列表 = []
    合计不符列表 = []
    窗报 = []
    阻断窗 = []
    事件总数 = 0

    for 窗 in 窗列:
        事件们 = conn.execute(
            "SELECT * FROM 互动事件 WHERE 窗键=? AND 命运='已入窗' ORDER BY 事件时",
            (窗["窗键"],),
        ).fetchall()
        事件总数 += len(事件们)
        事件赞 = sum(int(e["点赞增量"]) for e in 事件们)
        事件送 = sum(int(e["送礼额"]) for e in 事件们)
        窗表赞, 窗表送, 窗表笔 = (
            int(窗["点赞合计"]),
            int(窗["送礼合计"]),
            int(窗["事件笔数"]),
        )

        本窗错挂 = []
        for e in 事件们:
            应属 = _重算窗键(e, 窗长秒)
            if 应属 != e["窗键"]:
                项 = {
                    "事件编号": e["事件编号"],
                    "房间键": e["房间键"],
                    "事件时": e["事件时"],
                    "落库窗键": e["窗键"],
                    "应属窗键": 应属,
                }
                本窗错挂.append(项)
                错挂列表.append(项)

        合计不符 = (
            事件赞 != 窗表赞 or 事件送 != 窗表送 or len(事件们) != 窗表笔
        )
        if 合计不符:
            合计不符列表.append(
                {
                    "窗键": 窗["窗键"],
                    "窗表点赞": 窗表赞,
                    "事件点赞": 事件赞,
                    "窗表送礼": 窗表送,
                    "事件送礼": 事件送,
                    "窗表笔数": 窗表笔,
                    "事件笔数": len(事件们),
                }
            )

        原因 = []
        if 本窗错挂:
            原因.append(f"窗键错挂{len(本窗错挂)}笔")
        if 合计不符:
            原因.append("窗表合计与事件求和不符")
        窗有效 = not 原因
        if not 窗有效:
            阻断窗.append(窗["窗键"])

        窗报.append(
            {
                "窗键": 窗["窗键"],
                "房间键": 窗["房间键"],
                "状态": 窗["状态"],
                "互证状态": 窗["互证状态"],
                "窗表": {"点赞": 窗表赞, "送礼": 窗表送, "笔数": 窗表笔},
                "事件求和": {"点赞": 事件赞, "送礼": 事件送, "笔数": len(事件们)},
                "错挂笔数": len(本窗错挂),
                "错挂明细": 本窗错挂,
                "valid": 窗有效,
                "阻断原因": "；".join(原因),
            }
        )

    valid = not 错挂列表 and not 合计不符列表
    return {
        "valid": valid,
        "是否通过": valid,
        "口径": 口径名,
        "错挂列表": 错挂列表,
        "合计不符列表": 合计不符列表,
        "窗": 窗报,
        "阻断窗": 阻断窗,
        "合计": {
            "窗数": len(窗列),
            "入窗事件数": 事件总数,
            "错挂数": len(错挂列表),
            "合计不符窗数": len(合计不符列表),
            "阻断窗数": len(阻断窗),
        },
    }


def 跑互证(锁内回调=None) -> dict:
    """重算互证并落阻断/通过标记，写窗贯验履历。主链锁内整事务，失败闭。

    锁内回调仅供测试在持锁事务中注入并发动作（模拟互证中的入流），生产路径不传。
    """
    with 主链锁:
        conn = 连接()
        try:
            # 立即取写锁：互证开始后，其他写事务在连接层即被挡住，配合主链锁双保险
            conn.execute("BEGIN IMMEDIATE")
            if 锁内回调 is not None:
                锁内回调(conn)

            果 = 读互证(conn)
            for w in 果["窗"]:
                新态 = 通过 if w["valid"] else 阻断
                conn.execute(
                    "UPDATE 热度窗 SET 互证状态=? WHERE 窗键=?",
                    (新态, w["窗键"]),
                )

            问题 = []
            if 果["错挂列表"]:
                问题.append(
                    "窗键错挂事件:"
                    + ",".join(x["事件编号"] for x in 果["错挂列表"])
                )
            if 果["合计不符列表"]:
                问题.append(
                    "合计不符窗:" + ",".join(x["窗键"] for x in 果["合计不符列表"])
                )

            事件数 = conn.execute("SELECT COUNT(*) FROM 互动事件").fetchone()[0]
            已关闭 = conn.execute(
                "SELECT * FROM 热度窗 WHERE 状态='已关闭'"
            ).fetchall()
            撤回数 = conn.execute("SELECT COUNT(*) FROM 撤回单").fetchone()[0]
            旁路数 = conn.execute("SELECT COUNT(*) FROM 旁路匣").fetchone()[0]

            # 既有贯验保留项：末次撤回须与窗表一致；旁路事件不得挂窗键
            for 窗 in 已关闭:
                末撤 = conn.execute(
                    "SELECT * FROM 撤回单 WHERE 窗键=? ORDER BY 编号 DESC LIMIT 1",
                    (窗["窗键"],),
                ).fetchone()
                if 末撤 and (
                    末撤["新点赞"] != 窗["点赞合计"]
                    or 末撤["新送礼"] != 窗["送礼合计"]
                ):
                    问题.append(f"窗{窗['窗键']}末次撤回与窗表不一致")
            脏旁路 = conn.execute(
                "SELECT COUNT(*) FROM 互动事件 WHERE 命运='已旁路' AND 窗键!=''"
            ).fetchone()[0]
            if 脏旁路:
                问题.append(f"旁路事件仍挂窗键:{脏旁路}")

            通过旗 = 1 if not 问题 else 0
            说明 = (
                "窗键归属与合计同源互证通过"
                if 通过旗
                else "；".join(问题)[:800]
            )
            conn.execute(
                """INSERT INTO 窗贯验(时刻,事件数,已关闭窗数,撤回数,旁路数,是否通过,说明,错挂数,阻断窗数)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    此刻(),
                    事件数,
                    len(已关闭),
                    撤回数,
                    旁路数,
                    通过旗,
                    说明,
                    果["合计"]["错挂数"],
                    果["合计"]["阻断窗数"],
                ),
            )
            conn.commit()

            果.update(
                {
                    "事件数": 事件数,
                    "已关闭窗数": len(已关闭),
                    "撤回数": 撤回数,
                    "旁路数": 旁路数,
                    "说明": 说明,
                    "问题": 问题,
                }
            )
            return 果
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
