# 调研：C4 侧栏身份区的数据来源（昵称 / 头像 / VIP 种类）

> 2026-06-11 调研完成；**2026-06-12 已实施**（见文末实施记录）。UI 形态见 [search-ui-review.md](search-ui-review.md) 的 C4 项。

## 任务描述

C4（侧栏身份区）需要登录账号的 **昵称、头像、VIP 状态**。验证 `qqmusic-api-python`（锁定 `>=0.6.1,<0.7`）能否取到这三样，尤其确认 VIP 能否区分 **绿钻 / 豪华绿钻 / 超级会员（SVIP）/ 年费** 种类，并确定接口调用路径。

## 调研结果

### 1. 昵称 + 头像：`get_homepage` 即可

```python
client.user.get_homepage(euin, credential=cred)
# → UserHomepageResponse.base_info.name    昵称
# → UserHomepageResponse.base_info.avatar  头像 URL（可直接喂 CoverCache 管道）
# 另有 big_avatar / is_singer / user_type 等
```

- `euin` 直接用 `credential.encrypt_uin`——项目 `service.py` 拉收藏专辑（`CgiGetAlbumFavInfo`）已在用同字段，路径验证过。

### 2. VIP 种类：库的类型化模型拿不到，但原始响应全有

`client.user.get_vip_info()`（`VipLogin.VipLoginInter.vip_login_base`）的类型化模型
`UserVipInfoResponse / VipUserInfo` 只建模了 `expire` / `music_level` / `score` / `buy_url`
等字段，**没有会员种类**（上游 main / v0.6.2 仍如此，pydantic 默认丢弃未建模字段）。

但用本机缓存凭据实测（`QuaverService.load_cached_credential_sync()` + `_bypass_post` 裸调），
**原始响应携带完整身份块**：

| 字段 | 含义 |
| --- | --- |
| `identity.vip` | 绿钻在期（0/1） |
| `identity.HugeVip` + `HugeVipStart/End` | **豪华绿钻** + 起止时间（字符串 `"YYYY-MM-DD HH:MM:SS"`） |
| `svip`（顶层） | **超级会员 SVIP**（0/1） |
| `identity.yearflag` / `HugeYearFlag` | 年费 / 豪华年费标志 |
| `identity.twelve`（+start/end） | 十二平台会员 |
| `identity.ChildVip` / `ExpVip` / `GroupVipFlag` / `CPLoverFlag` / `AdVipFlag` | 儿童 / 体验 / 家庭组 / 情侣 / 广告会员等 |
| `identity.icon` | **官方等级徽章图 URL**（如 `…/mediastyle/global/vip_icon/lv_7.png`，服务端按等级出图） |
| `identity.purchaseUrl` | 开通入口 |
| `star` / `ystar`（顶层，各带 start/end） | 星级 / 年费星级会员 |
| `userinfo.expire` / `userinfo.music_level` | 到期时间戳 / 音乐等级（类型化模型也有） |

`identity.icon` 是意外收获：侧栏徽章可以直接渲染 QQ 官方徽章资产，不用手绘。

### 3. 上游 issue 已提（→ 已被采纳）

- **https://github.com/L-1124/QQMusicApi/issues/257** —— 按上游 feature 模板提交：脱敏响应形状 + 建议的 `VipIdentity(Response)` 子模型代码（可直接抄）+ `extra="allow"` 零成本替代方案。提交前已确认上游 main 未建模、无重复 issue。
- **2026-06-12 上游已实现**（PR #258，commit `650437317290c4905bc81fefed169a9e725f7c29`）：新增 `VipIdentity` 子模型（绿钻/豪华绿钻/年费/家庭组等标志 + 起止时间 + 官方徽章 icon）+ `UserVipInfoResponse` 顶层补 `svip` / `star` / `ystar` / `identity`，全字段默认值容错。该提交在 v0.6.2 **之后**、尚未发版。

## 预期结果（C4 实施时的数据面方案）

1. `service.get_user_profile()`：并发两个请求——
   - `_bypass_post("VipLogin.VipLoginInter", "vip_login_base", {}, require_login=True)` 解析 `vip / HugeVip / svip / yearflag / expire / icon`；
   - `get_homepage(cred.encrypt_uin)` 拿 `Name / Avatar`。
   解析逻辑做成纯函数，TDD 用本次录到的原始 dict 形状当 fixture（与 `_parse_fav_albums` 同款"绕过库模型 + 手动容错解析"套路，先例见 `service.py` 收藏专辑）。
2. `AppController` 暴露 `nickname` / `avatarUrl` / `vipKind`（或 `vipIconUrl`），登录 / 登出 / 凭据过期时刷新。
3. 徽章展示优先级：**SVIP > 豪华绿钻 > 绿钻 > 无**（非会员不显示负面标签）；优先用服务端 `icon` 图，拉不到回退文字徽章。
4. **风险与降级**：`_bypass_post` 走未公开原始接口，字段名可能随服务端变——解析函数对缺字段一律默认 `0` / 空串，徽章静默缺席、昵称回退"已登录"、头像回退占位首字，不挡登录主流程。上游 issue 被采纳发版后，解析切回官方模型并解除版本锁内的裸调。

## 实施记录（2026-06-12）

上游在实施前已合入 VipIdentity 建模（见上"已被采纳"），故**跳过 `_bypass_post` 裸调阶段，直接走官方类型化模型**；其余按预期方案落地：

1. **依赖**：`pyproject.toml` 把 `qqmusic-api-python` 临时 git pin 到上游 commit `6504373`（PyPI 包 repository 即 `github.com/l-1124/QQMusicApi`，`luren-dc` 为同仓库旧名重定向）；hatchling 需 `[tool.hatch.metadata] allow-direct-references = true` 放行 direct reference。**上游发布含该提交的版本后切回 PyPI 版本锁并移除这两处**。
2. **service 层**（`core/service.py` + `core/models.py`）：`UserProfile` dataclass；`get_user_profile()` 用 `asyncio.gather(return_exceptions=True)` 并发 `user.get_homepage` + `user.get_vip_info`，单失败不挡另一半、双失败返 None、凭据过期抛 `CredentialExpiredError`；`_parse_user_profile` 纯函数按优先级映射 `vip_kind`，非会员抑制 icon。契约测试含"原始响应形状 → 上游 pydantic 模型 → 我们的解析"全链路（防上游 alias 漂移）。
3. **桥接层**：`ServiceController.get_user_profile()` 走 `call_service` 统一过期处理；`AppController` 暴露 `nickname / avatarUrl / vipKind / vipIconUrl` + `profileChanged`，`_set_authed` 变 true 时 fire-and-forget 刷新、变 false 同步清空 + 取消在途任务 + 丢弃迟到结果。
4. **UI**（`Sidebar.qml` 顶部 `IdentityArea`）：头像（`AlbumArt circular` 复用封面缓存管道，回退昵称首字）+ 昵称（回退"已登录"）+ VIP 徽章（官方 icon 图优先，`Image.status !== Ready` 回退文字 pill：SVIP/豪华绿钻金色 `vipGold` token、绿钻 `primaryFg`）；未登录显示人形占位（新增 `icons/user.svg`）+ "点击登录"即登录入口（原"登录同步"按钮移除）；已登录点击进资料库；紧凑态只显头像。
5. **测试**：+28（service 解析/并发容错 15、AppController 身份生命周期 6、ServiceController 包装 2、Sidebar 离屏契约 5），720 全绿 + lint 全绿。
