import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from llm_db_tool import DBConfig, DatabaseTool, TOOL_SCHEMA


DEFAULT_SYSTEM_PROMPT = (
    "你是一名专业的数据库专家，可以根据用户需求进行数据库相关操作，例如增删改查等"
)


@dataclass
class LLMAPIConfig:
    """LLM API 连接配置（OpenAI 兼容接口）。"""

    api_key: str
    model: str = "gpt-4o-mini"
    base_url: Optional[str] = None
    max_tool_rounds: int = 8

    @classmethod
    def from_env(cls) -> "LLMAPIConfig":
        api_key = os.getenv("LLM_API_KEY")
        if not api_key:
            raise ValueError("缺少 API Key，请设置 LLM_API_KEY 或 OPENAI_API_KEY")
        return cls(
            api_key=api_key,
            model=os.getenv("LLM_MODEL", ""),
            base_url=os.getenv("https://api.deepseek.com"),
            max_tool_rounds=int(os.getenv("LLM_MAX_TOOL_ROUNDS", "8")),
        )


@dataclass
class ToolBinding:
    """描述一个可被 LLM 调用的工具绑定。"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    executor: Callable[[Dict[str, Any]], Dict[str, Any]]


class LLMModule:
    """
    LLM 模块：
    1) 支持 system_prompt 自定义（含默认值）
    2) 默认接入 llm_db_tool.py 中的数据库工具
    """

    def __init__(
        self,
        system_prompt: Optional[str] = None,
        db_config: Optional[DBConfig] = None,
        db_tool: Optional[DatabaseTool] = None,
        llm_config: Optional[LLMAPIConfig] = None,
    ) -> None:
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._db_tool = db_tool or DatabaseTool(db_config or DBConfig.from_env())
        self.llm_config = llm_config
        self._client = None
        self._tools: Dict[str, ToolBinding] = {}
        self._register_default_db_tool()

    def _register_default_db_tool(self) -> None:
        self.register_tool(
            name=TOOL_SCHEMA["name"],
            description=TOOL_SCHEMA["description"],
            input_schema=TOOL_SCHEMA["input_schema"],
            executor=self._db_tool.run_tool,
        )

    def set_system_prompt(self, prompt: str) -> None:
        """更新 system_prompt。"""
        if not prompt or not prompt.strip():
            raise ValueError("system_prompt 不能为空")
        self.system_prompt = prompt.strip()

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        executor: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """注册一个可供 LLM 调用的工具。"""
        if not name:
            raise ValueError("tool name 不能为空")
        self._tools[name] = ToolBinding(
            name=name,
            description=description,
            input_schema=input_schema,
            executor=executor,
        )

    def get_system_prompt(self) -> str:
        return self.system_prompt

    def get_tools_spec(self) -> Dict[str, Dict[str, Any]]:
        """
        返回工具规范，可直接用于多数 function-calling 接口。
        """
        return {
            name: {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for name, tool in self._tools.items()
        }

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        工具连接接口：按 tool_name 调用已注册工具。
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError(f"未注册的工具: {tool_name}")
        if not isinstance(arguments, dict):
            raise ValueError("arguments 必须是 dict")
        return tool.executor(arguments)

    def build_messages(self, user_message: str) -> list[Dict[str, str]]:
        """
        生成标准消息结构，可直接传给聊天模型。
        """
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

    def _to_openai_tools(self) -> List[Dict[str, Any]]:
        """转换为 OpenAI 兼容 tools 格式。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self._tools.values()
        ]

    def set_llm_config(self, llm_config: LLMAPIConfig) -> None:
        """设置 LLM API 配置并重建客户端。"""
        self.llm_config = llm_config
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if self.llm_config is None:
            self.llm_config = LLMAPIConfig.from_env()

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("请先安装 openai：pip install openai") from exc

        kwargs: Dict[str, Any] = {"api_key": self.llm_config.api_key}
        if self.llm_config.base_url:
            kwargs["base_url"] = self.llm_config.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    @staticmethod
    def _parse_tool_arguments(raw_args: Any) -> Dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            text = raw_args.strip()
            if not text:
                return {}
            return json.loads(text)
        raise ValueError("tool arguments 格式错误，必须是 dict 或 JSON 字符串")

    @staticmethod
    def _extract_text_from_message(message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "\n".join(p for p in parts if p)
        return str(content)

    def chat(self, user_message: str) -> str:
        """
        用户自然语言入口：
        - 模型可自动决定是否调用数据库 tool
        - 支持多轮 tool 调用后给出最终回复
        """
        client = self._ensure_client()
        if not self.llm_config:
            raise ValueError("llm_config 未初始化")

        messages: List[Dict[str, Any]] = self.build_messages(user_message)
        tools = self._to_openai_tools()

        for _ in range(self.llm_config.max_tool_rounds):
            resp = client.chat.completions.create(
                model=self.llm_config.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []

            if not tool_calls:
                return self._extract_text_from_message(msg)

            messages.append(
                {
                    "role": "assistant",
                    "content": self._extract_text_from_message(msg),
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = self._parse_tool_arguments(tool_call.function.arguments)
                    result = self.call_tool(tool_name, arguments)
                    tool_content = json.dumps(result, ensure_ascii=False)
                except Exception as exc:
                    tool_content = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_content,
                    }
                )

        raise RuntimeError("模型工具调用轮次超限，请检查提示词或工具参数")


def demo() -> None:
    module = LLMModule(llm_config=LLMAPIConfig.from_env())
    print("system_prompt:", module.get_system_prompt())
    print("tools:", module.get_tools_spec())
    print("reply:", module.chat("查询 users 表最近 5 条数据"))


if __name__ == "__main__":
    demo()
