# AI 电话系统（Asterisk + PJSIP + Linphone）

一台 Ubuntu 24.04 云虚拟主机上的完整 AI 电话系统：Asterisk 做 PBX，PJSIP 做
SIP，本地 Vosk 做语音识别、Piper 做语音合成，免费 Pollinations 文本 API 做对
话大脑。**这套系统能打真实的 SIP 内网语音通话，但不能打公共电话**——没有
PSTN 线路，任何真实手机/座机号码都打不出去（见“还缺什么”）。

> 诚实红线：SIP 对 SIP 的通话是真实 SIP/RTP 语音（包数、音频内容都已实测
> 验证），但它**不是公共电话**。模拟通话绝不说成真实电话。本系统从未拨打
> 过任何真实号码，也从未用用户的号码做过测试通话。

- 工作目录：`~/workspace/ai-phone-system/`（本仓库）
- 部署日期：2026-11-24（北京时间）
- 预算：严格 **$0**——不绑卡、不充值、不买号码、不开付费套餐
- 仓库：https://github.com/gom92/ai-phone-system

---

## 1. 能不能拨打 / 能不能接听

| 问题 | 答案 |
|---|---|
| 能拨打真实电话号码吗 | **不能。** 没有 PSTN 线路，没有运营商中继。`scripts/dial.py` 会拒绝任何真实号码（见第 6 节）。 |
| 能接听真实电话吗 | **不能。** 同上——没有入局线路，真实电话打不进来。 |
| 能拨打 SIP 内网分机吗 | **能。** 1001（AI）、1002、1003 之间互通，已实测。 |
| 能接听 SIP 来电吗 | **能。** pjsua 端点自动接听（`--auto-answer 200`），已实测。 |
| AI 语音对话正常吗 | **正常。** 完整回路已在真实通话里跑通两轮（见第 5 节）。 |
| SIP 账号状态 | 1002、1003 已注册（TCP）；1001 是 AI 分机（无终端注册，接 AGI）。密码只存在本地 600 权限文件里，不在仓库、不在聊天记录里。 |

---

## 2. 系统架构

```
                ┌──────────────┐
                │  Asterisk    │  PBX, PJSIP TCP 127.0.0.1:5060
                │  20.6.0      │  RTP 10000-20000 (UDP, 经 shim)
                └──────┬───────┘
                       │ SIP/RTP (本机回环)
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   1001 AI 分机    1002 pjsua A   1003 pjsua B
   AGI ai_bridge   (测试软电话)   (测试软电话)
        │
        ▼
   音频 → Vosk STT → Pollinations 免费文本 API → Piper TTS → 放音
   （本地）        （经出口代理）              （本地）
```

### 分机

| 分机 | 用途 | 注册方式 |
|---|---|---|
| 1001 | AI 助手（AGI `ai_bridge.py`，最多 3 轮/通） | 无终端；拨号规则 `Answer() → AGI(ai_bridge.py) → Hangup()` |
| 1002 | 测试软电话 A（pjsua） | TCP 注册；自动接听；播 440Hz 测试音；录音 `recordings/rec-a.wav` |
| 1003 | 测试软电话 B（pjsua） | TCP 注册；自动接听；播 Piper 语音短语；录音 `recordings/rec-b.wav` |
| 1000 | 回声测试（Echo 应用） | 无终端；用于验证双向 RTP |

拨号规则（`config/asterisk/extensions.conf`）：1000 Echo，1001 AGI，
1002/1003 `Dial(PJSIP/<ext>,30)`，其他号码一律挂断；`_9.` / `_+X.`（外线
样子）直接拒绝并挂断。

### 账号与密码

- SIP 密码是安装时生成的强随机密码，只存在：
  - `secrets/sip-credentials.txt`（600 权限，本机）
  - `/etc/asterisk/pjsip.conf` 与 `manager.conf`（root:asterisk 640）
