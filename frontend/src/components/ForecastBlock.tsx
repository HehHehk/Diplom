import { Alert, Progress, Space, Typography } from "antd";
import type { Forecast } from "../api/types";

export default function ForecastBlock({ forecast }: { forecast: Forecast }) {
  const maxWeekday = Math.max(...forecast.by_weekday.map((item) => item.count), 1);
  const maxHour = Math.max(...forecast.by_hour.map((item) => item.count), 1);
  const hours = forecast.by_hour.filter((item) => item.count > 0);

  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Alert
        type={forecast.total_bookings ? "success" : "info"}
        showIcon
        title={forecast.recommendation}
        description={`Учтено выдач за ${forecast.period_days} дней: ${forecast.total_bookings}`}
      />
      {forecast.total_bookings ? (
        <>
          <div>
            <Typography.Text type="secondary">По дням недели</Typography.Text>
            <div className="bars">
              {forecast.by_weekday.map((item) => (
                <div key={item.weekday} className="bar-row">
                  <span className="bar-label">{item.label}</span>
                  <Progress
                    percent={Math.round((item.count / maxWeekday) * 100)}
                    showInfo={false}
                    strokeColor="#2f6fed"
                  />
                  <span className="bar-value">{item.count}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <Typography.Text type="secondary">По часам выдачи</Typography.Text>
            <div className="bars">
              {hours.map((item) => (
                <div key={item.hour} className="bar-row">
                  <span className="bar-label">{String(item.hour).padStart(2, "0")}:00</span>
                  <Progress
                    percent={Math.round((item.count / maxHour) * 100)}
                    showInfo={false}
                    strokeColor="#18a058"
                  />
                  <span className="bar-value">{item.count}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </Space>
  );
}
