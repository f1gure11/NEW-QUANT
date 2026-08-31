"""Curated, read-only macro-event schedule for the dashboard.

The dashboard must remain responsive even when public calendar websites are
slow or rate-limited.  This module therefore keeps a reviewed copy of the
official 2026 release schedule instead of scraping a third-party calendar on
each page refresh.  The payload deliberately contains *dates only*: market
consensus and released values need a separately auditable data source.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SCHEDULE_YEAR = 2026
SCHEDULE_UPDATED_AT = "2026-07-21T00:00:00+00:00"

FED_SOURCE_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_SOURCE_URL = "https://www.bls.gov/schedule/2026/home.htm"
BEA_SOURCE_URL = "https://www.bea.gov/news/schedule"
ECB_SOURCE_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"


def _event(
    event_id: str,
    *,
    scheduled_at: str,
    source_date: str,
    official_time: str,
    title: str,
    subtitle: str,
    categories: list[str],
    tags: list[str],
    source: str,
    source_url: str,
    market_note: str,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "scheduledAt": scheduled_at,
        "sourceDate": source_date,
        "officialTime": official_time,
        "title": title,
        "subtitle": subtitle,
        "categories": categories,
        "tags": tags,
        "impact": "high",
        "source": source,
        "sourceUrl": source_url,
        "marketNote": market_note,
    }


def _us_release_events(
    prefix: str,
    dates: list[tuple[str, str]],
    *,
    title: str,
    subtitle_prefix: str,
    categories: list[str],
    tags: list[str],
    source: str,
    source_url: str,
    market_note: str,
) -> list[dict[str, Any]]:
    """Build 08:30 ET releases, preserving EST/EDT in their UTC timestamp."""

    return [
        _event(
            f"{prefix}-{source_date}",
            scheduled_at=scheduled_at,
            source_date=source_date,
            official_time="08:30 ET",
            title=title,
            subtitle=subtitle_prefix,
            categories=categories,
            tags=tags,
            source=source,
            source_url=source_url,
            market_note=market_note,
        )
        for source_date, scheduled_at in dates
    ]


# All timestamps are UTC.  `sourceDate` / `officialTime` retain the official
# publisher's calendar convention, which is important around daylight saving
# changes and when Beijing time crosses into the following day.
_EVENTS: list[dict[str, Any]] = []

_EVENTS.extend(
    [
        _event(
            "fomc-2026-01-28",
            scheduled_at="2026-01-28T19:00:00+00:00",
            source_date="2026-01-28",
            official_time="14:00 ET",
            title="FOMC 利率决议",
            subtitle="1 月议息会议声明与发布会",
            categories=["central-bank", "decision"],
            tags=["央行", "决议"],
            source="Federal Reserve",
            source_url=FED_SOURCE_URL,
            market_note="利率路径、美元与风险资产波动",
        ),
        _event(
            "fomc-2026-03-18",
            scheduled_at="2026-03-18T18:00:00+00:00",
            source_date="2026-03-18",
            official_time="14:00 ET",
            title="FOMC 利率决议 · 季度经济预测（SEP）",
            subtitle="3 月议息会议，含点阵图与经济预测",
            categories=["central-bank", "decision", "quarterly"],
            tags=["央行", "决议", "季度"],
            source="Federal Reserve",
            source_url=FED_SOURCE_URL,
            market_note="点阵图与经济预测可能放大跨资产波动",
        ),
        _event(
            "fomc-2026-04-29",
            scheduled_at="2026-04-29T18:00:00+00:00",
            source_date="2026-04-29",
            official_time="14:00 ET",
            title="FOMC 利率决议",
            subtitle="4 月议息会议声明",
            categories=["central-bank", "decision"],
            tags=["央行", "决议"],
            source="Federal Reserve",
            source_url=FED_SOURCE_URL,
            market_note="利率路径、美元与风险资产波动",
        ),
        _event(
            "fomc-2026-06-17",
            scheduled_at="2026-06-17T18:00:00+00:00",
            source_date="2026-06-17",
            official_time="14:00 ET",
            title="FOMC 利率决议 · 季度经济预测（SEP）",
            subtitle="6 月议息会议，含点阵图与经济预测",
            categories=["central-bank", "decision", "quarterly"],
            tags=["央行", "决议", "季度"],
            source="Federal Reserve",
            source_url=FED_SOURCE_URL,
            market_note="点阵图与经济预测可能放大跨资产波动",
        ),
        _event(
            "fomc-2026-07-29",
            scheduled_at="2026-07-29T18:00:00+00:00",
            source_date="2026-07-29",
            official_time="14:00 ET",
            title="FOMC 利率决议",
            subtitle="7 月议息会议声明",
            categories=["central-bank", "decision"],
            tags=["央行", "决议"],
            source="Federal Reserve",
            source_url=FED_SOURCE_URL,
            market_note="利率路径、美元与风险资产波动",
        ),
        _event(
            "fomc-2026-09-16",
            scheduled_at="2026-09-16T18:00:00+00:00",
            source_date="2026-09-16",
            official_time="14:00 ET",
            title="FOMC 利率决议 · 季度经济预测（SEP）",
            subtitle="9 月议息会议，含点阵图与经济预测",
            categories=["central-bank", "decision", "quarterly"],
            tags=["央行", "决议", "季度"],
            source="Federal Reserve",
            source_url=FED_SOURCE_URL,
            market_note="点阵图与经济预测可能放大跨资产波动",
        ),
        _event(
            "fomc-2026-10-28",
            scheduled_at="2026-10-28T18:00:00+00:00",
            source_date="2026-10-28",
            official_time="14:00 ET",
            title="FOMC 利率决议",
            subtitle="10 月议息会议声明",
            categories=["central-bank", "decision"],
            tags=["央行", "决议"],
            source="Federal Reserve",
            source_url=FED_SOURCE_URL,
            market_note="利率路径、美元与风险资产波动",
        ),
        _event(
            "fomc-2026-12-09",
            scheduled_at="2026-12-09T19:00:00+00:00",
            source_date="2026-12-09",
            official_time="14:00 ET",
            title="FOMC 利率决议 · 季度经济预测（SEP）",
            subtitle="12 月议息会议，含点阵图与经济预测",
            categories=["central-bank", "decision", "quarterly"],
            tags=["央行", "决议", "季度"],
            source="Federal Reserve",
            source_url=FED_SOURCE_URL,
            market_note="点阵图与经济预测可能放大跨资产波动",
        ),
    ]
)

_EVENTS.extend(
    _us_release_events(
        "cpi",
        [
            ("2026-01-13", "2026-01-13T13:30:00+00:00"),
            ("2026-02-13", "2026-02-13T13:30:00+00:00"),
            ("2026-03-11", "2026-03-11T12:30:00+00:00"),
            ("2026-04-10", "2026-04-10T12:30:00+00:00"),
            ("2026-05-12", "2026-05-12T12:30:00+00:00"),
            ("2026-06-10", "2026-06-10T12:30:00+00:00"),
            ("2026-07-14", "2026-07-14T12:30:00+00:00"),
            ("2026-08-12", "2026-08-12T12:30:00+00:00"),
            ("2026-09-11", "2026-09-11T12:30:00+00:00"),
            ("2026-10-14", "2026-10-14T12:30:00+00:00"),
            ("2026-11-10", "2026-11-10T13:30:00+00:00"),
            ("2026-12-10", "2026-12-10T13:30:00+00:00"),
        ],
        title="美国 CPI",
        subtitle_prefix="消费者物价指数（月度）",
        categories=["inflation", "monthly"],
        tags=["通胀", "月度"],
        source="U.S. Bureau of Labor Statistics",
        source_url=BLS_SOURCE_URL,
        market_note="通胀定价、实际利率与美元敏感时点",
    )
)

_EVENTS.extend(
    _us_release_events(
        "nfp",
        [
            ("2026-01-09", "2026-01-09T13:30:00+00:00"),
            ("2026-02-06", "2026-02-06T13:30:00+00:00"),
            ("2026-03-06", "2026-03-06T13:30:00+00:00"),
            ("2026-04-03", "2026-04-03T12:30:00+00:00"),
            ("2026-05-08", "2026-05-08T12:30:00+00:00"),
            ("2026-06-05", "2026-06-05T12:30:00+00:00"),
            ("2026-07-02", "2026-07-02T12:30:00+00:00"),
            ("2026-08-07", "2026-08-07T12:30:00+00:00"),
            ("2026-09-04", "2026-09-04T12:30:00+00:00"),
            ("2026-10-02", "2026-10-02T12:30:00+00:00"),
            ("2026-11-06", "2026-11-06T13:30:00+00:00"),
            ("2026-12-04", "2026-12-04T13:30:00+00:00"),
        ],
        title="美国非农就业报告",
        subtitle_prefix="Employment Situation：非农、失业率与薪资",
        categories=["employment", "monthly"],
        tags=["就业", "非农", "月度"],
        source="U.S. Bureau of Labor Statistics",
        source_url=BLS_SOURCE_URL,
        market_note="就业韧性、工资增速与政策预期敏感时点",
    )
)

_EVENTS.extend(
    _us_release_events(
        "pce",
        [
            ("2026-01-30", "2026-01-30T13:30:00+00:00"),
            ("2026-02-27", "2026-02-27T13:30:00+00:00"),
            ("2026-03-27", "2026-03-27T12:30:00+00:00"),
            ("2026-04-30", "2026-04-30T12:30:00+00:00"),
            ("2026-05-29", "2026-05-29T12:30:00+00:00"),
            ("2026-06-26", "2026-06-26T12:30:00+00:00"),
            ("2026-07-30", "2026-07-30T12:30:00+00:00"),
            ("2026-08-26", "2026-08-26T12:30:00+00:00"),
            ("2026-09-30", "2026-09-30T12:30:00+00:00"),
            ("2026-10-29", "2026-10-29T12:30:00+00:00"),
            ("2026-11-25", "2026-11-25T13:30:00+00:00"),
            ("2026-12-23", "2026-12-23T13:30:00+00:00"),
        ],
        title="美国 PCE 物价指数",
        subtitle_prefix="个人收入与支出报告（含核心 PCE）",
        categories=["inflation", "monthly"],
        tags=["通胀", "PCE", "月度"],
        source="U.S. Bureau of Economic Analysis",
        source_url=BEA_SOURCE_URL,
        market_note="美联储偏好的通胀指标，关注核心 PCE",
    )
)

_EVENTS.extend(
    [
        _event(
            "gdp-advance-2026-q1",
            scheduled_at="2026-04-30T12:30:00+00:00",
            source_date="2026-04-30",
            official_time="08:30 ET",
            title="美国 GDP 初值 · 2026 Q1",
            subtitle="季度 GDP 增速首估",
            categories=["quarterly", "growth"],
            tags=["季度", "GDP"],
            source="U.S. Bureau of Economic Analysis",
            source_url=BEA_SOURCE_URL,
            market_note="增长动能与风险偏好敏感时点",
        ),
        _event(
            "gdp-advance-2026-q2",
            scheduled_at="2026-07-30T12:30:00+00:00",
            source_date="2026-07-30",
            official_time="08:30 ET",
            title="美国 GDP 初值 · 2026 Q2",
            subtitle="季度 GDP 增速首估",
            categories=["quarterly", "growth"],
            tags=["季度", "GDP"],
            source="U.S. Bureau of Economic Analysis",
            source_url=BEA_SOURCE_URL,
            market_note="增长动能与风险偏好敏感时点",
        ),
        _event(
            "gdp-advance-2026-q3",
            scheduled_at="2026-10-29T12:30:00+00:00",
            source_date="2026-10-29",
            official_time="08:30 ET",
            title="美国 GDP 初值 · 2026 Q3",
            subtitle="季度 GDP 增速首估",
            categories=["quarterly", "growth"],
            tags=["季度", "GDP"],
            source="U.S. Bureau of Economic Analysis",
            source_url=BEA_SOURCE_URL,
            market_note="增长动能与风险偏好敏感时点",
        ),
    ]
)

_EVENTS.extend(
    [
        _event(
            "ecb-2026-02-05",
            scheduled_at="2026-02-05T13:15:00+00:00",
            source_date="2026-02-05",
            official_time="14:15 CET",
            title="欧洲央行（ECB）利率决议",
            subtitle="管理委员会货币政策决定",
            categories=["central-bank", "decision"],
            tags=["央行", "决议", "ECB"],
            source="European Central Bank",
            source_url=ECB_SOURCE_URL,
            market_note="欧元、欧洲利率与全球风险偏好",
        ),
        _event(
            "ecb-2026-03-19",
            scheduled_at="2026-03-19T13:15:00+00:00",
            source_date="2026-03-19",
            official_time="14:15 CET",
            title="欧洲央行（ECB）利率决议",
            subtitle="管理委员会货币政策决定",
            categories=["central-bank", "decision"],
            tags=["央行", "决议", "ECB"],
            source="European Central Bank",
            source_url=ECB_SOURCE_URL,
            market_note="欧元、欧洲利率与全球风险偏好",
        ),
        _event(
            "ecb-2026-04-30",
            scheduled_at="2026-04-30T12:15:00+00:00",
            source_date="2026-04-30",
            official_time="14:15 CEST",
            title="欧洲央行（ECB）利率决议",
            subtitle="管理委员会货币政策决定",
            categories=["central-bank", "decision"],
            tags=["央行", "决议", "ECB"],
            source="European Central Bank",
            source_url=ECB_SOURCE_URL,
            market_note="欧元、欧洲利率与全球风险偏好",
        ),
        _event(
            "ecb-2026-06-11",
            scheduled_at="2026-06-11T12:15:00+00:00",
            source_date="2026-06-11",
            official_time="14:15 CEST",
            title="欧洲央行（ECB）利率决议",
            subtitle="管理委员会货币政策决定",
            categories=["central-bank", "decision"],
            tags=["央行", "决议", "ECB"],
            source="European Central Bank",
            source_url=ECB_SOURCE_URL,
            market_note="欧元、欧洲利率与全球风险偏好",
        ),
        _event(
            "ecb-2026-07-23",
            scheduled_at="2026-07-23T12:15:00+00:00",
            source_date="2026-07-23",
            official_time="14:15 CEST",
            title="欧洲央行（ECB）利率决议",
            subtitle="管理委员会货币政策决定",
            categories=["central-bank", "decision"],
            tags=["央行", "决议", "ECB"],
            source="European Central Bank",
            source_url=ECB_SOURCE_URL,
            market_note="欧元、欧洲利率与全球风险偏好",
        ),
        _event(
            "ecb-2026-09-10",
            scheduled_at="2026-09-10T12:15:00+00:00",
            source_date="2026-09-10",
            official_time="14:15 CEST",
            title="欧洲央行（ECB）利率决议",
            subtitle="管理委员会货币政策决定",
            categories=["central-bank", "decision"],
            tags=["央行", "决议", "ECB"],
            source="European Central Bank",
            source_url=ECB_SOURCE_URL,
            market_note="欧元、欧洲利率与全球风险偏好",
        ),
        _event(
            "ecb-2026-10-29",
            scheduled_at="2026-10-29T13:15:00+00:00",
            source_date="2026-10-29",
            official_time="14:15 CET",
            title="欧洲央行（ECB）利率决议",
            subtitle="管理委员会货币政策决定",
            categories=["central-bank", "decision"],
            tags=["央行", "决议", "ECB"],
            source="European Central Bank",
            source_url=ECB_SOURCE_URL,
            market_note="欧元、欧洲利率与全球风险偏好",
        ),
        _event(
            "ecb-2026-12-17",
            scheduled_at="2026-12-17T13:15:00+00:00",
            source_date="2026-12-17",
            official_time="14:15 CET",
            title="欧洲央行（ECB）利率决议",
            subtitle="管理委员会货币政策决定",
            categories=["central-bank", "decision"],
            tags=["央行", "决议", "ECB"],
            source="European Central Bank",
            source_url=ECB_SOURCE_URL,
            market_note="欧元、欧洲利率与全球风险偏好",
        ),
    ]
)

_EVENTS.sort(key=lambda item: str(item["scheduledAt"]))


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _as_utc(now: datetime | None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def macro_calendar_snapshot(*, now: datetime | None = None) -> dict[str, Any]:
    """Return the reviewed calendar in the dashboard's compact API shape."""

    current = _as_utc(now)
    events: list[dict[str, Any]] = []
    for raw_event in _EVENTS:
        event = dict(raw_event)
        event_time = _parse_timestamp(str(event["scheduledAt"]))
        event["status"] = "released" if event_time <= current else "scheduled"
        events.append(event)

    next_event = next((event for event in events if event["status"] == "scheduled"), None)
    upcoming = [event for event in events if event["status"] == "scheduled"]
    month_events = [
        event
        for event in upcoming
        if _parse_timestamp(str(event["scheduledAt"])).year == current.year
        and _parse_timestamp(str(event["scheduledAt"])).month == current.month
    ]
    return {
        "ok": True,
        "scheduleYear": SCHEDULE_YEAR,
        "scheduleUpdatedAt": SCHEDULE_UPDATED_AT,
        "generatedAt": current.isoformat(timespec="seconds"),
        "displayTimeZone": "Asia/Shanghai",
        "displayTimeZoneLabel": "北京时间",
        "status": "stale" if current.year > SCHEDULE_YEAR else "current",
        "nextEvent": next_event,
        "events": events,
        "summary": {
            "total": len(events),
            "upcoming": len(upcoming),
            "thisMonth": len(month_events),
        },
        "notice": "这是已核对的官方发布时间表，用于事件风控与观察；不含市场预期、前值或公布结果。实际发布可能因官方临时调整而变化。",
        "sources": [
            {"name": "Federal Reserve · FOMC Calendar", "url": FED_SOURCE_URL},
            {"name": "BLS · 2026 Release Schedule", "url": BLS_SOURCE_URL},
            {"name": "BEA · Release Schedule", "url": BEA_SOURCE_URL},
            {"name": "ECB · Governing Council Calendar", "url": ECB_SOURCE_URL},
        ],
    }
