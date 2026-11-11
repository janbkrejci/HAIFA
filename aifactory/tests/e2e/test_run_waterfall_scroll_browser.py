"""A long run's gantt scrolls inside its own region without overlapping blocks (canned APIs)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Route, expect, sync_playwright
from test_f3_browser import _launch
from test_limits_layout import _server
from test_runs_overflow_browser import _assert_document_fits

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]

# aifactory/web/src/lib/waterfall.ts: MIN_BLOCK_PX, QUEUED_BLOCK_PX, BLOCK_GAP_PX
MIN_BLOCK_PX = 132
QUEUED_BLOCK_PX = 170
BLOCK_GAP_PX = 6


def _iso(t: datetime) -> str:
    return t.isoformat()


def _phase(run_id: str, phase_id: str, seq: int, **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "adw_id": run_id,
        "phase_id": phase_id,
        "seq": seq,
        "name": phase_id,
        "kind": "agent",
        "owner": "builder",
        "description": None,
        "status": "success",
        "attempt": 1,
        "retries": 0,
        "error": None,
        "started_at": None,
        "ended_at": None,
        "harness": "claude",
        "model": "claude-opus-4",
        "tokens": 0,
        "cost": 0,
        "usage": None,
        "duration_s": None,
    }
    row.update(over)
    return row


def _long_phases(run_id: str, start: datetime) -> list[dict[str, Any]]:
    """An engineer request, dozens of short builds with retries, tests, a long review,
    a running build and queued phases."""
    phases = [
        _phase(
            run_id,
            "req",
            0,
            name="request",
            kind="engineer",
            owner="engineer",
            started_at=_iso(start),
            ended_at=_iso(start + timedelta(seconds=2)),
        )
    ]
    t = start + timedelta(seconds=2)
    seq = 1
    for i in range(36):
        end = t + timedelta(seconds=15)
        phases.append(
            _phase(
                run_id,
                f"build-{i}",
                seq,
                name="build",
                description=f"Pokus {i % 4 + 1}",
                attempt=i % 4 + 1,
                retries=i % 4,
                status="fail" if i % 4 != 3 else "success",
                started_at=_iso(t),
                ended_at=_iso(end),
                duration_s=15,
            )
        )
        seq += 1
        t = end
        if i % 4 == 3:
            end = t + timedelta(seconds=5)
            phases.append(
                _phase(
                    run_id,
                    f"test-{i}",
                    seq,
                    name="test",
                    kind="code",
                    owner="test",
                    harness=None,
                    model=None,
                    started_at=_iso(t),
                    ended_at=_iso(end),
                    duration_s=5,
                )
            )
            seq += 1
            t = end
    end = t + timedelta(minutes=8)
    phases.append(
        _phase(
            run_id,
            "review",
            seq,
            name="review",
            owner="reviewer",
            started_at=_iso(t),
            ended_at=_iso(end),
            duration_s=480,
        )
    )
    seq += 1
    phases.append(
        _phase(
            run_id,
            "build-run",
            seq,
            name="build",
            status="running",
            attempt=5,
            started_at=_iso(end),
        )
    )
    seq += 1
    for i in range(4):
        phases.append(
            _phase(
                run_id,
                f"queued-{i}",
                seq,
                name=f"next-{i}",
                owner="reviewer" if i % 2 else "builder",
                status="queued",
            )
        )
        seq += 1
    return phases


def _detail(
    run_id: str, state: str, start: datetime, phases: list[dict[str, Any]]
) -> dict[str, Any]:
    run = {
        "run_id": run_id,
        "task_id": "HAIFA-S01-T112",
        "task_title": "Dlouhý Gantt",
        "workflow": "build-review",
        "state": state,
        "branch": "factory/HAIFA-S01-T112-1",
        "started_at": _iso(start),
        "ended_at": None if state == "running" else phases[-1]["ended_at"],
        "duration_s": None,
        "tokens": 0,
        "cost": 0,
        "error": None,
        "note": None,
        "started_by": "manual",
        "pr": None,
        "archived": False,
        "phases": [{"seq": p["seq"], "name": p["name"], "status": p["status"]} for p in phases],
    }
    return {
        "run": run,
        "session": {
            "adw_id": run_id,
            "adw_name": None,
            "request": "# Zadání",
            "status": None,
            "engineer": None,
            "started_at": None,
            "ended_at": None,
            "total_tokens": None,
            "total_cost": None,
        },
        "usage": {"read": 0, "written": 0},
        "agents": [],
        "phases": phases,
        "gates": [],
        "envelopes": [],
        "cursors": {"events": 0, "phases": 0, "gates": 0, "envelopes": 0},
    }


def _serve(details: dict[str, dict[str, Any]]) -> Any:
    fallback = _server("live")

    def serve(route: Route) -> None:
        url = urlsplit(route.request.url)
        assert url.netloc == "haifa.test", route.request.url
        path = url.path
        prefix = "/api/repos/haifa/runs"
        data: Any
        if path == "/api/repos/haifa/live":
            route.abort()
            return
        if path == prefix:
            data = {"runs": [d["run"] for d in details.values()]}
        elif path.startswith(prefix + "/"):
            parts = path[len(prefix) + 1 :].split("/")
            detail = details.get(parts[0])
            if detail is None:
                fallback(route)
                return
            if len(parts) == 1:
                data = detail
            elif parts[1] == "events":
                data = {"events": [], "has_more": False, "cursor": 0}
            elif parts[1] == "tail":
                data = {
                    **{k: detail[k] for k in ("run", "session", "agents", "cursors")},
                    "events": [],
                    "phases": detail["phases"],
                    "gates": [],
                    "envelopes": [],
                    "usage_delta": {"read": 0, "written": 0},
                    "has_more": False,
                }
            else:
                data = {}
        else:
            fallback(route)
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps({"ok": True, "data": data, "error": None, "warnings": []}),
        )

    return serve


GEOMETRY = """el => {
    const r = (x) => {
        const b = x.getBoundingClientRect();
        return {left: b.left, right: b.right, width: b.width};
    };
    const axis = el.querySelector('.axis-row .track');
    return {
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        scrollLeft: el.scrollLeft,
        region: r(el),
        axis: r(axis),
        lanes: [...el.querySelectorAll('[data-lane]')].map(lane => ({
            id: lane.dataset.lane,
            track: r(lane.querySelector('.track')),
            label: r(lane.querySelector('.label')),
            blocks: [...lane.querySelectorAll('button.block')].map(b => ({
                id: b.dataset.phase, queued: b.classList.contains('queued'), ...r(b)
            })),
        })),
    };
}"""


def _check_lanes(geometry: dict[str, Any]) -> None:
    """No two blocks of a lane overlap, each keeps its floor; every track lines up with the axis."""
    axis = geometry["axis"]
    for lane in geometry["lanes"]:
        track = lane["track"]
        assert abs(track["left"] - axis["left"]) < 0.5, (lane["id"], track, axis)
        assert abs(track["width"] - axis["width"]) < 0.5, (lane["id"], track, axis)
        blocks = sorted(lane["blocks"], key=lambda b: b["left"])
        for prev, cur in zip(blocks, blocks[1:], strict=False):
            assert cur["left"] >= prev["right"] + BLOCK_GAP_PX - 1, (lane["id"], prev, cur)
        for block in blocks:
            if lane["id"] == "engineer":
                continue
            floor = QUEUED_BLOCK_PX if block["queued"] else MIN_BLOCK_PX
            assert block["width"] >= floor - 1, (lane["id"], block)


def _assert_in_viewport(page: Page, selector: str) -> None:
    box = page.locator(selector).first.bounding_box()
    assert box is not None, selector
    width = page.evaluate("document.documentElement.clientWidth")
    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 0.5, (selector, box, width)


def _at_right(page: Page) -> None:
    page.wait_for_function("""() => {
        const el = document.querySelector('[data-test="waterfall-scroll"]');
        return el && Math.abs(el.scrollWidth - el.clientWidth - el.scrollLeft) <= 2;
    }""")


def _grow(page: Page, details: dict[str, dict[str, Any]], start: datetime) -> None:
    """Append queued work on the same lane so the minimum-width canvas must grow."""
    phases = details["long-run"]["phases"]
    for _ in range(10):
        seq = len(phases) + 1
        phases.append(_phase("long-run", f"extra-{seq}", seq, status="queued"))
    details["long-run"] = _detail("long-run", "running", start, phases)
    previous = page.locator('[data-test="waterfall-scroll"]').evaluate("el => el.scrollWidth")
    page.evaluate("""() => window.waterfallLive.dispatchEvent(new MessageEvent('trace', {
        data: JSON.stringify({run_ids: ['long-run'], task_ids: [], phases: 1, events: 0})
    }))""")
    expect(page.locator("button.block")).to_have_count(len(phases))
    page.wait_for_function(
        """previous =>
        document.querySelector('[data-test="waterfall-scroll"]').scrollWidth > previous
    """,
        arg=previous,
    )


def test_long_run_waterfall_scrolls_locally() -> None:
    now = datetime.now(UTC)
    long_start = now - timedelta(minutes=30)
    long_phases = _long_phases("long-run", long_start)
    short_start = now - timedelta(hours=2)
    short_phases = [
        _phase(
            "short-run",
            "plan",
            1,
            name="plan",
            owner="planner",
            started_at=_iso(short_start),
            ended_at=_iso(short_start + timedelta(minutes=3)),
        ),
        _phase(
            "short-run",
            "test",
            2,
            name="test",
            kind="code",
            owner="test",
            started_at=_iso(short_start + timedelta(minutes=3)),
            ended_at=_iso(short_start + timedelta(minutes=4)),
        ),
    ]
    details = {
        "long-run": _detail("long-run", "running", long_start, long_phases),
        "short-run": _detail("short-run", "succeeded", short_start, short_phases),
    }

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.add_init_script("""window.EventSource = class extends EventTarget {
                constructor() { super(); window.waterfallLive = this; }
                close() {}
            }""")
            page.route("**/*", _serve(details))
            page.goto("http://haifa.test/#/r/haifa/runs/long-run")
            region = page.locator('[data-test="waterfall-scroll"]')
            expect(region).to_be_visible()
            expect(region).to_have_attribute("data-overflow", "true")
            expect(page.locator('[data-test="waterfall-scroll"]')).to_have_count(1)
            expect(region).to_have_css("overflow-x", "auto")
            page.evaluate("document.fonts.ready")
            blocks = region.locator("button.block")
            expect(blocks).to_have_count(len(long_phases))

            _at_right(page)
            geometry = region.evaluate(GEOMETRY)
            assert geometry["scrollWidth"] > geometry["clientWidth"] + 1000, geometry
            assert (
                abs(geometry["scrollLeft"] - geometry["scrollWidth"] + geometry["clientWidth"]) <= 2
            )
            _check_lanes(geometry)
            # every lane keeps its own phases: one builder lane holds the dozens of builds
            builder = next(lane for lane in geometry["lanes"] if lane["id"] == "agent:builder")
            assert len(builder["blocks"]) == 36 + 1 + 2, builder
            _assert_document_fits(page)
            _assert_in_viewport(page, ".run-detail")
            _assert_in_viewport(page, "header.head")
            _assert_in_viewport(page, '[data-test="waterfall"]')

            toggle = page.get_by_role("checkbox", name="Automaticky posouvat pohled")
            expect(toggle).to_be_checked()
            _grow(page, details, long_start)
            _at_right(page)
            # Native keyboard scrolling pauses following; data growth preserves that offset.
            region.focus()
            region.evaluate("""el => {
                window.waterfallScrollEnd = new Promise(resolve =>
                    el.addEventListener('scrollend', () => resolve(), {once: true}));
            }""")
            region.press("ArrowLeft")
            expect(toggle).not_to_be_checked()
            page.evaluate("window.waterfallScrollEnd")
            manual_left = region.evaluate("el => el.scrollLeft")
            _grow(page, details, long_start)
            expect(toggle).not_to_be_checked()
            assert abs(region.evaluate("el => el.scrollLeft") - manual_left) <= 2
            # Position just short of the new edge, then return with a native horizontal key.
            region.evaluate("el => { el.scrollLeft = el.scrollWidth - el.clientWidth - 20 }")
            region.press("ArrowRight")
            expect(toggle).to_be_checked()
            _at_right(page)
            _grow(page, details, long_start)
            _at_right(page)
            # Space operates the native accessible checkbox in both directions.
            toggle.focus()
            toggle.press("Space")
            expect(toggle).not_to_be_checked()
            paused = region.evaluate("el => el.scrollLeft")
            _grow(page, details, long_start)
            assert abs(region.evaluate("el => el.scrollLeft") - paused) <= 2
            toggle.press("Space")
            expect(toggle).to_be_checked()
            _at_right(page)
            before_resize = region.evaluate("el => el.clientWidth")
            page.set_viewport_size({"width": 1000, "height": 900})
            page.wait_for_function(
                """width =>
                document.querySelector('[data-test="waterfall-scroll"]').clientWidth < width
            """,
                arg=before_resize,
            )
            _at_right(page)
            scrolled = region.evaluate(GEOMETRY)
            assert scrolled["scrollLeft"] >= scrolled["scrollWidth"] - scrolled["clientWidth"] - 1
            _check_lanes(scrolled)
            for lane in scrolled["lanes"]:
                assert abs(lane["label"]["left"] - scrolled["region"]["left"]) < 1.5, lane["label"]
            _assert_document_fits(page)

            last = details["long-run"]["phases"][-1]
            target = region.locator(f'button.block[data-phase="{last["phase_id"]}"]')
            # bring the block into the window first: a scroll dismisses an open tooltip
            target.scroll_into_view_if_needed()
            page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            box = target.bounding_box()
            assert box is not None
            region_box = scrolled["region"]
            assert box["x"] >= region_box["left"] + 240 - 1, (box, region_box)
            assert box["x"] + box["width"] <= region_box["right"] + 0.5, (box, region_box)
            target.hover()
            tooltip = page.get_by_role("tooltip")
            expect(tooltip).to_contain_text(last["name"])
            target.click()
            expect(page).to_have_url(
                f"http://haifa.test/#/r/haifa/runs/long-run/{last['phase_id']}"
            )
            expect(target).to_have_attribute("aria-pressed", "true")
            panel = page.locator(".phase-panel")
            expect(panel).to_be_visible()
            expect(panel).to_contain_text(last["name"])
            _assert_in_viewport(page, ".phase-panel")
            _assert_document_fits(page)
            # the selection keeps the scroll position
            assert region.evaluate("el => el.scrollLeft") > 0

            # a short run fills the region without a horizontal scroll
            page.goto("http://haifa.test/#/r/haifa/runs/short-run")
            expect(page.locator('button.block[data-phase="plan"]')).to_be_visible()
            short = region.evaluate(GEOMETRY)
            assert short["scrollWidth"] <= short["clientWidth"], short
            expect(region).not_to_have_attribute("data-overflow", "true")
            expect(toggle).to_have_count(0)
            _check_lanes(short)
            _assert_document_fits(page)
        finally:
            browser.close()
