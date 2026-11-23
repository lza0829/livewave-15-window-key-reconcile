import React, { useEffect, useState } from "react";
import { 取, 递 } from "../api.js";

export default function 窗互证页() {
  const [列, 设列] = useState([]);
  const [果, 设果] = useState(null);
  const [只, 设只] = useState(null);
  const 刷只读 = () => 取("/窗键互证").then(设只);
  const 刷履历 = () => 取("/贯验").then(设列);
  useEffect(() => {
    刷只读();
    刷履历();
  }, []);
  const 跑 = async () => {
    设果(await 递("/贯验"));
    刷只读();
    刷履历();
  };
  return (
    <div>
      <h1 className="题">窗互证</h1>
      <p className="述">
        口径（全局唯一）：<b>合计加窗键归属</b>。每条已入窗事件按其事件时重算窗键，须与落库窗键一致；
        且窗表点赞/送礼/笔数 = 窗内事件求和。「合计凑齐但窗键错挂」同样判失败并列错挂明细——
        失败窗置「阻断」：关窗扫描不得标发射成功，入流不得再写入，修复后重算通过才解除。
      </p>
      <div className="行">
        <button className="水" onClick={跑}>跑窗互证（落阻断/通过）</button>
        <button className="次" onClick={() => { 刷只读(); 刷履历(); }}>刷新</button>
      </div>

      {只 && (
        <div className="段">
          <div className="段题">
            只读互证（不写库） · 口径：{只.口径}
            <span className={`徽章 ${只.valid ? "通" : "败"}`} style={{ marginLeft: 8 }}>
              {只.valid ? "valid" : "invalid"}
            </span>
          </div>
          <div className="格">
            <div className="卡"><b>{只.合计.窗数}</b><span>热度窗</span></div>
            <div className="卡"><b>{只.合计.入窗事件数}</b><span>已入窗事件</span></div>
            <div className="卡"><b>{只.合计.错挂数}</b><span>窗键错挂笔数</span></div>
            <div className="卡"><b>{只.合计.合计不符窗数}</b><span>合计不符窗</span></div>
            <div className="卡"><b>{只.合计.阻断窗数}</b><span>阻断窗</span></div>
          </div>

          {只.错挂列表.length > 0 && (
            <div className="段">
              <div className="段题">错挂明细（落库窗键 ≠ 事件时重算窗键）</div>
              <table>
                <thead>
                  <tr><th>事件</th><th>房间</th><th>事件时</th><th>落库窗键</th><th>应属窗键</th></tr>
                </thead>
                <tbody>
                  {只.错挂列表.map((x) => (
                    <tr key={x.事件编号}>
                      <td>{x.事件编号}</td><td>{x.房间键}</td>
                      <td className="码">{x.事件时}</td>
                      <td className="码" style={{ color: "var(--败)" }}>{x.落库窗键}</td>
                      <td className="码" style={{ color: "var(--通)" }}>{x.应属窗键}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="段">
            <div className="段题">逐窗合计同源 + 归属</div>
            <table>
              <thead>
                <tr>
                  <th>窗键</th><th>窗状态</th><th>互证</th><th>窗表(赞/送/笔)</th>
                  <th>事件求和(赞/送/笔)</th><th>错挂</th><th>valid</th><th>阻断原因</th>
                </tr>
              </thead>
              <tbody>
                {只.窗.map((w) => (
                  <tr key={w.窗键}>
                    <td className="码">{w.窗键}</td>
                    <td>{w.状态}</td>
                    <td>
                      <span className={`徽章 ${w.互证状态 === "阻断" ? "败" : w.互证状态 === "通过" ? "通" : ""}`}>
                        {w.互证状态}
                      </span>
                    </td>
                    <td className="码">{w.窗表.点赞}/{w.窗表.送礼}/{w.窗表.笔数}</td>
                    <td className="码">{w.事件求和.点赞}/{w.事件求和.送礼}/{w.事件求和.笔数}</td>
                    <td>{w.错挂笔数}</td>
                    <td><span className={`徽章 ${w.valid ? "通" : "败"}`}>{String(w.valid)}</span></td>
                    <td style={{ color: "var(--淡)" }}>{w.阻断原因 || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {果 && (
        <div className="证板">
          <div className={`证旗 ${果.是否通过 ? "通" : "败"}`}>
            <div className="标">{果.是否通过 ? "对齐" : "撕裂"}</div>
            <div className="辅">{果.说明}</div>
          </div>
          <div className="格">
            <div className="卡"><b>{果.事件数}</b><span>事件</span></div>
            <div className="卡"><b>{果.已关闭窗数}</b><span>已关窗</span></div>
            <div className="卡"><b>{果.撤回数}</b><span>撤回</span></div>
            <div className="卡"><b>{果.旁路数}</b><span>旁路</span></div>
            <div className="卡"><b>{果.合计?.错挂数 ?? 0}</b><span>错挂</span></div>
            <div className="卡"><b>{果.合计?.阻断窗数 ?? 0}</b><span>阻断</span></div>
          </div>
        </div>
      )}

      <div className="段">
        <div className="段题">互证履历</div>
        {!列.length ? (
          <div className="空态">尚无履历</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>编号</th><th>时刻</th><th>结果</th><th>事件</th><th>关窗</th><th>撤回</th>
                <th>旁路</th><th>错挂</th><th>阻断</th><th>说明</th>
              </tr>
            </thead>
            <tbody>
              {列.map((r) => (
                <tr key={r.编号}>
                  <td>{r.编号}</td><td className="码">{r.时刻}</td>
                  <td><span className={`徽章 ${r.是否通过 ? "通" : "败"}`}>{r.是否通过 ? "对齐" : "撕裂"}</span></td>
                  <td>{r.事件数}</td><td>{r.已关闭窗数}</td><td>{r.撤回数}</td><td>{r.旁路数}</td>
                  <td>{r.错挂数 ?? 0}</td><td>{r.阻断窗数 ?? 0}</td>
                  <td>{r.说明}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
