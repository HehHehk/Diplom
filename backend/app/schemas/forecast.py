from pydantic import BaseModel


class WeekdayStat(BaseModel):
    weekday: int
    label: str
    count: int
    share: float


class HourStat(BaseModel):
    hour: int
    count: int
    share: float


class LoadForecast(BaseModel):
    equipment_id: int
    title: str
    period_days: int
    total_bookings: int
    by_weekday: list[WeekdayStat]
    by_hour: list[HourStat]
    best_weekday: str | None
    best_hours: list[int]
    recommendation: str