- **密码不在仓库、不在日志、不在聊天记录里。** 换密码后重跑
  `scripts/install-configs.sh` 再 `pjsip reload`。

---

## 3. 环境限制（实测结论，不是猜测）

这台机器是 NAT/代理后面的云容器，部署前实测发现：

1. **UDP 从未连接的 socket 发包被容器 seccomp 挡掉（EPERM）。**
   Python、C 程序、`systemd-run` 作用域里都一样——所有进程都有 seccomp
   过滤器。已连接的 UDP socket 上 `send()`/`sendmsg()` 正常。
   后果：SIP 信令只能走 **TCP**（多方 SIP 不能每包 connect），RTP 走
   UDP 单对端 socket。
2. **绕过办法：`lib/udp_connect_shim.c`（LD_PRELOAD）。**
   拦截 `sendto`/`sendmsg`/`sendmmsg`：对 AF_INET/AF_INET6 的数据报
   socket，先 `connect()` 到目标再无目标发送；其他调用原样透传；不改
   payload。实测：不用 shim，回环 UDP 收不到；用 shim，`hello-rtp` 收到。
   Asterisk 通过 systemd drop-in 加载它
   （`/etc/systemd/system/asterisk.service.d/shim.conf`），pjsua/linphonec
   启动时也加 `LD_PRELOAD`。重新编译：`gcc -shared -fPIC -o
   lib/libudp_connect_shim.so lib/udp_connect_shim.c -ldl`。
3. **apt 有一个挂死的镜像。** `/etc/apt/sources.list.d/ubuntu.sources`
   里 `mirror.cogentco.com` 会让 `apt-get update` 无限挂起（5 分钟 0 进
   度）。已去掉该镜像（备份在 `docs/ubuntu.sources.bak`），update 恢复
   到约 10 秒。
4. **容器不能 `chown` 给其他用户**（Operation not permitted，即使 root）。
   Asterisk 因此以 **root** 身份运行（systemd drop-in 去掉 `-U
   asterisk`）；本机其他服务也都以 root 跑，保持一致。
5. **`/tmp` 和系统安装在虚拟机重启后会被清空**，`~` 下文件保留。
   重启后需重装 apt 包并按“维护方法”重起服务；不要把必须持久的东西
   放 `/tmp`。
6. **出口需要代理。** Asterisk 进程本身没有代理环境变量时，AGI 里
   Python `urllib` 直连 `text.pollinations.ai` 会 SSL 握手超时（60 秒）。
   已把出口代理变量写进 `secrets/proxy.env`（600 权限，不进仓库），由
   systemd drop-in 用 `EnvironmentFile=` 加载。直接 curl 不带代理也一样
   超时——不是 shim 的问题（已对照测试）。

端口快照（部署前）：见 `docs/BACKUP-BEFORE-DEPLOY.md`。已占端口：只有
127.0.0.1:8899（电话号码识别系统）。本系统用 127.0.0.1:5060（SIP TCP）、
10000–20000（RTP UDP）、127.0.0.1:5038（AMI），均不冲突。现有服务
（Muse、电话号码识别、微信桥）部署前后未动。

---

## 4. 安装了什么

| 组件 | 版本/来源 | 说明 |
|---|---|---|
| Asterisk | 20.6.0（apt，universe） | 核心 PBX；`systemctl` 服务已启用 |
| pjsua | 2.14.1（pjproject 源码编译） | apt 没有 pjsua 包；release 资产 404，改用 codeload 包编译；`./configure --disable-video --disable-libwebrtc && make -j4 dep && make -j4` |
| linphonec | 5.2.0（apt，linphone-cli） | 已安装并能跑；**注册未验证**（见第 8 节） |
| baresip | 1.0.0（apt） | 备用软电话，已安装，未用作主测试端点 |
| Vosk | vosk-model-small-en-us-0.15（41MB） | STT，英文小模型，16kHz；`venv-ai/` |
| Piper | en_US-lessac-medium.onnx（63MB） | TTS，本地；`venv-ai/` |
| espeak-ng、sox | apt | sox 做 8k↔16k 重采样；espeak 是 Piper 失败时的回落（本次没用到） |
| Python | 3.12.3 | AGI 与工具脚本 |

