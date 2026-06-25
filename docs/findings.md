# QQMusicApi 地区版权绕过完整研究报告

> **测试环境**：新加坡 IP, QQ 音乐账号 `musicid=2685843396`(有绿钻 VIP), 库 `qqmusic-api-python==0.6.1`, 测试时间 2026-05
> **测试方式**: 所有结论均经过实测验证 (含 84 项稳定性矩阵 + HEAD 实际文件大小验证)

---

## TL;DR 极简结论

**只需要不传 `ct` 字段 + 带 `qq+authst` 认证就能完全绕过地区版权**:

```python
payload = {
    "comm": {"qq": str(cred.musicid), "authst": cred.musickey},
    "req_0": {
        "module": "music.vkey.GetVkey",
        "method": "UrlGetVkey",
        "param": {
            "filename": [f"M500{mid}{mid}.mp3"],   # 或 M800/F000/AI00/Q000
            "guid": uuid.uuid4().hex,
            "songmid": [mid],
            "songtype": [0],
        },
    },
}
# POST https://u.y.qq.com/cgi-bin/musicu.fcg
```

任何品质 (MP3_128 → MASTER 母带) 都能拿到完整明文 URL, 任何账号 (含免费小号) 都行, 不需要 VIP, 不需要付费等级.

---

## 一、问题起点

新加坡 IP 用 QQMusicApi 0.6.1 默认的 `client.song.get_song_urls()`:
- 大量歌曲返回 `result=104003` + `purl=空`
- 跟账号是否有 VIP 无关
- 跟歌曲的 `pay_play` 字段无关 (无法静态预判)
- QQ 音乐 APP 在新加坡也放不了同一首歌

## 二、根因定位 (消融实验)

从能成功的"全套 0.4.1 风格" baseline 出发, 逐一变量消融:

| 变量 | 改后结果 | 含义 |
|------|---------|------|
| 去 `uid=3931641530` (社区"魔法 UID") | ✅ | 完全无关 |
| `ct=19` 改回 `ct=11` | ❌ 104003 | **关键** |
| `cv=14090008` (最新版本号) | ✅ | 版本号无关 |
| 加完整 Android 设备指纹 | ✅ | 设备字段无关 |
| param 里加 `uin` | ✅ | 无关 |
| 去掉 `qq+authst` (匿名) | ❌ | 必须有认证 |
| 换 QQMusic Android UA | ✅ | UA 无关 |

**唯一开关是 `ct` 字段**. `uid=3931641530` 是个流传已久的误导.

## 三、`ct` 字段扫描 (0~100)

| 状态 | ct 值 | 备注 |
|------|------|------|
| ❌ 被风控 | 1, 3, 4, **11**, 18, **19**, 23, 27, 46 | 都对应"热门客户端" (ct=19 于 2026-06-07 实测新增黑名单, CDN Lego Server 直接 403) |
| ✅ 通过 | 其它所有值, 以及 **不传 ct** | 冷门/未注册值 |

**最终最稳方案**: 直接**不传 ct** (服务端走默认逻辑, 不应用地区策略).

## 四、稳定性验证

### 4.1 地区限制歌曲 (12 首) × 候选 ct (7 个) = 84 项

样本: 周杰伦《最伟大的作品》《稻香》《晴天》/ Ed Sheeran / 邓丽君 / 罗大佑 / 赵雷 / 逃跑计划 / 光良 / 马頔 / 陈奕迅 / 邓紫棋

**结果: 84/84 全部 ✅** 拿到完整 URL.

### 4.2 多音质验证 (HEAD 实测文件大小)

| 音质 | filename prefix | 实测大小 | 含义 |
|------|----------------|---------|------|
| MP3_128 | M500 | 3.73 MB | 标准 |
| MP3_320 | M800 | 9.31 MB | HQ |
| FLAC | F000 | 48.0 MB | SQ 无损 |
| **MASTER** | AI00 | **161.5 MB** | **臻品母带 24Bit/192kHz, 平时需豪华绿钻** |
| **ATMOS_2** | Q000 | **23.93 MB** | **臻品音质 (银河), 平时需 SVIP** |

**vkey 接口在"无 ct"路径下完全不校验音质权限**. 连付费才能听的母带都能拿.

## 五、必需字段

实测最简 comm:

