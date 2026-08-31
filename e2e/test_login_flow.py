# -*- coding: utf-8 -*-
"""端到端：登录失败与成功流。"""
from playwright.sync_api import expect


def test_login_wrong_password_shows_error(page, base_url):
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("用户名").fill("admin")
    page.get_by_placeholder("密码").fill("definitely-wrong-password")
    page.get_by_role("button", name="登 录").click()

    # 后端返回 401 → antd message 弹出错误提示
    expect(page.get_by_text("用户名或密码错误")).to_be_visible(timeout=15000)


def test_login_success_navigates_to_chat(page, base_url):
    # 成功登录同时会重置上一次失败留下的限流计数（同 用户名|IP 维度）
    page.goto(f"{base_url}/login")
    page.get_by_placeholder("用户名").fill("admin")
    page.get_by_placeholder("密码").fill("123456")
    page.get_by_role("button", name="登 录").click()

    page.wait_for_url("**/chat", timeout=15000)
    expect(page.get_by_text("RAG 知识库问答")).to_be_visible(timeout=10000)