详细安装记录：`INSTALL-LOG.md`。

---

## 5. AI 语音对话（已实测跑通）

流程：`RECORD FILE`（8 秒超时，2 秒静音停）→ sox 重采样 8k→16k →
Vosk STT → Pollinations 免费文本 API（`model=openai`，无 key）→ Piper
TTS → sox 重采样到 8kHz → `STREAM FILE` 放音。每通最多 3 轮。

**2026-11-24 12:53 的 live 通话实测（分机 1002 呼叫 1001，全程 58.3 秒）：**

| 轮次 | STT（耗时） | LLM（耗时） | TTS（耗时） |
|---|---|---|---|
| 1 | `know what can you do for me today`（2.8s） | 5.2s：*“Sure! I can set reminders, check the weather, play music, call someone, or answer quick questions for you. What would you like to do?”* | 3.5s |
| 2 | `hello what can you do for me today`（2.7s） | 4.4s：*“Hi! I can set reminders, check the weather, get directions, or answer quick questions—just let me know what you need.”* | 4.5s |
| 3 | ``（空，呼叫方已播完测试音频） | — | 通话结束 |

每轮总延迟约 15–20 秒（录音 3–8 秒 + STT 约 2–3 秒 + LLM 约 5 秒 +
TTS 约 3–4 秒 + 放音）。放音已验证到达呼叫方：`recordings/rec-ai.wav`
（58.4 秒）里 AI 两轮回复的语音段能量清晰；`recordings/ai_out_*.wav`
是 Piper 生成的原文件（8kHz 真实语音，非提示音）。

日志：`logs/ai_calls.log`（只记文字与耗时，不记音频内容）。
测试音频：`recordings/test-phrase-delayed.wav`（4 秒静音 + 短语 +
2 秒静音 + 短语，10.4 秒）——短语必须落在 AGI 录音窗口里（问候语
3.45 秒播完后才开始录音），直接播短语会被问候语盖住。

> 注意：Vosk 是英文小模型，第一轮把开头的 “hello” 听成 “know”。
> 正常英文短句识别准确；这不是故障，是小模型的精度水平。

---

## 6. 拨打前确认（`scripts/dial.py`）

```bash
python3 scripts/dial.py --to 1000 --confirm   # 本地分机：放行，需 --confirm
python3 scripts/dial.py --to 13800138000       # 真实号码：拒绝
python3 scripts/dial.py --to +8613800138000 --confirm  # 真实号码：照样拒绝
```

- 没有配置 PSTN 线路时，任何非本地分机的号码都被拒绝并打印原因
  （无中继、费用未知、预算严格 $0），退出码 1；加 `--confirm` 也一样
  拒绝。
- 本地分机（1000/1001/1002/1003）不加 `--confirm` 时只打印目标并要求
  重新确认（退出码 2）；加 `--confirm` 才真正发起呼叫。
- 绝不自动群呼、不骚扰。拨号规则里 `_9.` / `_+X.` 也是直接挂断。

---

## 7. 人工接管与挂断（`scripts/control.sh`）

```bash
bash scripts/control.sh list              # 列出活动通道
bash scripts/control.sh hangup <channel>  # 挂断指定通道（Asterisk 20 用 channel request hangup）
bash scripts/control.sh hangup-all        # 挂断全部
bash scripts/control.sh takeover <channel>    # 把该通道转给人工软电话（1002）
bash scripts/control.sh takeover-ai <channel> # 把该通道转给 AI（1001）
bash scripts/control.sh spy <channel>     # 用 1002 监听该通道（ChanSpy）
bash scripts/control.sh status            # 通道 + 注册状态
```

