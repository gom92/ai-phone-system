# 安装记录（INSTALL-LOG）

部署日期：2026-11-24（北京时间）。环境：Ubuntu 24.04 云容器，约 4 vCPU、
7.7GB 内存，root；重启会清空 /tmp 与系统安装，`~` 下文件保留。
现有服务（Muse、电话号码识别系统 127.0.0.1:8899、微信桥）部署前后未动、
未重启、未删除。

---

## 0. 部署前检查

- 端口快照已写入 `docs/BACKUP-BEFORE-DEPLOY.md`。部署前唯一 TCP 监听是
  127.0.0.1:8899（电话号码识别系统）；微信桥不监听 TCP 端口；无 UDP 监听。
- 内存：约 1.35GB 可用（hatch daemon 约 500MB RSS 是最大头）；磁盘 113GB 空闲。
- 网络实测：
  - HTTP(S) 出口经代理正常；shell curl 直连部分主机正常。
  - **UDP 从未连接的 socket 发包被容器 seccomp 挡掉（EPERM）**——Python、C
    程序、`systemd-run` 作用域里都一样。已连接的 UDP socket 上
    `send()`/`sendmsg()` 正常；TCP 回环与 TCP 出口正常。
  - 结论：SIP 信令走 TCP；RTP 走 UDP 单对端 socket（见 README 第 3 节）。

## 1. apt

- `apt-get update` 被 `mirror.cogentco.com` 挂死（5 分钟 0 进度、0 CPU）。
  修复：备份 `/etc/apt/sources.list.d/ubuntu.sources` 到
  `docs/ubuntu.sources.bak`，去掉 cogentco 镜像，update 恢复到约 10 秒。
- 安装：`asterisk` 20.6.0（universe）、`linphone-cli` 5.2.0（linphonec）、
  `baresip` 1.0.0、`espeak-ng`、`sox`。
- `pjsua` 没有 apt 包，见第 2 节。

## 2. pjsua（pjproject 2.14.1，源码编译）

- release 资产 URL 返回 404 Not Found；改用 codeload tarball
  （10,322,231 字节），解压到 `src/pjproject/`。
- `./configure --disable-video --disable-libwebrtc && make -j4 dep && make -j4`
  → BUILD_OK。二进制：
  `src/pjproject/pjsip-apps/bin/pjsua-x86_64-unknown-linux-gnu`。
- 关键选项（实测确认）：`--play-file=<文件>` 与 `--auto-play` 是两个独立
  flag（不是 `--auto-play <文件>`）；`--rec-file` 与 `--auto-rec` 同理；
  `--auto-answer=code`；`--null-audio`；`--local-port`；`--rtp-port`；
  `--ip-addr`；`--no-udp`。

## 3. UDP shim（`lib/udp_connect_shim.c`）

- LD_PRELOAD 库，拦截 `sendto`/`sendmsg`/`sendmmsg`：对 AF_INET/AF_INET6
  数据报 socket，先 `connect()` 到目标再无目标发送；其他调用透传；不改
  payload。
- 编译：`gcc -shared -fPIC -o lib/libudp_connect_shim.so lib/udp_connect_shim.c -ldl`。
- 验证：不用 shim，回环 UDP 收不到（recvfrom 超时）；用 shim，
  `hello-rtp` 收到。
- Asterisk 经 systemd drop-in
  （`/etc/systemd/system/asterisk.service.d/shim.conf`）加载；pjsua /
  linphonec 启动时加 `LD_PRELOAD` 环境变量。

## 4. Asterisk 配置

- `scripts/install-configs.sh` 生成强随机 SIP 密码，写入
  `secrets/sip-credentials.txt`（600）与 `/etc/asterisk/{pjsip,manager}.conf`
  （root:asterisk 640）；模板在 `config/asterisk/`。
- PJSIP：TCP-only transport 127.0.0.1:5060；端点 1001（AI，接 AGI）、1002、
  1003；编解码 ulaw/alaw；`direct_media=no`。
- 拨号规则（`config/asterisk/extensions.conf`）：1000 Echo()，1001
  Answer + AGI(ai_bridge.py)，1002/1003 Dial(PJSIP/<ext>,30)；`_9.` /
  `_+X.` 拒绝并挂断；未知 `_X.` 挂断。
- `rtp.conf` 10000–20000，`strictrtp=no`，`icesupport=no`；`cdr.conf` CSV
  开启（Master.csv）；`manager.conf` AMI 127.0.0.1:5038；`modules.conf`
  autoload + `noload = chan_sip.so`。
- systemd drop-in：Asterisk 以 **root** 运行（容器不能 chown 给 asterisk
  用户；去掉 `-U asterisk`）+ `LD_PRELOAD` shim + 后来追加的
  `EnvironmentFile=secrets/proxy.env`（AGI 的 LLM 请求要用出口代理）。
- 部署中修掉的配置问题：
  - `/etc/asterisk/pjsip.conf` 曾缺失 `[1003]` type=aor 段（模板里有，
    安装时用的旧模板没有）→ 1003 注册报 `AOR '1003' not found`。已补，
    `pjsip reload` 生效。
  - AOR 追加 `remove_existing=yes`，1002/1003 `max_contacts=1`（见第 7 节）。
  - `logger.conf` 追加 `full => notice,warning,error,verbose,debug`，供排障。