| 字段 | 是否必需 | 说明 |
|------|---------|------|
| `qq` | ✅ | 真实 musicid |
| `authst` | ✅ | 对应 musickey |
| `tmeLoginType` | ⭕ | 可省 |
| `ct` | ❌ **省略** | 填 11/23/... 触发风控 |
| 其它 (`cv/v/tmeAppID/format/QIMEI/uid/device`) | ❌ | 全不需要 |

### tmeAppID 反直觉发现

| 值 | 结果 |
|------|------|
| `qqmusic` 或省略 | ✅ |
| `qqmusic_pc` / `qqmusic_web` / `qqmusic_mac` | ❌ 反触发版权检查 |

更具体的客户端 ID 反而启动版权策略.

### purl → 播放 URL 拼接: 有两种形态, 不能无脑拼 host (2026-06-26 实测)

`midurlinfo[].purl` 实测有**两种返回形态**, 由服务端 CDN 调度决定:

| 形态 | 例子 | 出现频率 |
|------|------|---------|
| **裸路径** | `F000{mid}{mid}.flac?guid=...&vkey=...` | 多数歌 |
| **完整 URL** (含 host) | `http://ws6.stream.qqmusic.qq.com/F000{mid}{mid}.flac?guid=...&vkey=...` | 个别歌 |

- 配套的 `sip` (CDN 根地址列表) 字段**两种形态下实测都是空 `[]`**。
- 形态切换跟请求参数**无关**: 实测加 `uin` + `ctx` (照 qqmusic-api `get_song_urls` 的写法) purl 形态不变, 纯服务端按文件/账号/区域/时刻的 CDN 调度决定。
- **坑**: 旧实现无脑 `f"https://isure.stream.qqmusic.qq.com/{purl}"`, 遇到完整-URL 形态拼出 `https://isure.../http://ws6.../F000...` 垃圾 URL → CDN 返 **HTTP 401** (拉流层, 不是 vkey 层; `命中 FLAC` 日志说明 vkey 已成功)。这是"大多数能播、个别 401"的真正主因 (实测 mid=`002rRaZH0MOSun` 花寂寥/程潇 FLAC 必现; 完整 purl 直接拉返 206)。
- **修复** (`service.py` `_try_bypass_urls`): purl `startswith("https://")` 原样用, `http://` 升 https (走 curl_cffi JA3), 否则才拼 `isure` 默认 host。回归测试见 `tests/test_service_bypass_contracts.py::test_vkey_purl_already_full_url_used_as_is`。
- **qqmusic-api 库不替你拼 URL**: 当前 git pin 版 `song.get_song_urls` 只返回 `UrlinfoItem(purl, vkey, ekey, result)` 原始片段, `get_cdn_dispatch` 单独返 `sip`, 拼接全留给调用方; 库里的 `_SONG_URL_FALLBACK_DOMAIN = "https://isure.stream.qqmusic.qq.com/"` 常量**定义了却未被引用** (死代码)。库的意图模式 `sip[i] + purl` 同样**没处理完整-URL 形态**, 照抄会踩同样的坑——我们的"按形态分支"比它更稳。`sip` 一直为空, 故暂不实现 sip 选路 (YAGNI; 若将来遇到 sip 非空 + 裸路径在 isure 上 401, 再读 `sip[0]`)。

## 六、备用通道 (多通道冗余)

### 6.1 主路径
`music.vkey.GetVkey` / `UrlGetVkey` + 极简 comm. **12/12 全通**.

### 6.2 备用通道 1: 旧版 module
`vkey.GetVkeyServer` / `CgiGetVkey` — 跟新版**完全独立**的接口. **12/12 全通**.

### 6.3 备用通道 2: 加密文件 + ekey
`music.vkey.GetEVkey` / `CgiGetEVkey` 在 ct=2 下成功返回 `purl + ekey(704 字节)`. 文件需客户端用 ekey 本地解密. 完整解密实现待补 (见第九节).

### 6.4 ct 轮换
冷门 ct 值 `[2, 5, 8, 13, 24, 30]` 都能用. 但既然不传 ct 就行, 没必要绕一层.

## 七、其它探索结论

### 7.1 匿名访问 (6 种变体测试)
- 完全空 comm → ❌ 104003
- 伪造 `qq + authst` → ❌ 104003
- 仅 cookies → ❌ 104003
- 完全无身份字段 → ❌ 104003
- 仅伪造 qq, 无 authst → ❌ 104003
- Web 风格 (uin + g_tk + ct=24) 无认证 → ❌ 104003

