# 测试报告（TEST-REPORT）

测试日期：2026-11-24（北京时间）。测试范围：**只测 SIP 内网，不测真实
电话**。测试号码只用本地分机（1000/1001/1002/1003），绝不拨打任何真实
号码。所有结论都有日志、CDR 或录音文件作证，不凭感觉写。

---

## 1. 环境与前置

- Asterisk 20.6.0 运行中（`systemctl status asterisk` active，Main PID
  随重启变化）；PJSIP TCP 127.0.0.1:5060；RTP 10000–20000。
- pjsua 2.14.1（源码编译），linphonec 5.2.0，baresip 1.0.0。
- 录音分析方法：pjsua 的 WAV 头在录音器关闭前是占位大小（RIFF size
  0），Python `wave` 模块打不开未关闭的录音文件；分析时直接读 44 字节
  后的原始 PCM（16kHz 单声道 16-bit），用 numpy 做 FFT 与能量分析。

## 2. SIP 注册

| 端点 | 结果 | 证据 |
|---|---|---|
| 1002（pjsua A，TCP） | ✅ 通过 | `pjsip show contacts` 有 `1002/sip:1002@127.0.0.1:<端口>;transport=TCP;ob` |
| 1003（pjsua B，TCP） | ✅ 通过 | 同上，1003 有 1 个 live 联系人 |
| 1001（AI 分机） | ✅ 按设计 | 无终端注册；拨号规则接 AGI |

中间故障（已修）：`[1003]` type=aor 段缺失 → 注册报 `AOR '1003' not
found`；补段 + `pjsip reload` 后注册成功。

## 3. SIP 对 SIP 回声通话（1002 → 1000 Echo）

- 呼叫接通：CDR `1000 internal ANSWERED`，时长 6 秒，计费 5 秒。
- `pjsip show channelstats`（通话中）：codec ulaw，**Receive 300 包 /
  Transmit 298 包，丢失 0，抖动 0.001–0.004**。
- `rtp set debug on` 期间 full 日志记到 299 条 RTP 包收发记录。
- 录音 `recordings/rec-a.wav`：5.89 秒 @16kHz，RMS 16210，峰值 23413，
  93,038 个非零采样；1 秒窗 FFT **峰值正好 440.0Hz**（两侧 439/441Hz
  为加窗旁瓣）——录到的就是 A 播的 440Hz 测试音经 Echo 返回的音频。
- **结论：SIP 信令 + 双向 RTP + 音频内容三者都通。**

中间故障（已修）：首次 originate 失败——当时 A 的配置漏了
`--auto-answer 200`，pjsua 只打印 `Press a to answer` 不接听，30 秒
后 Asterisk CANCEL；补上后接通。

## 4. 双端点通话（1002 ↔ 1003）

- 呼叫接通：CDR `1003 internal ANSWERED`，时长 10 秒，计费 9 秒。
- `pjsip show channelstats`（通话中）：两条通道在**同一桥接**
  （BridgeId 57cc0bf8），各 10 秒，ulaw；
  - 1002 腿：Receive 500 包 / Transmit 498 包，丢失 0；
  - 1003 腿：Receive 498 包 / Transmit 496 包，丢失 0。
- 录音内容交叉验证（FFT + 能量）：
  - `recordings/rec-b.wav`（B 录到的）：9.9 秒，峰值 **440.0Hz**，
    1kHz 以上能量占比 0.000——纯音，正是 A 播的 440Hz 测试音。
  - `recordings/rec-a.wav`（A 录到的）：9.9 秒，峰值 164Hz（语音基频），
    1kHz 以上能量占比 0.039（宽带语音）——正是 B 播的 Piper 语音短语。
- **结论：双向语音通，且内容正确交叉到达对方。**

## 5. AI 对话回路（1002 → 1001）

测试音频：`recordings/test-phrase-delayed.wav`（4 秒静音 + 短语 +
2 秒静音 + 短语，10.4 秒）。短语内容：“Hello, what can you do for me
today?”

### 5.1 完整通话（2026-11-24 12:53:33–12:54:31，全程 58.3 秒）