## 5. 语音识别与合成

- `venv-ai/`：`vosk` + `piper-tts`（pip 安装通过）。
- Vosk 模型 `vosk-model-small-en-us-0.15`（41MB）；Piper 语音
  `en_US-lessac-medium.onnx`（63MB）+ `.onnx.json`。
- Vosk 小模型是 16kHz，Asterisk 录音是 8kHz——`ai_bridge.py` 的 `stt()`
  先用 sox 重采样 8k→16k（第一次 STT 测试报采样率不匹配后修好）。
- 离线验证（2026-11-24）：Piper 句子 → Vosk 识别完全一致（“hello what
  can you do for me today”），约 2.2 秒含模型加载；Piper 合成一句约 2 秒；
  Pollinations 文本 API “what is two plus two?” → “Four.”，约 4.8 秒。

## 6. AGI 桥接（`scripts/ai_bridge.py`）

- 流程：RECORD FILE（wav，# 键打断，8 秒超时，静音 s=2）→ sox 重采样 →
  Vosk STT → Pollinations（GET，model=openai，短回复提示）→ Piper TTS →
  sox 重采样到 8kHz → STREAM FILE；每通最多 3 轮；日志只记文字与耗时到
  `logs/ai_calls.log`。
- 问候语与无应答提示预生成在 `recordings/greeting.wav`、`nocatch.wav`。
- 部署中修掉的 bug：
  - Debian 的 AGI 目录是 `/usr/share/asterisk/agi-bin/`，不是
    `/var/lib/asterisk/agi-bin/`（后者根本不存在，AGI 报 File does not
    exist）。已 symlink 到前者。
  - 经 symlink 调用时 `abspath(__file__)` 不解 symlink，BASE 会算成
    `/usr/share/asterisk`，日志写不进去、模型找不到，脚本静默退出。已改
    成 `realpath(__file__)`，`log()` 也加了建目录保护。
  - `stt()` 重采样到 `.16k.wav` 后又打开原 8kHz 文件按 16kHz 识别，live
    录音 STT 全空。已改成打开重采样后的文件并固定 16000。
  - AGI 进程没有代理环境变量时 LLM 请求 SSL 握手超时 60 秒。已在
    systemd drop-in 加 `EnvironmentFile=secrets/proxy.env`（600 权限，
    不进仓库）；直接 curl 不带代理也一样超时，已对照排除 shim 的嫌疑。

## 7. 联系人过期问题（部署时踩的大坑）

- 现象：originate 到 1002 在有多个联系人时 0 秒失败，
  `TRANSPORT_ERROR` + 503；唯一成功的一次只有一个 live 联系人。
- 根因：联系人存在 astdb（`/registrar/contact/`，`prune_on_boot=no`），
  Asterisk 重启也不清；拨到已死的 TCP 联系人会先失败并终止整通拨号。
- 修复：AOR 加 `remove_existing=yes`，1002/1003 `max_contacts=1`，新注
  册顶掉旧联系人；测试前确认 `pjsip show contacts` 每个分机只有 1 个
  live 联系人。

## 8. 测试端点

- pjsua A（1002，`scripts/run-pjsua.sh a`）与 B（1003，`run-pjsua.sh b`）：
  TCP 注册、`--auto-answer 200`、`--null-audio`、播音 + 录音。
- pjsua stdin 一关就退出：`run-pjsua.sh` 用 `< <(sleep 1800)` 喂 stdin；
  `</dev/null` 会报 `Cannot switch back to console from file redirection`
  后退出；`--no-cli-console` 没用。
- AI 测试配置 `data/pjsua-a-ai.cfg`：播
  `recordings/test-phrase-delayed.wav`（4 秒静音 + 短语 + 2 秒静音 +
  短语），录到 `recordings/rec-ai.wav`；`run-pjsua.sh a-ai` 启动。
- linphonec（1003，`data/linphonec-1003.rc`，TCP，本地端口 5072）：
  能启动、配置加载、CLI 可用，但从不发出 REGISTER（见 TEST-REPORT.md）。

## 9. 仓库

- https://github.com/gom92/ai-phone-system（公开空仓库，父代理创建）。
- 只推 UTF-8 文本文件：README/INSTALL-LOG/TEST-REPORT、`.gitignore`、
  `config/asterisk/*`、`scripts/*`、`lib/udp_connect_shim.c`、
  `docs/BACKUP-BEFORE-DEPLOY.md`、`free-credit-screening-20261124.md`。
- 不推：`secrets/`（密码、代理凭证）、`data/`（含 pjsua 配置里的密码、
  calls.db）、`recordings/`、`logs/`、`models/`、`venv-ai/`、
  `src/pjproject/`（175MB，可重建）、`lib/*.so`（二进制编译产物）。
  见 `.gitignore`。

## 10. 未完成 / 已知限制

- linphonec 注册未验证（见 TEST-REPORT.md）。
- pjsua 实例没有自启；`run-pjsua.sh` 的 stdin 保持 1800 秒，过期后
  pjsua 退出，需重起（或改用 FIFO 做法，见 README 第 10 节）。
- 重启虚拟机后需重装 apt 包与 pjsua（/tmp 与系统安装会被清空）；
  `/etc/asterisk` 配置与 `~/workspace` 文件保留。
- 没有 PSTN 线路；真实通话测试等用户决定（见 README 第 9 节）。
