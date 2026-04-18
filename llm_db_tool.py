import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pymysql
from pymysql.cursors import DictCursor


@dataclass
class DBConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = "YOUR_PASSWORD"
    database: str = "demo"
    charset: str = "utf8mb4"

    @classmethod
    def from_env(cls) -> "DBConfig":
        """
        从环境变量读取 MySQL 连接配置:
        DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_CHARSET
        """
        return cls(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "flk050430"),
            database=os.getenv("DB_NAME", "demo"),
            charset=os.getenv("DB_CHARSET", "utf8mb4"),
        )


class DatabaseTool:
    """
    一个可被 LLM 调用的数据库工具，支持 CRUD。
    基于 MySQL（PyMySQL）实现。
    """

    def __init__(self, config: Optional[DBConfig] = None) -> None:
        self.config = config or DBConfig.from_env()

    @contextmanager
    def _conn(self):
        conn = pymysql.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset=self.config.charset,
            cursorclass=DictCursor,
            autocommit=False,
        )
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _build_where_clause(where: Optional[Dict[str, Any]]) -> Tuple[str, List[Any]]:
        if not where:
            return "", []
        clauses = []
        values: List[Any] = []
        for key, value in where.items():
            clauses.append(f"{key} = %s")
            values.append(value)
        return " WHERE " + " AND ".join(clauses), values

    def create_table(self, table: str, schema: Dict[str, str]) -> Dict[str, Any]:
        """
        schema 示例:
        {
            "id": "INT PRIMARY KEY AUTO_INCREMENT",
            "name": "VARCHAR(100) NOT NULL",
            "age": "INT"
        }
        """
        if not schema:
            raise ValueError("schema 不能为空")
        columns_sql = ", ".join([f"{col} {typ}" for col, typ in schema.items()])
        sql = f"CREATE TABLE IF NOT EXISTS {table} ({columns_sql})"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        return {"ok": True, "message": f"表 {table} 创建或已存在"}

    def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            raise ValueError("insert 的 data 不能为空")
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, list(data.values()))
                return {"ok": True, "last_row_id": cur.lastrowid, "rowcount": cur.rowcount}

    def select(
        self,
        table: str,
        columns: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        select_cols = ", ".join(columns) if columns else "*"
        where_sql, where_vals = self._build_where_clause(where)
        sql = f"SELECT {select_cols} FROM {table}{where_sql}"
        params: List[Any] = list(where_vals)
        if isinstance(limit, int) and limit >= 0:
            sql += " LIMIT %s"
            params.append(limit)
        if isinstance(offset, int) and offset >= 0:
            sql += " OFFSET %s"
            params.append(offset)

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                return {"ok": True, "rows": rows, "count": len(rows)}

    def update(self, table: str, data: Dict[str, Any], where: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            raise ValueError("update 的 data 不能为空")
        if not where:
            raise ValueError("update 必须提供 where，防止全表更新")

        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        where_sql, where_vals = self._build_where_clause(where)
        sql = f"UPDATE {table} SET {set_clause}{where_sql}"
        params = list(data.values()) + where_vals

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return {"ok": True, "rowcount": cur.rowcount}

    def delete(self, table: str, where: Dict[str, Any]) -> Dict[str, Any]:
        if not where:
            raise ValueError("delete 必须提供 where，防止全表删除")
        where_sql, where_vals = self._build_where_clause(where)
        sql = f"DELETE FROM {table}{where_sql}"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, where_vals)
                return {"ok": True, "rowcount": cur.rowcount}

    def run_tool(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        给 LLM 的统一入口。payload 示例:
        {
          "action": "select",
          "table": "users",
          "columns": ["id", "name"],
          "where": {"age": 20},
          "limit": 10
        }
        """
        action = payload.get("action")
        table = payload.get("table")
        if not action or not table:
            raise ValueError("payload 必须包含 action 和 table")

        if action == "create_table":
            return self.create_table(table, payload.get("schema", {}))
        if action == "insert":
            return self.insert(table, payload.get("data", {}))
        if action == "select":
            return self.select(
                table=table,
                columns=payload.get("columns"),
                where=payload.get("where"),
                limit=payload.get("limit"),
                offset=payload.get("offset"),
            )
        if action == "update":
            return self.update(table, payload.get("data", {}), payload.get("where", {}))
        if action == "delete":
            return self.delete(table, payload.get("where", {}))

        raise ValueError(f"不支持的 action: {action}")

    def ping(self) -> Dict[str, Any]:
        """测试数据库连通性。"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                row = cur.fetchone()
        return {"ok": True, "result": row}


TOOL_SCHEMA = {
    "name": "database_crud_tool",
    "description": "对 MySQL 数据库执行增删改查操作",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create_table", "insert", "select", "update", "delete"],
            },
            "table": {"type": "string"},
            "schema": {"type": "object"},
            "data": {"type": "object"},
            "columns": {"type": "array", "items": {"type": "string"}},
            "where": {"type": "object"},
            "limit": {"type": "integer"},
            "offset": {"type": "integer"},
        },
        "required": ["action", "table"],
    },
}


def demo() -> None:
    tool = DatabaseTool(DBConfig.from_env())

    print("== 连通性检查 ==")
    print(tool.ping())

    print("== 建表 ==")
    print(
        tool.run_tool(
            {
                "action": "create_table",
                "table": "users",
                "schema": {
                    "id": "INT PRIMARY KEY AUTO_INCREMENT",
                    "name": "VARCHAR(100) NOT NULL",
                    "age": "INT",
                },
            }
        )
    )

    print("== 插入 ==")
    print(tool.run_tool({"action": "insert", "table": "users", "data": {"name": "Alice", "age": 22}}))
    print(tool.run_tool({"action": "insert", "table": "users", "data": {"name": "Bob", "age": 25}}))

    print("== 查询 ==")
    print(tool.run_tool({"action": "select", "table": "users"}))

    print("== 更新 ==")
    print(tool.run_tool({"action": "update", "table": "users", "data": {"age": 23}, "where": {"name": "Alice"}}))

    print("== 删除 ==")
    print(tool.run_tool({"action": "delete", "table": "users", "where": {"name": "Bob"}}))

    print("== 最终查询 ==")
    print(tool.run_tool({"action": "select", "table": "users"}))

    print("== Tool Schema ==")
    print(json.dumps(TOOL_SCHEMA, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    demo()
