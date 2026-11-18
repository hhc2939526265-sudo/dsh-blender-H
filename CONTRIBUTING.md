# 贡献指南

感谢你参与 DSH Blender Bridge 项目！

## 开发流程

1. Fork 仓库并新建分支：`feat/xxx` / `fix/xxx` / `docs/xxx`。
2. 本地运行单元测试：`python3 -m unittest discover -s tests -v`。
3. Blender 端代码须在 4.2 与 5.3 两类版本上确认无报错；版本差异一律走 `compat/` 层。
4. 提交前执行 `bash scripts/package_all.sh` 确认打包结构正确。

## 代码规范

- 所有函数 / 类 / 核心逻辑补充中文注释；
- 配置项统一收敛到 `config/default_config.py`，禁止业务代码硬编码魔法数字；
- 处理器异常必须收敛为 FAILED 回执，不得抛到网络线程；
- 仅使用 Blender 内置库与 Python 标准库；
- 新增指令需同步更新 `docs/API.md` 指令清单。

## 提交信息

遵循 Conventional Commits：

```
feat(handlers): 新增晶格形变指令
fix(ws): 修复分片续传索引丢失
docs(api): 补充材质指令参数说明
```

## 发布

- 版本号遵循 Semantic Versioning；
- Release 提供三个下载项：DSH 插件包、Blender Addon 包、完整源码包；
- 变更记录写入 `CHANGELOG.md`。