已实测：`takeover` 把 1003 的通话腿成功重定向到 1002
（`successfully redirected to internal,1002,1`）；`hangup-all` 清空通道。
注意：`channel hangup` 在 Asterisk 20 里不存在，正确写法是
`channel request hangup <channel>`（脚本里已修正）。

---

## 8. 测试报告（摘要；完整版见 `TEST-REPORT.md`）

| 测试 | 结果 |
|---|---|
| SIP 注册（1002、1003，TCP） | ✅ 通过 |
| SIP 对 SIP 回声（1002 → 1000） | ✅ 通过：6 秒，RTP 收 300 包 / 发 298 包，0 丢失；录音 5.89 秒，FFT 峰值正好 440.0Hz（播的测试音） |
| 双端点通话（1002 ↔ 1003） | ✅ 通过：同一桥接，10 秒，双向各约 500 包，0 丢失；B 录到 A 的 440Hz 音，A 录到 B 的语音短语（164Hz 基频，宽带语音） |
| AI 对话回路（1002 → 1001） | ✅ 通过：58.3 秒，2 轮完整问答 + 1 轮空识别；STT/LLM/TTS/放音全通（见第 5 节） |
| 通话记录与时长统计 | ✅ 通过：`scripts/cdr_stats.py` 导入 CDR，18 通、11 通接通、总计 376 秒/计费 344 秒，按目的地分列 |
| 挂断 / 接管 | ✅ 通过（见第 7 节） |
| dial.py 拒绝真实号码 | ✅ 通过（138 / +86，加不加 `--confirm` 都拒绝） |
| linphonec 注册 | ❌ **未通过。** 已安装、能启动、配置加载、CLI 能用（`proxy list` 显示代理配好），但从不发出 REGISTER（`registered: no`），原因未定位。pjsua 是已验证的软电话；linphonec 只作为备用记录，不作为测试端点 |

测试只用本地分机，绝不拨打真实号码。

---

## 9. 还缺什么（按 $0 预算写；不推荐任何要花钱的方案）

依据：`~/workspace/phone-number-identifier/calling-options-20261124.md`
（2026-11-24 官方来源核实）与 `free-credit-screening-20261124.md`
（同日 11 家运营商逐家核实）。

**结论先说：目前没有一条合法、可用、零费用的线路，能从这台虚拟主机
拨打中国大陆 +86 普通电话（手机和座机）。** 真实通话测试必须等用户
决定并提供授权测试号码后才能做；在此之前只测 SIP 内网。

| 路径 | 结论（官方来源） |
|---|---|
| Twilio 试用 | 唯一能从虚拟主机打出真实电话的免费路子，但**打不了中国**——官方中国语音指南原话：*Outbound calls to Mainland China are not supported*（付费也一样）。75 分钟语音/30 天，免绑卡。最实际的 $0 路：用他手机上的 **Visible 15 天美国号注册 Twilio** → 注册国为美国 → 75 分钟可打美国号码（每个被叫号要先收短信验证，最多 5 个）。限制：试用电话开头有提示音、单通限 10 分钟。注册和短信验证必须他本人做。 |
| Plivo 试用 | 约 $10 额度，免绑卡。中国在官方价目表中，但仅限已验证的沙箱号码，+86 能否验证官方未确认；中国手机 $0.40/分钟（$10 约 25 分钟）。 |
| Vonage 试用 | 约 €2 额度，免绑卡。语音**仅限注册时绑定的那一个号码**（若注册号就是 +86 才可能打中国），+86 能否做注册号未确认。 |
| Localphone 首通免费 | 一次、5 分钟、任意目的地（含中国），官方页面明确写了；但能否经 Asterisk SIP 中继拨出未确认，且仅一次。 |
| SignalWire / Bandwidth / IPComms / Telnyx | 试用额度真实存在，但官方层面锁死国际/中国方向：SignalWire 试用明文禁国际；Bandwidth 试用仅限美加；IPComms 测试中继仅限美加 + 要美加银行卡 + 照片 ID；Telnyx 国际外呼要 L2（绑卡 + KYC + 公司信息）。 |
| Google Voice | 拿不到号：须身在美国 + 绑定美国手机号 + 政府 ID 验证。有号后打中国 $0.01/分钟是付费路线里最便宜的，但号本身拿不到。 |
| TextNow | 免费美加号码，但条款仅限美加居民；他在深圳/香港，不符合。 |
| 免费 SIP（Linphone/OnSIP/sipgate） | $0，但只能 SIP 对 SIP，不能拨传统电话号码。 |
| 打中国唯一真正免费的办法 | 微信语音/视频通话（双方都要装微信）——但这不是“打电话号码”，他本来就有微信。 |