| 轮次 | 录音 | STT（耗时） | LLM（耗时） | TTS（耗时） |
|---|---|---|---|---|
| 1 | 2.9 秒 | `know what can you do for me today`（2.8s） | 5.2s，真实回复：“Sure! I can set reminders, check the weather, play music, call someone, or answer quick questions for you. What would you like to do?” | 3.5s → `ai_out_…_1.wav`（126,918 字节） |
| 2 | 4.1 秒 | `hello what can you do for me today`（2.7s） | 4.4s，真实回复：“Hi! I can set reminders, check the weather, get directions, or answer quick questions—just let me know what you need.” | 4.5s → `ai_out_…_2.wav`（111,872 字节） |
| 3 | 1.0 秒 | ``（空，呼叫方已播完测试音频） | — | 通话结束（`call end total=58.3s`） |

- CDR：`1001 internal ANSWERED`，58 秒，计费 58 秒。
- 放音到达呼叫方已验证：`recordings/rec-ai.wav`（58.4 秒）按 2 秒窗
  的能量分布与 AI 两轮回复的播放时段一致（问候语段 → 静音录音段 →
  第一轮回复语音段 → 静音 → 第二轮回复语音段）；`ai_out_1.wav` 为
  7.9 秒真实语音（1kHz 以上能量占比 0.104，宽带语音，非提示音）。
- 每轮总延迟约 15–20 秒（录音 3–8 秒 + STT 约 2–3 秒 + LLM 约 5 秒 +
  TTS 约 3–4 秒 + 放音）。
- **结论：音频 → STT → LLM → TTS → 放音，全链路在真实通话里跑通
  两轮。**

### 5.2 过程中修掉的三个 AI 回路故障（都记在这里，不粉饰）

1. **AGI 不执行。** 拨号规则调 `AGI(ai_bridge.py)`，Asterisk 报
   `Failed to execute '/usr/share/asterisk/agi-bin/ai_bridge.py': File
   does not exist`。根因：脚本 symlink 在 `/var/lib/asterisk/agi-bin/`
   （该目录根本不存在），Debian 版用的是
   `/usr/share/asterisk/agi-bin/`。已修正。
2. **AGI 静默退出。** 环境发完后脚本无任何回令、无日志。根因：
   `abspath(__file__)` 不解 symlink，BASE 算成 `/usr/share/asterisk`，
   `log()` 打开不存在的目录抛错，脚本在记第一行日志前就崩了。已改成
   `realpath(__file__)`，`log()` 加建目录保护。
3. **STT 全空。** 录音文件能量很高（RMS 约 5000），Vosk 却返回空。
   根因：`stt()` 重采样到 `.16k.wav` 后又打开原 8kHz 文件按 16kHz 识
   别（Vosk 模型是 16kHz）。已改成打开重采样后的文件并固定 16000；
   修复后直接对录音文件跑 STT 得到 `hello what can you do for me today`。
4. **LLM 60 秒超时。** `urlopen error _ssl.c:983: The handshake operation
   timed out`。根因：Asterisk 进程没有代理环境变量，直连
   `text.pollinations.ai` 握手超时（不带代理的 curl 同样超时；带代理
   0.77 秒 200）。已在 systemd drop-in 加
   `EnvironmentFile=secrets/proxy.env`；修复后 LLM 4.4–5.2 秒返回真实
   回复。超时期间脚本按设计用备用回复继续，不会卡死整通电话。

### 5.3 其他说明

- Vosk 是英文小模型，第一轮把开头的 “hello” 听成 “know”；第二轮听
  对。这是小模型的精度水平，不是故障。
- 测试短语必须用延迟版：AGI 先播 3.45 秒问候语再录音，直接播短语会
  被问候语盖住（第一次 live 测试 STT 为空就是这个原因）。

## 6. 通话记录与时长统计

- `python3 scripts/cdr_stats.py`：从 `/var/log/asterisk/cdr-csv/Master.csv`
  导入 `data/calls.db`（SQLite），去重后统计。
- 截至 2026-11-24 12:55：**18 通、11 通接通、总计 376 秒、计费 344 秒**；
  按目的地：1001（AI）8 通/316 秒，s（拨号失败的 originate）7 通/0 秒，
  1000（Echo）2 通/19 秒，1003 1 通/9 秒。
