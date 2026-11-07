# 野蛮人大作战 · 自定义 BUFF 调研报告

时间：2026-11-06
工作目录：`G:\My\野蛮人大作战`
游戏目录：`C:\Program Files\4399野蛮人大作战`

---

## 一、结论（先说结果）

**可行。** 这个游戏的 BUFF/技能系统是**纯客户端逻辑**，配置表就在本地资源包里，
技能 ID、名称、等级、权重参数都能静态抓出来；运行时角色对象也能直接读写。

三条可行路线，按稳定性排序：

| 路线 | 做法 | 适用场景 | 难度 |
|---|---|---|---|
| A. 运行时改写候选列表 | 找到升级时那 3 张卡片的 ID 数组，直接改成想要的 ID | 人机 / PVE / 大部分联机 | 低 |
| B. Hook 随机技能生成函数 | 改 `CSkillRandom::GetCanSelectSkills`，让面板直接显示自定义 BUFF | 同上，体验最好 | 中 |
| C. 伪造"添加技能"协议包 | 改 `COperateMessage.AddSkill` 里的 skillid | 联机（需服务端不校验） | 中高 |

A 路线最快出效果，B 路线做成品工具最稳，C 路线只在 A/B 被服务端拦截时才需要。

---

## 二、已经拿到的东西（实证）

### 1. 逆向证据

- 游戏引擎：Cocos2d-x + 自研框架（`libcocos2d.dll` / `GameLogic.dll` / `msc.dll`）
- 战斗与 BUFF 逻辑在 **`GameLogic.dll`**，带完整 C++ 符号信息：
  - `Character\Buff.cpp`、`Character\SkillRandom.cpp`、`Character\Skill.cpp`
  - 类：`CSkillRandom`、`CBuffFunction`、`BuffConfig`、`HighFrequencyBuffConfig`、`InsideBuffConfig`
  - 关键函数：`CSkillRandom::GetCanSelectSkills`、`GetSkillPlans`、`GetCurSelectLevel`、`GetSelectedSkills`
- 配置系统：`config.dll` 里 `xconf::tms::DataLine` 逐表解析，表名如
  `config.skill.HeroSkillConfig`、`config.hero.EntityRandomSkillPlans`
- 网络协议（protobuf，`protocol.dll`）：
  - 服务端下发：`_RandomSkill { randomskillid, curlevel, canselectedskillid[], selectedskillid[], eventcount }`
  - 客户端上行：`COperateMessage.AddSkill { skillid, number }`
  - 广播：`SFrameUpdate.AddSkill`
- 反作弊：游戏目录内**没有** ACE / SGuard 等模块；进程 Wilds.exe 已加载模块里也没有反作弊 DLL。
  （系统里装了 AntiCheatExpert，但未注入本游戏。）

### 2. 配置表已解包

资源包 `packages\final\pc\asset.vfs` 是 `VISPACK` 私有格式，内部条目为 zlib 流。
已批量解压出 **90 张配置表**（`work\tables\`），其中：

- `tbl_05c2a9d4.txt` = **HeroSkillConfig（技能/BUFF 总表，108 条）**
- 5 张 1.9MB 的是多语言文本表（中/英/德/西/葡）

### 3. 技能 ID 已抓出

导出文件：`work\buff_catalog.csv`（ID / 名称 / 分类 / 等级 / 权重参数）

**截图里那三张卡，ID 已经对上了：**

| 卡片 | 技能 ID | 表内名称 |
|---|---|---|
| 磁铁2级 | `110131` | 宝藏lv2（权重名 `V_I_Weight_Magne`，即磁铁） |
| 双重撞击 | `70131` | 滑步（权重名 `V_I_Weight_DoubleCharge`） |
| 命中吸血1级 | `210131` | 吸血lv1 |

其他常用 BUFF ID 举例（完整见 CSV）：

- 吸血：`210131` / `220131` / `230131`（1~3 级），`390131`/`400131`（4~5 级）
- 磁铁：`100131` / `110131` / `120131`（1~3 级），`370131`/`380131`（4~5 级）
- 吸体：`240131`/`250131`/`260131`
- 闪电球：`180131`/`190131`/`200131`
- 地刺：`270131`/`280131`/`290131`
- 命中二暴：`150131`/`160131`/`170131`
- 命中加速：`140131`；体力上限：`130131`
- 主动技能：旋风斩 `10131`、冲击波 `20131`、勾手 `30131`、滑步 `70131` ……

### 4. 运行时对象已验证

用你现有 CT 的指针链读到了当前角色对象（游戏正在运行，PID 33128）：

```
libcocos2d.dll+AAAEEC → +B4 → +2B8 → +2B4 → +2E4  = 角色对象
角色对象+0x258 血量=50   +0x254 血量上限=286
        +0x25C 体力=10500 +0x260 体力上限=10500
        +0x26C 移速=150   +0x274 近攻距离=79  +0x278 拾取范围=60
