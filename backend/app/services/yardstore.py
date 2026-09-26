"""堆存记录业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "yardstore"
REQUIRED_FIELDS = ["堆存单号", "关联箱号", "箱区编号"]
STATUS_ORDER = ["待进场", "堆存中", "待提离", "已提离"]
ACTION_RULES = {"确认进场": "堆存中", "确认提离": "已提离", "撤销堆存": "待进场"}
NEGATIVE_ACTIONS = ["撤销堆存"]


class YardstoreService:
    def list_entries(
        self,
        *,
        order_no: str | None = None,
        container_no: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, str | None]:
        rows = store.rows(MODULE)
        order_no = (order_no or "").strip()
        container_no = (container_no or "").strip()
        if order_no:
            rows = [row for row in rows if order_no.casefold() in str(row.get("堆存单号", "")).casefold()]
        if container_no:
            rows = [row for row in rows if container_no.casefold() in str(row.get("关联箱号", "")).casefold()]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        notice = None
        if total == 0:
            notice = self._empty_notice(order_no=order_no, container_no=container_no)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total, notice

    def _empty_notice(self, *, order_no: str, container_no: str) -> str:
        all_rows = store.rows(MODULE)
        scope_total = len(all_rows)

        def matches(field: str, keyword: str) -> bool:
            return any(keyword.casefold() in str(row.get(field, "")).casefold() for row in all_rows)

        order_known = bool(order_no) and matches("堆存单号", order_no)
        container_known = bool(container_no) and matches("关联箱号", container_no)
        if order_no and container_no:
            if not order_known and not container_known:
                return (
                    f"当前列表共 {scope_total} 条堆存单，堆存单号「{order_no}」与关联箱号"
                    f"「{container_no}」都查不到记录，请核对后重试"
                )
            if not order_known:
                return f"当前列表共 {scope_total} 条堆存单，查无堆存单号包含「{order_no}」的记录，请确认单号是否填写正确"
            if not container_known:
                return f"当前列表共 {scope_total} 条堆存单，查无关联箱号包含「{container_no}」的记录，请确认箱号是否填写正确"
            return (
                f"当前列表共 {scope_total} 条堆存单，堆存单号「{order_no}」与关联箱号「{container_no}」"
                "各自都有记录，但不在同一张堆存单上（两个条件为叠加过滤）"
            )
        if order_no:
            return (
                f"当前列表共 {scope_total} 条堆存单，查无堆存单号包含「{order_no}」的记录，"
                "请确认单号是否填写正确"
            )
        if container_no:
            return (
                f"当前列表共 {scope_total} 条堆存单，查无关联箱号包含「{container_no}」的记录，"
                "请确认箱号是否填写正确"
            )
        return "当前列表没有符合条件的堆存单"

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"堆存单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于堆存记录可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"堆存单已{action}"