- 中间故障（已修）：按目的地统计的 SQL 用了不存在的列别名 `c`
  （`ORDER BY c DESC`），报 `no such column: c`；已改成 `COUNT(*) AS c`。

## 7. 挂断 / 接管（`scripts/control.sh`）

| 操作 | 结果 |
|---|---|
| `list`（通话中） | ✅ 显示 2 条活动通道、1 通活动通话 |
| `takeover <1003 通道>` | ✅ `Channel 'PJSIP/1003-00000006' successfully redirected to internal,1002,1`；重定向后该通道位置变为 `internal!1002!2!Up!Dial!PJSIP/1002,30`，并新起一条呼叫人工软电话的通道 |
| `hangup-all` | ✅ 通道清空（0 条）。注：挂第一条腿时桥接已拆，第二条会报 `is not a known channel`，属于清理时的正常现象，不影响结果 |
| `spy` | 未在 live 通话里实测（命令已就绪：`channel originate PJSIP/1002 application ChanSpy <通道>,q`）；接管已验证，监听走同一机制 |

注：Asterisk 20 没有 `channel hangup` 命令，正确写法是
`channel request hangup <channel>`（脚本里已修正）。

## 8. 拨打前确认（`scripts/dial.py`）

| 输入 | 结果 |
|---|---|
| `--to 13800138000`（无 `--confirm`） | ❌ 拒绝，退出码 1：“is not a local extension. This PBX has no PSTN trunk…” |
| `--to 13800138000 --confirm` | ❌ 拒绝，退出码 1（加确认也一样拒绝） |
| `--to +8613800138000 --confirm` | ❌ 拒绝，退出码 1 |
| `--to 1000`（无 `--confirm`） | 打印目标并要求重新确认，退出码 2 |
| `--to 1000 --confirm` | ✅ 放行，originate 成功，通道 Up（Echo） |

## 9. linphonec（未通过，如实记录）

- 已安装（5.2.0），能启动，配置文件加载（日志确认），CLI 可用
  （`proxy list` 显示代理配好：`sip:127.0.0.1:5060;transport=tcp`，
  identity `sip:1003@127.0.0.1:5060`，`register: yes`，`expires: 3600`）。
- **但从不发出 REGISTER**（`registered: no`；`-d 6`  full 调试日志里也
  没有 SIP 事务；Asterisk 侧联系人无变化）。`register` 命令显式执行后
  也一样。
- 未定位根因。怀疑方向：该版本 liblinphone 在无声卡容器里注册状态机
  未触发，或代理配置键名与版本不匹配。pjsua 是已验证的软电话；
  linphonec 只作为“已安装的备用软电话”记录，不作为测试端点。
- 附带现象：无声卡导致 ALSA/PulseAudio 报错（容器里没有音频设备，
  预期内，不影响 pjsua 的 `--null-audio` 路线）；linphone 数据库目录
  不存在（`~/.local/share/linphone/`），只影响通话历史持久化。

## 10. 拨号失败的系统性原因（已修，记录备查）

- 过期联系人堵死拨号：联系人存在 astdb（`prune_on_boot=no`），Asterisk
  重启也不清；拨到已死的 TCP 联系人时 `TRANSPORT_ERROR` + 503，整通
  失败（CDR 里 12:29:30、12:30:11、12:31:36、12:32:03 四次 originate
  0 秒失败都是这个原因；唯一成功的一次只有一个 live 联系人）。
  修复：AOR 加 `remove_existing=yes`，1002/1003 `max_contacts=1`。
- 另有两次 originate 失败是测试端点已退出（A 未启动）所致，与配置无关。

## 11. 未测 / 未验证

- linphonec 注册与通话（见第 9 节）。
- `control.sh spy` 的 live 监听（命令就绪，未实测）。
- 任何真实电话号码的拨打/接听（无 PSTN 线路；按 $0 预算与用户要求，
  真实通话测试须等用户决定并提供授权测试号码后才能做）。
- Asterisk 重启后的完整重装流程（apt 包 + pjsua 编译）未在本次任务
  里走第二遍；步骤见 README 第 10 节与 INSTALL-LOG.md。