```

说明现有的内存读写通道是通的，后续找 BUFF 数组可以复用同一套工具。

---

## 三、还没验证的关键点（必须实测）

1. **升级面板那 3 个候选 ID 存在哪**：怀疑在 `CSkillRandom` 对象的 `m_vCanSelectSkills`
   （vector<SSkillPlanConfig>）里，但需要在"面板正显示"的瞬间扫描确认。
2. **服务端是否校验你选的 ID**：
   - 若 `COperateMessage.AddSkill` 的 skillid 由客户端决定且服务端只做转发 → 联机也能自定义。
   - 若服务端只会下发/校验 `canselectedskillid[]` → 联机只能三选一，自定义仅限人机/PVE。
   这一条决定最终工具是"全模式"还是"人机专用"。

---

## 四、下一步（需要你配合）

1. 开一局**人机或 PVE**，升到 2 级让三张卡出现，**保持界面不要点**，告诉我"卡出来了"。
2. 我用已写好的扫描器（`tools\memscan.py`）扫这三个 ID，定位数组地址。
3. 把其中一张改成 `230131`（吸血3级）或 `380131`（磁铁5级），点它，看是否生效。
4. 人机验证通过后，再到联机局重复一次（先用低风险 BUFF 测），确认服务端态度。

工具已经就绪，只差这一局实测。

---

## 五、工期预估（确认方向后）

| 阶段 | 内容 | 工作日 |
|---|---|---|
| 实测定位 | 找数组 / 验证服务端 | 0.5~1 天 |
| CE 原型 | CT 表：锁定 3 个槽位、预设 BUFF 下拉 | 1 天 |
| 易语言成品 | 界面选 BUFF、写入、热键、配置保存 | 2~3 天 |
| 联机适配（若可行） | 协议层伪造 / 兼容处理 | 1~2 天 |
| 测试与文档 | 多模式回归、交接文档 | 1 天 |

合计：**CE 原型 1~2 天；易语言成品 4~7 个工作日**（联机部分若不通过则省 1~2 天）。

---

## 六、文件清单

```
G:\My\野蛮人大作战\
├─ tools\
│  ├─ pe_xref.py          PE 字符串交叉引用（定位函数）
│  ├─ extract_tables.py   asset.vfs 配置表批量解压
│  ├─ memscan.py          进程内存扫描（按 4 字节值）
│  └─ memdump.py          指定地址内存转储
├─ work\
│  ├─ tables\             90 张解压出的配置表 + _manifest.json
│  └─ buff_catalog.csv    108 条技能/BUFF 目录
└─ 调研报告-自定义buff.md  本文件
```

---

## 七、追加：调试弹窗（Error / PreOperation）已定位并屏蔽

对局中改数据后周期性弹出的 "Error" 对话框（内容为 `PreOperation: ... / Carry Skill: ... / Random Skill index: ...`），
来源已确认：

- 位置：`GameLogic.dll` 函数 `0x1004CCC0`（`Character\SkillRandom.cpp`）
- 触发条件：3 个技能槽里有任意一个查不到配置（返回 0）时，拼出这段状态并调用
  `MessageBoxA(0, text, "Error", MB_YESNO|MB_ICONINFORMATION)`
- 该对话框是模态的，会卡住主线程 → 表现为"游戏暂停"；连弹 3 次是因为对应 3 个槽位/角色各检查一次
- **不是服务端下发，也不是反作弊**，是客户端自带的调试输出

处理方式：运行时把 `GameLogic.dll+0x4D02A` 的 `call [MessageBoxA]`（6 字节）改成
`add esp,0x10; nop×3`，弹窗不再出现，逻辑继续执行。

工具：`tools\patch_popup.py`（`--restore` 可还原；只改内存，重启游戏即恢复原状）。

推论：以后写 BUFF 只用配置表里合法的 108 个 ID，就不会触发这个检查；补丁作为双保险。