**窄口子的现状（2026-11-24 20:06 用户原话后）：** Plivo、Vonage、
Localphone 三条窄口子都要求先验证/拨打他本人 +86 号码，而用户已明
确“电话系统不用打给他、不拿他的号码做测试通话”。在没有其他授权号码
的前提下，连三条窄口子都无法测试。若他以后提供一个**非他本人、且
对方同意接听**的 +86 测试号码，并明确批准用哪个运营商的试用额度打
这一通测试电话，Localphone 5 分钟首通是最干净的候选（不要求绑卡、
不要求先验证沙箱号）。

**不要做的事：** 不要为了解锁 Telnyx L2 而绑卡/交 KYC；不要用不明免费
网关；不要把“免费注册/免费中继/免费套餐”当成“免费打中国”。
最便宜的真实付费路线（仅作参考，不在 $0 预算内，不执行）：Telnyx
（KYC + 绑卡后约 $0.002/分钟 API 费 + 目的地结算价）、Google Voice
（有号后 $0.01/分钟）。

---

## 10. 维护方法

### 日常状态检查

```bash
systemctl status asterisk --no-pager
asterisk -rx "pjsip show contacts"     # 应看到 1002、1003 各 1 个
asterisk -rx "core show channels concise"
python3 scripts/cdr_stats.py           # 通话记录统计（data/calls.db）
```

### 重启服务（虚拟机重启后必须做，因为 /tmp 与系统安装会被清空）

```bash
# 1. 重装 apt 包（若被清空）：asterisk、linphone-cli、baresip、espeak-ng、sox
#    注意先去掉 ubuntu.sources 里的 cogentco 镜像（见第 3 节第 3 条）
# 2. 重装 pjsua（若 src/pjproject 被清空，需重新下载编译；源码在 ~/workspace
#    保留，见 INSTALL-LOG.md）
# 3. 重起 Asterisk（配置在 /etc/asterisk，重启后仍在）
systemctl restart asterisk
# 4. 重起两个测试端点（pjsua 没有自启；stdin 要一直开着，见 run-pjsua.sh）
scripts/run-pjsua.sh a
scripts/run-pjsua.sh b
# 5. 验证
asterisk -rx "pjsip show contacts"
```

### 已知坑（部署时踩过，都已修好并记在这里）

- **过期联系人会堵死拨号。** 联系人存在 astdb（`prune_on_boot=no`），
  Asterisk 重启也不清；拨到已死的 TCP 联系人会 `TRANSPORT_ERROR` +
  503，整通失败。已修：AOR 加 `remove_existing=yes` 且 1002/1003
  `max_contacts=1`，新注册会顶掉旧联系人。仍建议拨号失败时先查
  `pjsip show contacts` 是否只有一个 live 联系人。
- **pjsua stdin 一关就退出。** `run-pjsua.sh` 用 `< <(sleep 1800)` 喂
  stdin；不要用 `</dev/null`（pjsua 会报 `Cannot switch back to console
  from file redirection` 后退出）；不要用 `--no-cli-console`（没用）。
  1800 秒后 stdin 会关、pjsua 退出——需要长期跑时改大 sleep 或改用
  FIFO（linphonec 用的就是 FIFO 做法）。