**绕过路径必须有有效登录态**. 任何账号都行, 包括完全免费小号. 服务端会验证 `qq + authst` 组合的真实性, 伪造无效.

### 7.2 替代取链接口探测 (13 个候选 module)
全部返回 `500003` (不存在):
- `music.musicdownload.MusicDownloadServer`
- `MusicPlay.PlayLogic.getPlayInfo`
- `music.musichallSong.PlaybackUrl`
- `intl.song.SongFile`
- 等等...

**QQ 音乐取播放链接的入口就 3 个**:
1. `music.vkey.GetVkey` / `UrlGetVkey`
2. `music.vkey.GetEVkey` / `CgiGetEVkey` (加密)
3. `vkey.GetVkeyServer` / `CgiGetVkey` (旧版)

### 7.3 endpoint
- `https://u.y.qq.com/cgi-bin/musicu.fcg` ✅
- `http://u.y.qq.com/cgi-bin/musicu.fcg` ✅
- `https://u.y.qq.com/cgi-bin/musics.fcg` ❌ (需 JCE 二进制协议)

### 7.4 MV/视频接口
`music.stream.MvUrlProxy` / `GetMvUrls`:
- modern 路径 (带 ct=11): 返回结构中 `url=[]` 全空, `code=1000/2000`
- bypass 路径 (无 ct): 与 modern 完全相同的响应, **也拿不到 URL**

**MV 用独立的版权策略**, 跟 vkey 不是一套. 当前绕过对 MV 无效. 深挖需另起项目.

## 八、为什么 0.6.1 默认失败?

`qqmusic_api/core/versioning.py:209`:
```python
DEFAULT_VERSION_POLICY.android.ct = 11
```

`Client` 默认 `platform=Platform.ANDROID`, `Client.request_api` 调 `_version_policy.build_comm` 把 `ct=11` 写进 comm, 正好命中 QQ 音乐对 Android 客户端的地区策略.

### 修复路径
- **不改库**: 用 `hybrid.py` 直接绕过 `request_api`, 自己拼 JSON payload
- **改库源码**: `versioning.py` 里把 `android.ct` 改成 `2` 等冷门值, 或重写 `build_comm` 让它不传 ct
- **未来 PR 上游**: 让 0.6.1+ 默认就走绕过路径

## 九、ekey 加密文件本地解密 (已评估为低价值)

### 9.1 现状
- API 路径已通: `music.vkey.GetEVkey` 在新加坡 IP + 无 ct 下能拿到 ekey (704 字符 base64) + 加密文件 URL
- 加密文件下载没问题 (HEAD 实测 1MB 范围下载成功)

### 9.2 解密未完成
尝试了:
- ✅ 标准 Tencent TC_TEA chain mode (已实现, 见 `qmc_crypto.py`)
- ❌ 6 种 head → 16-byte TEA key 派生方式
- ❌ 标准 RC4 (raw ekey / b64 ekey / head)
- ❌ 把全 ekey 当密文 + 公开常量 key (3DES key / qqmusic 字面 / EKey 字面)

**没有一种产生正确的 FLAC magic (`fLaC`)**. 解密涉及 QMC v2 RC4 分段 mask 算法, 包含 `0x8000` 边界 / `5120` 字节分段 / 段内 skip 等魔数, 没有权威参考实现就难以从可观测行为反推.

