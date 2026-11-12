[English](README.md) · **简体中文**

# friday-brain

一套给多个私人 Claude 助理共用、用 git 管理版本的「大脑」，你在 Telegram 上和它们对话。

每个 agent（Friday、Study、Feed、Dev、Trader）都是一个在**自己目录里**运行的 Claude Code 会话，
有自己的角色、权限和记忆；所有 agent 还共用一套规则和一份关于你的事实。记忆就是 git 里的
Markdown 文件，所以你可以直接阅读、对比、修改和回滚。

```
global/            所有 agent 都遵守的规则（CLAUDE.md）+ 关于你的事实（memory/）
agents/<name>/     一个 agent：CLAUDE.md（角色）+ .claude/settings.json（权限）
                   + memory/（一事一文件，MEMORY.md 是索引）+ journal/
shared/            跨 agent 的项目和参考笔记（对 agent 只读）
inbox/             消息的指针（来源 + id + 时间），从不存原文
feedback/          /fb 队列：对系统本身的意见，和记忆分开存
relay/             最小的 Telegram <-> Claude Code 中继（只用标准库）+ 测试
hooks/pre-commit   拒绝新增密钥或你的私人字符串的提交
scripts/           setup-local.sh、install-hooks.sh
```

## 快速开始

需要：Python 3.10+、git，以及已安装并登录的 [Claude Code](https://docs.claude.com/en/docs/claude-code)
（运行 `claude`，再执行 `/login`）。

```sh
git clone <你的 fork> friday-brain && cd friday-brain
sh scripts/setup-local.sh        # 安装钩子，生成 .env、config.json、.private-patterns 和每个 agent 的本地设置
```

1. 用 [@BotFather](https://t.me/BotFather) 给每个 agent 建一个 bot，把各自的 token 填进 `.env`。
   不需要的 agent 从 `config.json` 里删掉。
2. 启动中继，给任意一个 bot 发 `/whoami`，把返回的数字填进 `config.json` 的 `owner_id`。
   在此之前中继拒绝启动；之后它只理你一个人。
3. 填写 `global/memory/user-profile.md`，并在 `.private-patterns` 里列出绝对不能提交的字符串
   （地址、电话、各种 ID）。
4. `python3 relay/relay.py`

任何一个 bot 里都能用的命令：`/new`（开新会话）、`/fb <内容>`（反馈系统问题）、`/whoami`。

**你自己的 fork 请保持私有。** 这个模板可以公开；一旦开始用，`memory/` 和 `journal/` 就会装满
你的生活。git 历史会保留所有提交过的内容，事后删除文件并不能让它「撤回公开」。

## 设计说明

**为什么每个 agent 一个目录。** Claude Code 会读取它所在目录下的 `CLAUDE.md` 和 `.claude/settings.json`。
让每个 agent 在自己的工作目录里运行，它就自然拥有独立的角色和独立的权限边界：Study 和 Dev 完全没有
shell，Trader 只能运行四个脚本，任何 agent 都不能写 `global/` 或 `shared/`。权限由运行环境强制执行，
而不是靠礼貌地请模型遵守。

**记忆是一事一文件，加一个索引。** agent 先读 `MEMORY.md` 这份短清单，只在相关时才打开单个文件。
这样上下文保持很小，每条事实都可以单独修改、单独删除。`feedback` 类记忆必须写明 *Why*（为什么）和
*How to apply*（怎么用），后来的会话才能判断这条规则什么时候已经不适用，而不是永远照做。

**两类东西，两个地方。** 关于你的事实进记忆。对系统的抱怨（「邮件摘要总在重复旧邮件」）通过 `/fb`
进 `feedback/queue.jsonl`。混在一起的话，agent 会把自己的 bug 当成你的偏好来谈。

**默认不可信。** 每条消息都会被包在 `<untrusted_message>` 里交给 agent（中继会把正文里出现的闭合标签
转义掉），全局规则也写明了邮件、网页、转发的内容都是数据。这是防提示词注入的纵深防御，不是保证；
真正的硬边界仍然是 `.claude/settings.json` 允许什么。

**inbox 只存指针，不存原文。** 万一仓库泄露，inbox 只暴露「有过这条消息」，不暴露消息说了什么。

**什么都接，但只记自己这一摊。** agent 之间不能互相转发消息，所以拒答跑题的问题只会浪费你的时间。
分工只决定两件事：agent 主动推送什么，以及它往记忆里写什么。

## 中继是故意做得很小的

`relay/relay.py` 不到 300 行：长轮询、只认主人、每个 agent 的会话续接、inbox 指针、`/fb`。
它不处理语音、图片、定时简报、邮件或日历，也不做 agent 之间的路由，这些留给你自己的 fork。
每条消息会在对应 agent 的目录里运行一轮 `claude -p ... --resume <session>`，所以回复速度就是
一轮 Claude Code 的速度（几秒到几分钟）。

计费：中继用的是 `claude` 当前登录的身份。用订阅登录，消耗的是订阅额度；如果环境里有
`ANTHROPIC_API_KEY`，则按 token 计费。

测试：`python3 -m pytest relay`（离线；不联网，不调用真实的 Claude）。

## 文档语言

本 README 有英文和中文两个版本。agent 的提示词（`CLAUDE.md`）和示例记忆只有英文：它们是写给模型的，
而 agent 会用你说话的语言回复你。

## License

MIT，见 [LICENSE](LICENSE)。
