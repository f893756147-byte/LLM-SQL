from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from llm_db_tool import DBConfig
from llm_module import LLMAPIConfig, LLMModule


st.set_page_config(page_title="LLM-SQL", page_icon="💬", layout="centered")

CONFIG_PATH = Path(__file__).with_name("llm_sql_config.json")
DEFAULT_PROMPT = "你是一名专业的数据库专家，可以根据用户需求进行数据库相关操作，例如增删改查等"


def default_config() -> dict:
    return {
        "mysql_host": "127.0.0.1",
        "mysql_port": 3306,
        "mysql_user": "root",
        "mysql_password": "",
        "mysql_database": "demo",
        "llm_api_key": "",
        "llm_model": "gpt-4o-mini",
        "llm_base_url": "",
        "system_prompt": DEFAULT_PROMPT,
        "remember_config": True,
        "save_sensitive": False,
    }


def load_saved_config() -> dict:
    if not CONFIG_PATH.exists():
        return default_config()
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = default_config()
        if isinstance(payload, dict):
            merged.update(payload)
        return merged
    except Exception:
        return default_config()


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_saved_config() -> None:
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()


def init_state() -> None:
    if "module" not in st.session_state:
        st.session_state.module = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "configured" not in st.session_state:
        st.session_state.configured = False
    if "config_cache" not in st.session_state:
        st.session_state.config_cache = load_saved_config()


def build_module_from_form(
    mysql_host: str,
    mysql_port: int,
    mysql_user: str,
    mysql_password: str,
    mysql_database: str,
    llm_api_key: str,
    llm_model: str,
    llm_base_url: str,
    system_prompt: str,
) -> LLMModule:
    db_config = DBConfig(
        host=mysql_host.strip(),
        port=int(mysql_port),
        user=mysql_user.strip(),
        password=mysql_password,
        database=mysql_database.strip(),
        charset="utf8mb4",
    )
    llm_config = LLMAPIConfig(
        api_key=llm_api_key.strip(),
        model=llm_model.strip(),
        base_url=llm_base_url.strip() or None,
    )
    return LLMModule(system_prompt=system_prompt.strip(), db_config=db_config, llm_config=llm_config)


def render_config_form() -> None:
    st.title("LLM—SQL")
    st.caption("首次进入请先配置数据库与 LLM API，配置成功后即可用自然语言操作 SQL。")
    cfg = st.session_state.config_cache

    top_left, top_right = st.columns([3, 1])
    with top_right:
        if st.button("清除已保存配置"):
            clear_saved_config()
            st.session_state.config_cache = default_config()
            st.success("已清除本地配置。")
            st.rerun()

    with st.form("config_form", clear_on_submit=False):
        st.subheader("MySQL 配置")
        mysql_host = st.text_input("Host", value=str(cfg["mysql_host"]))
        mysql_port = st.number_input("Port", min_value=1, max_value=65535, value=int(cfg["mysql_port"]), step=1)
        mysql_user = st.text_input("User", value=str(cfg["mysql_user"]))
        mysql_password = st.text_input("Password", type="password", value=str(cfg["mysql_password"]))
        mysql_database = st.text_input("Database", value=str(cfg["mysql_database"]))

        st.subheader("LLM 配置")
        llm_api_key = st.text_input("API Key", type="password", value=str(cfg["llm_api_key"]))
        llm_model = st.text_input("Model", value=str(cfg["llm_model"]))
        llm_base_url = st.text_input("Base URL（可选）", value=str(cfg["llm_base_url"]))
        system_prompt = st.text_area(
            "System Prompt",
            value=str(cfg["system_prompt"]),
            height=90,
        )
        remember_config = st.checkbox("记住本次配置（本地持久化）", value=bool(cfg["remember_config"]))
        save_sensitive = st.checkbox(
            "同时保存密码与 API Key（谨慎）",
            value=bool(cfg["save_sensitive"]),
            help="关闭时仅保存非敏感配置，下次仍需输入密码和 API Key。",
        )

        submitted = st.form_submit_button("保存并连接", type="primary")

    if not submitted:
        return

    required_texts = [mysql_host, mysql_user, mysql_database, llm_api_key, llm_model, system_prompt]
    if not all(v and str(v).strip() for v in required_texts):
        st.error("请完整填写必填项。")
        return

    try:
        next_config = {
            "mysql_host": mysql_host.strip(),
            "mysql_port": int(mysql_port),
            "mysql_user": mysql_user.strip(),
            "mysql_password": mysql_password,
            "mysql_database": mysql_database.strip(),
            "llm_api_key": llm_api_key.strip(),
            "llm_model": llm_model.strip(),
            "llm_base_url": llm_base_url.strip(),
            "system_prompt": system_prompt.strip(),
            "remember_config": remember_config,
            "save_sensitive": save_sensitive,
        }
        module = build_module_from_form(
            mysql_host=next_config["mysql_host"],
            mysql_port=int(mysql_port),
            mysql_user=next_config["mysql_user"],
            mysql_password=next_config["mysql_password"],
            mysql_database=next_config["mysql_database"],
            llm_api_key=next_config["llm_api_key"],
            llm_model=next_config["llm_model"],
            llm_base_url=next_config["llm_base_url"],
            system_prompt=next_config["system_prompt"],
        )
        ping_result = module.call_tool("database_crud_tool", {"action": "select", "table": "information_schema.tables", "limit": 1})
        st.session_state.module = module
        st.session_state.configured = True
        st.session_state.messages = []
        st.session_state.config_cache = next_config.copy()
        if remember_config:
            persisted = next_config.copy()
            if not save_sensitive:
                persisted["mysql_password"] = ""
                persisted["llm_api_key"] = ""
            save_config(persisted)
        else:
            clear_saved_config()
        st.success(f"连接成功，测试查询返回 {ping_result.get('count', 0)} 条记录。")
        st.rerun()
    except Exception as exc:
        st.error(f"连接失败：{exc}")


def render_chat() -> None:
    st.title("LLM-SQL")
    st.caption("通过自然语言让 LLM 调用数据库工具执行增删改查。")

    with st.expander("当前会话配置", expanded=False):
        if st.button("重新配置连接"):
            st.session_state.module = None
            st.session_state.configured = False
            st.rerun()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_text = st.chat_input("例如：查询 users 表最近 10 条数据")
    if not user_text:
        return

    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        with st.spinner("思考并执行中..."):
            try:
                reply = st.session_state.module.chat(user_text)
            except Exception as exc:
                reply = f"执行失败：{exc}"
            st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})


def main() -> None:
    init_state()
    if not st.session_state.configured:
        render_config_form()
    else:
        render_chat()


if __name__ == "__main__":
    main()