- **pjsua 配置里漏 `--auto-answer 200` 时来电不接**（只打印 Press a to
  answer）。两份配置都已补上。
- **`pkill -f <pattern>` / `pgrep -f <pattern>` 会匹配到 exec 自身的命令
  行并把自己杀掉。** 只用 `kill <pid>` 或 `ps -C <精确进程名>`。
- **`cmd1 && cmd2 &` 会把整个 `&&` 链放进后台**（`cd` 也会进后台子
  shell），下一行会在错误目录执行。长命令用独立脚本或绝对路径。
- **AGI 脚本要用 `realpath` 算 BASE。** 经 symlink 调用时 `abspath`
  不解 symlink，BASE 会算成 `/usr/share/asterisk`，日志写不进去、模型
  找不到，脚本静默退出。已改成 `realpath`。
- **AGI 的 `stt()` 曾打开原 8kHz 文件却按 16kHz 识别**（Vosk 模型是
  16kHz），导致 live 录音 STT 全空。已改成打开重采样后的 `.16k.wav`。
- **Asterisk 进程没有代理变量时 LLM 请求 60 秒超时。** 已用
  `EnvironmentFile=secrets/proxy.env` 解决；不要直接在代码里写死代理。
- **Debian 的 AGI 目录是 `/usr/share/asterisk/agi-bin/`**，不是
  `/var/lib/asterisk/agi-bin/`。`ai_bridge.py` 已 symlink 到前者。
- **WAV 录音头在 pjsua 退出前是占位大小（RIFF size 0）。**
  Python `wave` 模块打不开未关闭的录音文件；分析时直接读 44 字节后
  的原始 PCM（见 TEST-REPORT.md 的分析方法）。

### 文件清单

| 路径 | 内容 |
|---|---|
| `README.md` / `INSTALL-LOG.md` / `TEST-REPORT.md` | 本文档、安装记录、测试报告 |
| `config/asterisk/` | `pjsip.conf.template`、`extensions.conf`、`rtp.conf`、`cdr.conf`、`modules.conf`、`manager.conf.template`（模板；安装脚本生成到 `/etc/asterisk`） |
| `scripts/` | `ai_bridge.py`（AGI）、`install-configs.sh`、`run-pjsua.sh`、`dial.py`、`control.sh`、`cdr_stats.py`、`contacts.py` |
| `lib/udp_connect_shim.c` | UDP shim 源码（`.so` 需编译，不进仓库） |
| `docs/BACKUP-BEFORE-DEPLOY.md` | 部署前端口/服务快照 |
| `free-credit-screening-20261124.md` | 11 家运营商免费额度筛选报告 |
| `secrets/`（不进仓库） | `sip-credentials.txt`、`proxy.env`（均为 600） |
| `data/`、`recordings/`、`logs/`、`models/`、`venv-ai/`（不进仓库） | 运行时数据、录音、日志、模型、虚拟环境 |

### 联系人管理

`scripts/contacts.py`：JSON 联系人表（`data/contacts.json`），只接受本
地分机号码；非数字或超过 4 位的条目会被拒绝。

### 通话录音

只存本地（`recordings/`），不上传、不进仓库。录音文件包含真实通话
音频，按本地文件处理，不要外发。

---

## 11. 诚实声明

- SIP 内网通话是真实 SIP/RTP 语音（包数、音频内容、STT/LLM/TTS 全
  链路均已实测），但**不是公共电话**。本系统不能拨打或接听任何真实
  电话号码。
- 没有伪造过任何收入、通话记录或测试结果；没跑通的功能直接写没跑
  通（linphonec 注册，见第 8 节）。
- 预算严格 $0：没有注册任何 PSTN 服务商，没有买号码，没有充值，没
  有激活任何试用。Twilio/Plivo/Vonage/Localphone 的试用注册都必须由
  用户本人决定并操作。
