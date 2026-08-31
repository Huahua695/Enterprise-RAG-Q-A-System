# -*- coding: utf-8 -*-
"""端到端：建知识库 → 上传文档 → 等待后台向量化完成 → 流式问答 → 断言答案与引用。"""
import uuid

import httpx
from playwright.sync_api import expect


def test_create_kb_upload_and_ask(page, base_url, admin_headers, llm_ready, product_doc_path):
    kb_name = f"E2E测试库-{uuid.uuid4().hex[:6]}"
    try:
        # 1. 登录进入聊天页
        page.goto(f"{base_url}/login")
        page.get_by_placeholder("用户名").fill("admin")
        page.get_by_placeholder("密码").fill("123456")
        page.get_by_role("button", name="登 录").click()
        page.wait_for_url("**/chat", timeout=15000)

        # 2. 新建知识库（Modal 为 antd 默认英文 locale，确认按钮是 OK）
        page.get_by_role("button", name="知识库管理").click()
        page.wait_for_url("**/knowledge", timeout=15000)
        page.get_by_role("button", name="新建知识库").click()
        page.get_by_placeholder("输入知识库名称").fill(kb_name)
        page.get_by_placeholder("输入知识库描述").fill("端到端测试自动创建")
        page.get_by_role("button", name="OK").click()
        expect(page.get_by_text("知识库创建成功")).to_be_visible(timeout=15000)

        # 3. 进入该库的文档面板，上传商品资料
        page.get_by_role("row").filter(has_text=kb_name).get_by_role("button", name="查看文档").click()
        page.set_input_files('input[type="file"]', product_doc_path)
        expect(page.get_by_text("文档已上传，后台向量化中")).to_be_visible(timeout=15000)

        # 4. 轮询生效：状态从 处理中 变为 已完成（后台向量化 + 前端每 2s 刷新）
        doc_row = page.get_by_role("row").filter(has_text="星尘X1Pro商品.md")
        expect(doc_row.get_by_text("已完成")).to_be_visible(timeout=180000)

        # 5. 回聊天页新建会话提问（未选库时后端检索全部可见知识库）
        page.goto(f"{base_url}/chat")
        page.get_by_role("button", name="新建对话").click()
        page.get_by_placeholder("输入你的问题...").fill("星尘X1 Pro 的价格是多少？")
        page.get_by_role("button", name="发 送").click()

        # 6. 断言：流式回答出现、引用来源展示且包含上传资料的内容
        expect(page.get_by_text("引用来源：").first).to_be_visible(timeout=120000)
        expect(page.get_by_text("星尘X1 Pro").first).to_be_visible(timeout=10000)
    finally:
        # 清理测试数据（删除知识库会级联清理文档、上传文件与向量索引）
        resp = httpx.get(f"{base_url}/api/knowledge/knowledge-bases",
                         headers=admin_headers, timeout=10)
        for kb in (resp.json() if resp.status_code == 200 else []):
            if kb["name"] == kb_name:
                httpx.delete(f"{base_url}/api/knowledge/knowledge-bases/{kb['id']}",
                             headers=admin_headers, timeout=30)
