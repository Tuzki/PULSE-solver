from pathlib import Path
import copy
import hashlib
import json
import sys
from collections import Counter

root=Path(r'D:\codex\pulse-solver-v1.15win')
out=root/'reports/windows_compare_20261027_final'
sys.path.insert(0,str(root/'scripts'))
import windows_compare as w

summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
rows=[]
for entry in summary['cases']:
    folder=out/entry['case']
    status=entry['status']
    if status=='STATISTICS_PASS_VISUAL_REVIEW_PENDING':
        config=json.loads((folder/'case_snapshot.json').read_text(encoding='utf-8'))
        original=Path(entry['source_case'])/config['source_model']
        capture=folder/'plecs_model'/original.name
        before=w.parse(original.read_text(encoding='utf-8-sig').splitlines())[0]
        after=w.parse(capture.read_text(encoding='utf-8-sig').splitlines())[0]
        reduced=copy.deepcopy(after)
        blocks=reduced[0]['children']
        # These Buck/Boost sources have no original top-level output terminals.
        assert not w.subs(before[0]['children'],'Terminal')
        blocks[:]=[n for n in blocks if n['key']!='Terminal']
        schematic=w.subs(blocks,'Schematic')[0]
        schematic[:]=[n for n in schematic if not (
            n['key']=='Component' and w.scalar(n['children']).get('Name','').startswith('WIN_')
            or n['key']=='Connection' and w.scalar(n['children']).get('DstComponent','').startswith('WIN_'))]
        preserved=reduced==before
        assert preserved,'Capture changed original model structure'
        images={kind:hashlib.sha256((folder/(kind+'.png')).read_bytes()).hexdigest() for kind in ('startup','steady')}
        review={'reviewer':'Codex visual inspection','conclusion':'MATCH_WITH_SAMPLING_LIMITS','channels':json.loads((folder/'channel_mapping.json').read_text(encoding='utf-8')),
                'images_sha256':images,'original_model_structure_preserved':preserved,
                'note':'Both simulators share axes and channel order. Startup envelope, steady ripple, switching frequency and phase were reviewed. Edge-side/sample-grid drawing differences remain; no waveform time shift was applied. This review does not measure sub-sample timing error.'}
        w.dump(folder/'visual_review.json',review)
        human='统计通过，波形复核一致（含采样限制）'
        detail=f"{entry['statistics_passed']}/{entry['statistics_total']}；7 通道；0.3 s"
    elif status=='PULSE_UNSUPPORTED_OR_FAILED':
        human='PULSE 不支持/求解失败'
        detail=entry.get('diagnostic',{}).get('subcode','见日志')
    elif status=='ERROR' and not (folder/'pulse').exists():
        human='转换未支持'
        detail=entry.get('error','').split('{')[0].replace('\n',' ')[:160]
    else:
        human=status;detail=entry.get('error','')
    rows.append((entry['case'],human,detail))

lines=['# Windows 原生构建及实时 PLECS 对照报告','',
'已建立 `D:\\codex\\pulse-solver-v1.15win`，Windows x64 原生编译成功。求解器源码及 CMakeLists.txt 共 26 个文件与原版逐字节一致；未修改求解算法、阈值、预算或物理参数。',
'','新工具实际安装于 `D:\\codex\\tool\\pulse-win`；项目内 `.build_tools` 仅为目录链接。无需 Linux、WSL 或虚拟机。',
'','## Windows 验证','',
'- 8/8 CTest 通过，包含 C ABI 动态库及 NPZ 兼容性。',
'- 20 个历史回归电路中 19 个完成；`rectifier_pf` 在约 9.800004 µs 因 `TRANSACTION_BUDGET` 停止。前缀和诊断保存在 `../windows_native_validation/rectifier_pf/`，没有放宽预算。该跨平台差异尚未定因。',
'- 构建清单：`../windows_build_manifest.json`；源码一致性：`../windows_source_integrity.json`。',
'','## compare 最新版本的 20 个案例','',
'本批次实际调用 Windows PLECS 4.8.2 的后台 RPC 与新编译 PULSE。Buck、Boost 均完成 0.3 s；每例 7 个显示电气通道的 RMS、max、mean 共 21 项均通过冻结的 `atol + 1% × |PLECS|` 容差。启动/稳态叠加图已复核。',
'','其余 14 个案例因转换器不支持控制模块/测量映射而未生成可运行对照，4 个案例在 PULSE 原版报 `MODEL_SINGULAR`。这些状态不是电气一致性通过。',
'','| Case | 本次结果 | 说明 |','|---|---|---|']
for case,status,detail in rows:lines.append(f'| [{case}]({case}/result.json) | {status} | {detail.replace("|","/")} |')
lines+=['','## 查看有效结果','',
'- [Buck 启动](rohm-c006-d-buck-v001/startup.png)、[Buck 稳态](rohm-c006-d-buck-v001/steady.png)、[统计 CSV](rohm-c006-d-buck-v001/statistics.csv)。',
'- [Boost 启动](rohm-c002-d-boost-v002/startup.png)、[Boost 稳态](rohm-c002-d-boost-v002/steady.png)、[统计 CSV](rohm-c002-d-boost-v002/statistics.csv)。',
'- 每例包含原始 PULSE NPZ、日志、实时 PLECS NPZ、通道映射、模型副本、源文件哈希和逐 XML 归档来源。',
'','## 判断范围','',
'统计采用各案例冻结统计窗，按已知开关时序分段积分。PLECS 采集初始 5 ms、统计窗、最终 0.2 ms，不是连续全历史输出；不能跨窗口空档插值。叠加图直接使用原时间戳，未人为平移对齐。开关左右值和采样网格可造成边沿绘图差别，图形复核不推断亚采样间隔精度。',
'','两个有效案例的模型结构已做 AST 对比：去掉新增的纯测量 Probe/Output 后，与原始模型完全一致。源目录缺失的中文 XML 从同案例冻结 ROHM ZIP 恢复原始字节到运行副本，不替换器件模型。',
'','热域/损耗等原案例跳过项仍未在 PULSE 中验证。本次独立电气对照不替代旧库的全部验收要求，不覆盖旧报告，不构成所有电路或所有连续时刻的正确性证明。旧文档的 PLECS 5.0.4 Demo 基准与本次本机 4.8.2 基准分别保存。',
'','早期批次保留作工具调试证据；`windows_compare_live_03` 全零值由生成器把新增连接放在 Annotation 区块之后导致，已经以 400 V 冒烟验证修复，不应把该批次当作电气失败。最终判断只采用当前 final 批次。',
'','## 复跑','',
'在项目根目录运行 `./build_windows.ps1` 构建并测试，`./compare_windows.ps1` 对照所有最新案例；`./compare_windows.ps1 -Case rohm-c006-d-buck,rohm-c002-d-boost` 只跑两个已完成案例。每次建立独立报告目录。',
'','PLECS RPC 耗时包括结果传输和 XML 解码；PULSE 耗时包括 CLI 输出保存，两者不能直接用来宣称求解内核速度比。']
(out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
w.dump(out/'review_summary.json',{'cases':[{'case':a,'reviewed_status':b,'detail':c} for a,b,c in rows],'counts':dict(Counter(b for _,b,_ in rows))})
print(Counter(b for _,b,_ in rows))
