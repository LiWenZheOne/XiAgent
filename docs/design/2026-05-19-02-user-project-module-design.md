# 用户与项目模块设计

## 模块定位

用户与项目模块负责身份、项目归属和基础访问校验。第一版实现简单账号系统，不做完整团队协作和 RBAC。

## 第一版能力

- 用户注册。
- 用户登录。
- 获取当前用户。
- 创建项目。
- 查询用户可访问项目。
- 查询项目详情。
- 检查用户对项目的基础访问权限。

## 核心实体

### User

```text
user_id
username
password_hash
status
created_at
updated_at
```

`status` 第一版支持：

```text
active
disabled
```

### Project

```text
project_id
owner_user_id
name
description
status
created_at
updated_at
```

`status` 第一版支持：

```text
active
archived
```

## 对外接口

```python
class UserService(ABC):
    async def create_user(self, *, username: str, password: str) -> UserRecord:
        ...

    async def authenticate(self, *, username: str, password: str) -> AuthResult:
        ...

    async def get_user(self, *, user_id: str) -> UserRecord:
        ...

    async def create_project(
        self,
        *,
        owner_user_id: str,
        name: str,
        description: str | None = None,
    ) -> ProjectRecord:
        ...

    async def get_project(
        self,
        *,
        user_id: str,
        project_id: str,
    ) -> ProjectRecord:
        ...

    async def list_projects_for_user(self, *, user_id: str) -> list[ProjectRecord]:
        ...

    async def ensure_project_access(
        self,
        *,
        user_id: str,
        project_id: str,
        action: str,
    ) -> None:
        ...
```

## 权限规则

第一版规则：

- 用户只能访问自己创建的项目。
- 系统内置全局项目 `project_id=global` 是例外，所有 active 用户都可以访问，但全局项目下的任务仍按 `user_id` 隔离。
- 创建任务必须拥有项目访问权限。
- 创建项目资产、项目目录、项目标签必须拥有项目访问权限。
- 使用项目工作流模板必须拥有项目访问权限。

接口中保留 `action` 参数，未来可以在模块内部扩展为角色、团队、项目成员权限，不影响调用方。

## 跨模块关系

任务必须保存：

```text
user_id
project_id
```

项目资产、项目检索结构、项目工作流模板必须保存：

```text
project_id
```

其他模块校验项目权限时只调用 `UserService.ensure_project_access()`。
