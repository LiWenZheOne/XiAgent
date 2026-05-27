# XiAgent 文档索引

XiAgent 文档按项目架构、设计文档、开发文档三个层级维护。

## 项目架构

- [XiAgent 架构总览](project-architecture/2026-05-19-01-xiagent-architecture-overview.md)

## 设计文档

- [总体平台设计](design/2026-05-19-01-overall-platform-design.md)
- [用户与项目模块设计](design/2026-05-19-02-user-project-module-design.md)
- [资产模块设计](design/2026-05-19-03-asset-module-design.md)
- [工作流模板与契约设计](design/2026-05-19-04-workflow-contract-design.md)
- [节点、任务运行与恢复设计](design/2026-05-19-05-node-runtime-task-design.md)
- [前端对接 API 设计](design/2026-05-19-06-api-integration-design.md)
- [模型路由模块设计](design/2026-05-19-07-model-router-module-design.md)
- [UI 任务交互与控件库设计](design/2026-05-26-01-ui-task-interaction-design.md)
- [资产库、对象存储与工作流文件选择器设计](design/2026-05-26-02-asset-library-object-storage-design.md)
- [UI 控件 Manifest 与后端对接规则设计](design/2026-05-27-01-ui-control-manifest-design.md)

## 开发文档

- [开发约束与实现准则](development/2026-05-19-01-development-guidelines.md)
- [后端 MVP 实现计划](development/2026-05-19-02-backend-mvp-implementation-plan.md)
- [UI 任务交互实现计划](development/2026-05-26-01-ui-task-interaction-implementation-plan.md)
- [资产库与对象存储实施计划](development/2026-05-26-02-asset-library-object-storage-implementation-plan.md)
- [依赖库与部署指南](development/2026-05-21-01-dependency-and-deployment-guidelines.md)

## 命名规则

文档文件名使用：

```text
YYYY-MM-DD-NN-topic-document-kind.md
```

规则：

- `YYYY-MM-DD` 表示文档创建日期。
- `NN` 是两位序号，用于同一天多文档排序。
- `topic` 使用英文短语，便于跨系统路径兼容。
- `document-kind` 表示文档类型，例如 `overview`、`design`、`guidelines`、`plan`。