### 9.3 决定: 跳过
- vkey 路径全品质 (MP3_128 → MASTER 161MB) 都能拿明文文件, ekey 解密**没有现实需求**
- 当前 ekey 仅作"vkey 接口未来被堵"的冗余备份, 现在不存在该威胁
- 真要做时建议路径: 用 [unlock-music CLI](https://git.unlock-music.dev/um/cli) 子进程调用 (Go, GPL, 已处理所有 QMC 变种)
- `qmc_crypto.py` 保留作骨架, 标记为待补

## 十、生产部署建议

1. **主路径**: `music.vkey.GetVkey` + `{qq, authst}` (无 ct) + `music.stream.MvUrlProxy` 同样可试这种姿势
2. **备用**: `vkey.GetVkeyServer` 作 fallback (独立通道)
3. **限速**: < 1 req/s/账号, 避免行为风控
4. **多账号轮换**: 提高总吞吐, 降低单账号风险
5. **监控 `result` 码变化**: 一旦发现 104003 比例上升, 说明 QQ 音乐扩大了风控范围 (比如把 "无 ct" 也加上检查)
6. **不要请求 MV**: 当前绕过对 MV 无效, 强请会浪费请求次数

## 十一、风险

- **`无 ct` 不是永远稳的**: 未来 QQ 音乐可能强制要求 ct 字段并校验在白名单内
- **`qq+authst` 是真实登录态**: 单账号被识别为异常行为可能限流/封禁
- **新加坡 IP 仍可能被特殊 ASN 拦截**: 当前测试中没发生
- **`ct=46` 等孤立风控点**: 提醒 QQ 音乐随时可能扩大风控列表
- **ekey 接口可能比 vkey 更早被收紧**: 因为它给的是 SVIP 限定的母带

## 十二、本次研究产出文件清单

| 文件 | 用途 |
|------|------|
| `findings.md` | 本文档 |
| `hybrid.py` | 生产级实现, 三通道自动 fallback |
| `qmc_crypto.py` | ekey 解密骨架 (未完成, 留作未来扩展) |
| `login_test.py` / `login_test2.py` / `login_test3.py` | 早期登录 + 诊断 |
| `test_song.py` | 单首歌测试工具 |
| `legacy_url.py` | 验证 0.4.1 风格请求能跑通 |
| `ablation.py` | 消融实验 (定位关键参数) |
| `explore.py` | ct 全空间扫描 + endpoint + tmeAppID |
| `explore2.py` | 稳定性矩阵 + 加密接口探测 |
| `explore3.py` | 高 ct 扩展 + 替代 module |
| `explore4.py` | 不传 ct 稳定性最终验证 |
| `explore_quality.py` | 高音质验证 (MP3_320 → MASTER) |
| `verify_quality.py` | HEAD 实测文件大小验证 |
| `explore_anonymous.py` | 无登录态全部尝试 |
| `explore_download.py` | 替代下载接口探测 |
| `explore_mv.py` | MV 接口测试 |
| `save_sample.py` | 离线保存加密样本 (用于 ekey 算法迭代) |
| `iterate_crypto.py` / `iterate2.py` / `iterate3.py` | ekey 算法迭代实验 |
| `sample/encrypted.mflac` + `sample/meta.json` | 1MB 加密样本 + ekey, 留作后续 ekey 研究素材 |
| `credential.json` | QQ 音乐登录凭据 (敏感, 勿提交) |

## 十三、被推翻的错误结论 (避坑提醒)

**误判 1**: `uid=3931641530` 是社区流传的"魔法 UID", 绕过关键 → ❌ 完全无关, 去掉照样过.

**误判 2**: 需要写死 0.4.1 风格的全套参数 → ❌ 只要不传 ct + 带 qq/authst 即可.

**误判 3**: `Platform.DESKTOP` 应该能绕过 → ❌ 库的 DESKTOP 路径同时换了认证字段为 `uin + g_tk`, vkey 不认, 反而返回 `result=22`.

**误判 4**: `expire: 0` 表示无 VIP → ❌ 实际上是新加坡 IP 下 VIP 接口的特殊响应, 跟实际 VIP 状态无关. 真实 VIP 权限要看具体接口 `result` 码.

**误判 5**: `pay_play=0` 表示免费可播 → ❌ `pay_play=0` 在新加坡可能是"无地区版权", 也可能是"真免费". 静态字段无法区分.

**误判 6**: 静态字段 (`status` / `pay` / `file.size`) 能预判能否播放 → ❌ 唯一可靠判定是动态调用 `get_song_urls` 看 `result`.

社区流传的"魔法参数"很多是历史包袱, **当前真相只有 ct 字段 + 认证字段两件事**.

---

## 十四、ct 字段对各 endpoint 的影响矩阵 (2026-05 新增)

### 背景

在排查"排行榜详情页拿不到 intro" 时怀疑 ct=11 风控, 做了系统性矩阵测试. **结论与最初猜测相反**: toplist 模块的 intro 在 ct=11 下完全正常返回, 之前看到 intro="" 是因为踩中了某些榜本身就没有 intro (如 tid=135 巅峰潮流榜, 是个无规则文本的编辑榜) — 跟 ct 没关系.

### 实测矩阵 (ct=11 vs ct=19, safe ct ∈ 2/5/6/7/8/9/10/12/13/14/15/16/17/19/20/21/22/24/25/26/28/29/30)

| Endpoint | ct=11 (库默认) | safe ct | 结论 |
|---|---|---|---|
| `music.musicToplist.Toplist / GetAll` | **43 个榜** (含 巅峰潮流榜 编辑榜); listing 字段 intro="" | 30 个榜 (移动端缩减集, 无 135); intro 列出来非空 | **ct=11 返回更全, 列表用 ct=11** |
| `music.musicToplist.Toplist / GetDetail` | intro 完整 (tid=62 飙升榜 → 96 字) | intro 完整 (相同) | **与 ct 无关** |
| `music.vkey.GetVkey / UrlGetVkey` | 区域版权 + 收费曲库 purl="" | 正常下发完整 URL | **必须 bypass** (原结论保留) |
| `music.srfDissInfo.DissInfo / CgiGetDiss` (歌单详情) | title/desc/songlist 完整 | 完全相同 | 无关 |
| `music.musichallAlbum.AlbumInfoServer / GetAlbumDetail` | desc 2515 字完整 | 完全相同 | 无关 |
| `music.musichallAlbum.AlbumSongList / GetAlbumSongList` | songList 完整 | 完全相同 | 无关 |
| `music.search.SearchCgiService / DoSearchForQQMusicDesktop` | list 完整 | 完全相同 | 无关 |
| `music.UnifiedHomepage.UnifiedHomepageSrv / GetHomepageTabDetail` (歌手主页 tab) | code=0 正常 | code=10000 拒绝 | **反向: 必须 ct=11** |

### 关键结论

1. **歌单 / 专辑 / 专辑歌曲 / 搜索: 完全不受 ct 影响**. 用户问的"歌单内容拿不到"不会是 ct 风控. 排查方向是参数 (`disstid` 用 `id` 不是 `dirid`, ID 类型 int/str) 或 cookie/登录态.

2. **被 ct=11 风控的 endpoint 目前只有 1 类**: `music.vkey.GetVkey.UrlGetVkey` (歌曲播放 URL 区域版权过滤).

3. **toplist 列表用 ct=11 反而更全**: ct=11 (PC web profile) 返 43 榜含巅峰潮流榜等编辑榜; safe ct (移动端 profile) 仅 30 榜, 缺一批编辑榜. 不能为了"safe"切换. 详情页两边都 OK.

4. **某些榜服务端就没 intro**: tid=135 巅峰潮流榜在两种 ct 下 GetDetail 都返 intro="". 这是 QQ 数据本身就空, 不是 bug.

5. **歌手主页 tab 反向**: 仅 ct=11 工作. 又一例说明全局换 ct 是错的.

### 实现策略

- **toplist (GetAll / GetDetail)**: 直接走库的 `client.top.get_category()` / `client.top.get_detail()`, **不 bypass**.
- **vkey**: 保留 bypass (`_try_bypass_url` 走自拼 musicu.fcg + safe ct).
- **lyric**: 保留 bypass (主要是为了 `crypt=0` 拿明文歌词, 顺带用 safe ct).
- **共享 helper** `_bypass_post(module, method, param)` 留着不删 — 抽象成本低, 未来新增 ct-gated endpoint 可一行调用.

### 复现命令

```bash
# 对比 ct=11 vs ct=19 的 toplist 列表
uv run python -c "
import niquests
for ct in (11, 19):
    body = {'comm':{'ct':ct,'cv':0},
            'req_0':{'module':'music.musicToplist.Toplist','method':'GetAll','param':{}}}
    r = niquests.post('https://u.y.qq.com/cgi-bin/musicu.fcg', json=body)
    groups = r.json()['req_0']['data'].get('group', [])
    ids = [t['topId'] for g in groups for t in g.get('toplist', [])]
    print(f'ct={ct}: {len(ids)} 榜, 含 135 巅峰潮流榜={135 in ids}')
"
```

### 推论 (未验证, 留作未来研究)

- ct=11 在 toplist *list* 中返回更多榜, 可能是 PC web 看到的"更广义"列表; safe ct 是移动端缩减集.
- 是否还有 module 在 list 类接口上返回不同子集? 后续接触新功能时逐个验证.
- safe ct 数量有限 (23 个), 若全部被风控, 需要另寻替代 (sinceCV / 替代 module).
